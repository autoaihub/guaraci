"""Liga o modo hospedado à aplicação FastAPI.

``install()`` acrescenta o middleware (login obrigatório, CSRF, limite de
requisições, cabeçalhos de segurança), as rotas de conta, rastreamento,
download e administração, e a faxina periódica das saídas e dos registros.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from guaraci.hosted.accounts import AccountError, Accounts, Session
from guaraci.hosted.artifacts import LinkSigner, list_files, resolve_file, stream_zip
from guaraci.hosted.db import Database
from guaraci.hosted.ratelimit import RateLimiter
from guaraci.hosted.settings import HostedSettings
from guaraci.hosted.tracking import Tracker, clean_view
from guaraci.services.jobs import DownloadJobService

ZIP_NAME = "__todos__.zip"
DOWNLOAD_LINK_SECONDS = 6 * 3600
_STATIC_DIR = Path(__file__).resolve().parent.parent / "api" / "static"

# Caminhos que não exigem login.
_PUBLIC_EXACT = {
    "/",
    "/ui",
    "/health",
    "/privacidade",
    "/auth/login",
    "/auth/signup",
    "/auth/logout",
    "/auth/me",
}
_PUBLIC_PREFIXES = ("/static/", "/files/")
# Caminhos que somem no modo hospedado (abrem pasta local, baixam na requisição,
# documentam a API inteira para quem não está logado).
_BLOCKED = re.compile(
    r"^/(docs|redoc|openapi\.json)(/.*)?$|^/downloads/|^/jobs/[^/]+/open-output$"
)
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

_CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class SignupRequest(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=320)
    institution: str = Field(default="", max_length=300)
    purpose: str = Field(default="", max_length=2000)
    password: str = Field(max_length=256)
    consent: bool = False


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class ViewEvent(BaseModel):
    view: str = Field(max_length=80)
    source: Optional[str] = Field(default=None, max_length=80)


class StatusChange(BaseModel):
    status: str


class RoleChange(BaseModel):
    role: str


class QuotaChange(BaseModel):
    quota_jobs_day: Optional[int] = Field(default=None, ge=0, le=1000)


class HostedRuntime:
    def __init__(self, settings: HostedSettings, job_service: DownloadJobService):
        settings.validate()
        self.settings = settings
        self.jobs = job_service
        self.db = Database(settings.db_path)
        self.accounts = Accounts(self.db, session_ttl_hours=settings.session_ttl_hours)
        self.tracker = Tracker(self.db)
        self.limiter = RateLimiter()
        self.signer = LinkSigner(settings.secret_key)
        self.cookie_name = "__Host-guaraci" if settings.cookie_secure else "guaraci_session"
        self._stop = threading.Event()
        self._janitor: Optional[threading.Thread] = None
        root = settings.output_root.resolve() if settings.output_root else None
        self._root_patterns: List[re.Pattern[str]] = []
        if root is not None:
            for text in {str(root), root.as_posix()}:
                escaped = re.escape(text)
                self._root_patterns.append(
                    re.compile(escaped + r"[\\/]users[\\/]\d+[\\/][0-9a-f]{32}[\\/]?")
                )
                self._root_patterns.append(re.compile(escaped + r"[\\/]?"))

    # -- utilidades -------------------------------------------------------
    @staticmethod
    def client_ip(request: Request) -> Optional[str]:
        # Atrás do proxy, o uvicorn roda com --proxy-headers e
        # --forwarded-allow-ips=<IP do proxy>: request.client já é o IP real.
        return request.client.host if request.client else None

    @staticmethod
    def session_of(request: Request) -> Optional[Session]:
        return getattr(request.state, "session", None)

    def owner_id(self, request: Request) -> Optional[str]:
        session = self.session_of(request)
        return str(session.user.id) if session else None

    def track(self, request: Request, kind: str, **fields: Any) -> None:
        session = self.session_of(request)
        try:
            self.tracker.record(
                kind,
                user_id=fields.pop("user_id", session.user.id if session else None),
                session_id=session.token_hash if session else None,
                ip=self.client_ip(request),
                user_agent=request.headers.get("user-agent"),
                **fields,
            )
        except Exception as exc:  # noqa: BLE001 - registro nunca derruba a requisição
            logger.warning(f"Falha ao registrar evento {kind}: {exc}")

    def redact(self, value: Any) -> Any:
        """Tira os caminhos do servidor de respostas que vão ao usuário."""
        if isinstance(value, str):
            for pattern in self._root_patterns:
                value = pattern.sub("", value)
            return value
        if isinstance(value, dict):
            return {key: self.redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        return value

    def public_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload)
        params = dict(data.get("params") or {})
        params.pop("output_dir", None)
        data["params"] = params
        data["output_dir"] = None
        data.pop("owner_id", None)
        return self.redact(data)

    def limits_payload(self, session: Session) -> Dict[str, Any]:
        policy = self.jobs.policy
        usage = self.jobs.owner_usage(str(session.user.id))
        return {
            "limits": {
                "active_per_user": policy.max_active_per_owner,
                "jobs_per_day": session.user.quota_jobs_day or policy.max_jobs_per_day,
                "job_gb": round((policy.max_job_bytes or 0) / 1024**3, 2),
                "job_minutes": round((policy.max_job_seconds or 0) / 60),
                "output_ttl_hours": policy.output_ttl_hours,
            },
            "usage": usage,
        }

    def _set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            self.cookie_name,
            token,
            max_age=int(self.settings.session_ttl_hours * 3600),
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
            path="/",
        )

    def _origin_ok(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if not origin:
            # Navegadores mandam Origin em POST de fetch; ausência = cliente de
            # linha de comando, que ainda precisa do token CSRF da sessão.
            return True
        if self.settings.public_origin:
            return origin.rstrip("/") == self.settings.public_origin.rstrip("/")
        host = request.headers.get("host", "")
        return origin.split("://", 1)[-1].rstrip("/") == host

    # -- faxina -----------------------------------------------------------
    def run_janitor_once(self) -> Dict[str, Any]:
        purged = self.jobs.purge_expired_outputs()
        self.accounts.purge()
        retention = self.tracker.apply_retention(
            ip_days=self.settings.ip_retention_days,
            event_days=self.settings.event_retention_days,
        )
        return {"purged_jobs": len(purged), **retention}

    def start_janitor(self) -> None:
        if self._janitor is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self.settings.janitor_interval_seconds):
                try:
                    report = self.run_janitor_once()
                    if report["purged_jobs"] or report["deleted"]:
                        logger.info(f"Faxina do modo hospedado: {report}")
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"Faxina falhou: {exc}")

        self._janitor = threading.Thread(target=loop, name="guaraci-janitor", daemon=True)
        self._janitor.start()

    def stop(self) -> None:
        self._stop.set()

    # -- middleware -------------------------------------------------------
    async def middleware(self, request: Request, call_next):
        path = request.url.path
        ip = self.client_ip(request) or "?"
        settings = self.settings

        if _BLOCKED.match(path):
            return self._headers(JSONResponse({"detail": "Not Found"}, status_code=404))

        wait = self.limiter.hit("ip", ip, capacity=settings.rate_ip_per_minute, period=60)
        if not wait and path in {"/auth/login", "/auth/signup"} and request.method == "POST":
            wait = self.limiter.hit("auth", ip, capacity=settings.rate_auth_per_minute, period=60)
            if not wait and path == "/auth/signup":
                wait = self.limiter.hit(
                    "signup", ip, capacity=settings.rate_signup_per_hour, period=3600
                )
        if wait:
            return self._too_many(wait)

        session = self.accounts.resolve_session(request.cookies.get(self.cookie_name))
        request.state.session = session

        public = path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)
        if not public and session is None:
            return self._headers(
                JSONResponse({"detail": "Faça login para continuar."}, status_code=401)
            )
        if path.startswith("/admin") and (session is None or not session.user.is_admin):
            return self._headers(JSONResponse({"detail": "Acesso restrito."}, status_code=403))

        if request.method in _UNSAFE:
            if not self._origin_ok(request):
                return self._headers(JSONResponse({"detail": "Origem não permitida."}, status_code=403))
            if session is not None and path not in {"/auth/login", "/auth/signup"}:
                if request.headers.get("x-csrf-token") != session.csrf_token:
                    return self._headers(
                        JSONResponse({"detail": "Token CSRF ausente ou inválido."}, status_code=403)
                    )
            if session is not None:
                user_key = str(session.user.id)
                if path == "/jobs" or re.match(r"^/jobs/[^/]+/retry$", path):
                    wait = self.limiter.hit(
                        "jobs", user_key, capacity=settings.rate_jobs_per_hour, period=3600
                    )
                elif path.endswith("/discovery"):
                    wait = self.limiter.hit(
                        "discovery", user_key, capacity=settings.rate_discovery_per_hour, period=3600
                    )
                if wait:
                    return self._too_many(wait)

        response = await call_next(request)
        return self._headers(response)

    def _too_many(self, wait: float) -> Response:
        seconds = max(1, int(wait + 0.999))
        return self._headers(
            JSONResponse(
                {"detail": f"Muitas requisições. Tente de novo em {seconds} s."},
                status_code=429,
                headers={"Retry-After": str(seconds)},
            )
        )

    def _headers(self, response: Response) -> Response:
        headers = response.headers
        headers.setdefault("Content-Security-Policy", _CSP)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        if self.settings.cookie_secure:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    # -- rotas ------------------------------------------------------------
    def router(self) -> APIRouter:
        router = APIRouter()
        rt = self

        @router.post("/auth/signup", status_code=202)
        def signup(payload: SignupRequest, request: Request) -> Dict[str, str]:
            if not payload.consent:
                raise HTTPException(400, "É preciso aceitar a política de privacidade.")
            try:
                user = rt.accounts.register(
                    email=payload.email,
                    name=payload.name,
                    institution=payload.institution,
                    purpose=payload.purpose,
                    password=payload.password,
                    consent_version=rt.settings.privacy_version,
                )
            except AccountError as exc:
                raise HTTPException(exc.status_code, str(exc)) from exc
            if user is not None:
                rt.track(request, "signup", user_id=user.id)
            # Mesma resposta para e-mail novo ou já cadastrado.
            return {
                "message": "Cadastro recebido. Um administrador vai analisar o pedido; "
                "tente entrar mais tarde para ver se o acesso foi liberado."
            }

        @router.post("/auth/login")
        def login(payload: LoginRequest, request: Request) -> Response:
            ip = rt.client_ip(request)
            try:
                user = rt.accounts.authenticate(payload.email, payload.password, ip)
            except AccountError as exc:
                kind = "lockout" if exc.status_code == 429 else "login_fail"
                known = rt.accounts.get_by_email(payload.email)
                rt.track(
                    request,
                    kind,
                    user_id=known.id if known else None,
                    meta={"status": exc.status_code},
                )
                raise HTTPException(exc.status_code, str(exc)) from exc
            token, session = rt.accounts.create_session(
                user, ip=ip, user_agent=request.headers.get("user-agent")
            )
            request.state.session = session
            rt.track(request, "login_ok")
            response = JSONResponse(rt.me_payload(session))
            rt._set_cookie(response, token)
            return response

        @router.post("/auth/logout")
        def logout(request: Request) -> Response:
            session = rt.session_of(request)
            if session is not None:
                rt.track(request, "logout")
                rt.accounts.revoke_session(session.token_hash)
            response = JSONResponse({"ok": True})
            response.delete_cookie(rt.cookie_name, path="/", secure=rt.settings.cookie_secure)
            return response

        @router.get("/auth/me")
        def me(request: Request) -> Dict[str, Any]:
            session = rt.session_of(request)
            if session is None:
                return {
                    "mode": "hosted",
                    "authenticated": False,
                    "privacy_version": rt.settings.privacy_version,
                }
            return rt.me_payload(session)

        @router.post("/events/view", status_code=204)
        def view_event(payload: ViewEvent, request: Request) -> Response:
            view = clean_view(payload.view)
            if view:
                rt.track(request, "page_view", view=view, source=payload.source)
            return Response(status_code=204)

        @router.get("/privacidade", response_class=HTMLResponse, include_in_schema=False)
        def privacy() -> HTMLResponse:
            page = _STATIC_DIR / "privacidade.html"
            return HTMLResponse(page.read_text(encoding="utf-8"))

        @router.get("/jobs/{job_id}/files")
        def job_files(job_id: str, request: Request) -> Dict[str, Any]:
            session = rt.session_of(request)
            assert session is not None
            try:
                job = rt.jobs.get_job(job_id, owner_id=str(session.user.id))
                folder = rt.jobs.job_output_folder(job_id, owner_id=str(session.user.id))
            except KeyError as exc:
                raise HTTPException(404, f"Job '{job_id}' not found") from exc
            files = list_files(folder) if job.status in rt.jobs.TERMINAL_STATES else []
            expires = int(time.time()) + DOWNLOAD_LINK_SECONDS
            items = [
                {**item, "url": rt.download_url(job_id, session.user.id, str(item["name"]), expires)}
                for item in files
            ]
            return {
                "job_id": job_id,
                "status": job.status,
                "expires_at": job.expires_at,
                "purged": job.purged_at is not None,
                "total_bytes": sum(int(item["bytes"]) for item in files),
                "files": items,
                "zip_url": (
                    rt.download_url(job_id, session.user.id, ZIP_NAME, expires) if files else None
                ),
            }

        @router.get("/files/{job_id}")
        def download(
            job_id: str,
            request: Request,
            name: str = Query(..., max_length=500),
            u: int = Query(...),
            exp: int = Query(...),
            sig: str = Query(..., max_length=100),
        ) -> Response:
            if not rt.signer.verify(job_id, u, name, exp, sig):
                raise HTTPException(403, "Link de download inválido ou vencido.")
            wait = rt.limiter.hit("download", str(u), capacity=60, period=3600)
            if wait:
                return rt._too_many(wait)
            try:
                folder = rt.jobs.job_output_folder(job_id, owner_id=str(u))
            except KeyError as exc:
                raise HTTPException(404, "Resultado não encontrado.") from exc
            if folder is None:
                raise HTTPException(410, "Este resultado já expirou e foi apagado.")
            rt.track(request, "download", user_id=u, job_id=job_id, meta={"name": name})
            if name == ZIP_NAME:
                files = list_files(folder)
                if not files:
                    raise HTTPException(404, "Nenhum arquivo para baixar.")
                filename = f"guaraci-{job_id[:8]}.zip"
                return StreamingResponse(
                    stream_zip(folder, files),
                    media_type="application/zip",
                    headers={
                        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
                    },
                )
            target = resolve_file(folder, name)
            if target is None:
                raise HTTPException(404, "Arquivo não encontrado.")
            return FileResponse(target, filename=target.name)

        # -- administração --------------------------------------------------
        @router.get("/admin/users")
        def admin_users(status: Optional[str] = None) -> List[Dict[str, Any]]:
            items = []
            for user in rt.accounts.list(status):
                data = user.public()
                data["usage"] = rt.jobs.owner_usage(str(user.id))
                items.append(data)
            return items

        @router.post("/admin/users/{user_id}/status")
        def admin_status(user_id: int, payload: StatusChange, request: Request) -> Dict[str, Any]:
            session = rt.session_of(request)
            assert session is not None
            if user_id == session.user.id and payload.status != "approved":
                raise HTTPException(400, "Você não pode bloquear a própria conta.")
            try:
                user = rt.accounts.set_status(user_id, payload.status, by=session.user.id)
            except AccountError as exc:
                raise HTTPException(exc.status_code, str(exc)) from exc
            rt.track(request, "admin_action", meta={"action": "status", "target": user_id, "status": payload.status})
            return user.public()

        @router.post("/admin/users/{user_id}/role")
        def admin_role(user_id: int, payload: RoleChange, request: Request) -> Dict[str, Any]:
            session = rt.session_of(request)
            assert session is not None
            if user_id == session.user.id and payload.role != "admin":
                raise HTTPException(400, "Você não pode tirar o próprio papel de administrador.")
            try:
                user = rt.accounts.set_role(user_id, payload.role)
            except AccountError as exc:
                raise HTTPException(exc.status_code, str(exc)) from exc
            rt.track(request, "admin_action", meta={"action": "role", "target": user_id, "role": payload.role})
            return user.public()

        @router.post("/admin/users/{user_id}/quota")
        def admin_quota(user_id: int, payload: QuotaChange, request: Request) -> Dict[str, Any]:
            try:
                user = rt.accounts.set_quota(user_id, payload.quota_jobs_day)
            except AccountError as exc:
                raise HTTPException(exc.status_code, str(exc)) from exc
            rt.track(request, "admin_action", meta={"action": "quota", "target": user_id, "quota": payload.quota_jobs_day})
            return user.public()

        @router.delete("/admin/users/{user_id}")
        def admin_delete(user_id: int, request: Request) -> Dict[str, bool]:
            session = rt.session_of(request)
            assert session is not None
            if user_id == session.user.id:
                raise HTTPException(400, "Você não pode excluir a própria conta.")
            rt.accounts.delete(user_id)
            rt.track(request, "admin_action", meta={"action": "delete", "target": user_id})
            return {"deleted": True}

        @router.get("/admin/stats")
        def admin_stats(days: int = Query(30, ge=1, le=366)) -> Dict[str, Any]:
            stats = rt.tracker.stats(days=days)
            all_jobs = rt.jobs.list_jobs(limit=100000)
            stats["queue"] = {
                "queued": sum(1 for job in all_jobs if job.status == "queued"),
                "running": sum(1 for job in all_jobs if job.status in {"running", "cancel_requested"}),
            }
            return stats

        @router.get("/admin/journey")
        def admin_journey(
            user_id: Optional[int] = None,
            session_id: Optional[str] = Query(default=None, max_length=16),
            limit: int = Query(500, ge=1, le=5000),
        ) -> List[Dict[str, Any]]:
            try:
                return rt.tracker.journey(user_id=user_id, session_id=session_id, limit=limit)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

        @router.get("/admin/events")
        def admin_events(
            kind: Optional[str] = None, limit: int = Query(200, ge=1, le=5000)
        ) -> List[Dict[str, Any]]:
            return rt.tracker.recent(limit=limit, kind=kind)

        @router.get("/admin/jobs")
        def admin_jobs(limit: int = Query(200, ge=1, le=2000)) -> List[Dict[str, Any]]:
            items = []
            for job in rt.jobs.list_jobs(limit=limit):
                data = rt.public_job(job.to_dict())
                data["owner_id"] = job.owner_id
                data.pop("events", None)
                items.append(data)
            return items

        @router.post("/admin/jobs/{job_id}/cancel")
        def admin_cancel(job_id: str, request: Request) -> Dict[str, Any]:
            try:
                job = rt.jobs.cancel_job(job_id)
            except KeyError as exc:
                raise HTTPException(404, f"Job '{job_id}' not found") from exc
            rt.track(request, "admin_action", job_id=job_id, meta={"action": "cancel_job"})
            return rt.public_job(job.to_dict())

        return router

    def me_payload(self, session: Session) -> Dict[str, Any]:
        return {
            "mode": "hosted",
            "authenticated": True,
            "user": session.user.public(),
            "csrf": session.csrf_token,
            "privacy_version": self.settings.privacy_version,
            **self.limits_payload(session),
        }

    def download_url(self, job_id: str, user_id: int, name: str, expires: int) -> str:
        query = urlencode(
            {"name": name, "u": user_id, "exp": expires, "sig": self.signer.sign(job_id, user_id, name, expires)}
        )
        return f"/files/{job_id}?{query}"


def install(app: FastAPI, job_service: DownloadJobService, settings: HostedSettings) -> HostedRuntime:
    runtime = HostedRuntime(settings, job_service)
    app.middleware("http")(runtime.middleware)
    app.include_router(runtime.router())
    if runtime.accounts.count_admins() == 0:
        logger.warning(
            "Modo hospedado sem administrador. Crie um com: guaraci admin create --email ..."
        )
    runtime.start_janitor()
    return runtime
