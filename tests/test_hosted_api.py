"""API no modo hospedado: login, CSRF, isolamento entre usuários, downloads e painel."""

from __future__ import annotations

import importlib
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from guaraci.api import main as api_main
from guaraci.core.results import JobResult

PASSWORD = "senha-forte-123"
_ENV_KEYS = (
    "GUARACI_MODE",
    "GUARACI_SECRET_KEY",
    "GUARACI_OUTPUT_ROOT",
    "GUARACI_DB_PATH",
    "GUARACI_COOKIE_SECURE",
    "GUARACI_RATE_AUTH_PER_MINUTE",
    "GUARACI_MIN_FREE_DISK_GB",
    "GUARACI_JANITOR_SECONDS",
)


class _FakeDownloads:
    def validate_source_params(self, source: str, params):  # noqa: ANN001
        if source != "snis":
            raise ValueError("Fonte desconhecida")

    def supports_discovery(self, source: str) -> bool:  # noqa: ARG002
        return False

    def run(self, source: str, progress_callback=None, **kwargs):  # noqa: ANN001, ANN003, ARG002
        folder = Path(str(kwargs["output_dir"]))
        (folder / "sub").mkdir(parents=True, exist_ok=True)
        (folder / "dados.csv").write_bytes(b"a,b\n1,2\n")
        (folder / "sub" / "extra.txt").write_text("ok", encoding="utf-8")
        (folder / ".cache").mkdir(exist_ok=True)
        (folder / ".cache" / "segredo").write_text("x", encoding="utf-8")
        return JobResult(
            source=source,
            documents_found=1,
            downloaded_count=1,
            manifest_path=str(folder / "manifest.json"),
        )


def _reload_local() -> None:
    importlib.reload(api_main)


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = {
        "GUARACI_MODE": "hosted",
        "GUARACI_SECRET_KEY": "x" * 48,
        "GUARACI_OUTPUT_ROOT": str(tmp_path / "saidas"),
        "GUARACI_DB_PATH": str(tmp_path / "estado" / "guaraci.db"),
        "GUARACI_COOKIE_SECURE": "false",
        "GUARACI_RATE_AUTH_PER_MINUTE": "50",
        "GUARACI_MIN_FREE_DISK_GB": "0",
        "GUARACI_JANITOR_SECONDS": "3600",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = importlib.reload(api_main)
    module.job_service._download_service = _FakeDownloads()
    runtime = module.runtime
    assert runtime is not None
    try:
        yield SimpleNamespace(module=module, runtime=runtime, tmp=tmp_path)
    finally:
        runtime.stop()
        runtime.db.close()
        for key in _ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        _reload_local()


def _user(runtime, email: str, *, role: str = "user", status: str = "approved"):
    return runtime.accounts.register(
        email=email,
        name="Pessoa Teste",
        institution="USP",
        purpose="teste",
        password=PASSWORD,
        consent_version="2026-11",
        role=role,
        status=status,
    )


def _login(module, email: str) -> tuple[TestClient, str]:
    client = TestClient(module.app)
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf"]


def _wait(module, job_id: str) -> None:
    module.job_service.wait_for_job(job_id, timeout_seconds=10)


def test_public_and_private_paths(hosted) -> None:
    client = TestClient(hosted.module.app)
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/sources").status_code == 401
    assert client.get("/jobs").status_code == 401
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.post("/downloads/snis", json={}).status_code == 404
    me = client.get("/auth/me").json()
    assert me == {"mode": "hosted", "authenticated": False, "privacy_version": "2026-11"}


def test_privacy_page_uses_configured_deadlines(hosted) -> None:
    page = TestClient(hosted.module.app).get("/privacidade")
    assert page.status_code == 200
    assert "{{" not in page.text
    assert "ficam 30 dias" in page.text and "após 365 dias" in page.text
    assert "48 horas" in page.text


def test_security_headers(hosted) -> None:
    response = TestClient(hosted.module.app).get("/")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_signup_needs_consent_and_approval(hosted) -> None:
    client = TestClient(hosted.module.app)
    body = {"name": "Ana", "email": "ana@exemplo.org", "password": PASSWORD, "consent": False}
    assert client.post("/auth/signup", json=body).status_code == 400

    body["consent"] = True
    first = client.post("/auth/signup", json=body)
    again = client.post("/auth/signup", json=body)
    assert first.status_code == again.status_code == 202
    assert first.json() == again.json()  # não revela e-mail já cadastrado

    pending = client.post("/auth/login", json={"email": "ana@exemplo.org", "password": PASSWORD})
    assert pending.status_code == 403

    user = hosted.runtime.accounts.get_by_email("ana@exemplo.org")
    hosted.runtime.accounts.set_status(user.id, "approved")
    _login(hosted.module, "ana@exemplo.org")


def test_wrong_password_is_generic_and_locks(hosted) -> None:
    _user(hosted.runtime, "bia@exemplo.org")
    client = TestClient(hosted.module.app)
    wrong = {"email": "bia@exemplo.org", "password": "errada-errada"}
    unknown = {"email": "ninguem@exemplo.org", "password": "errada-errada"}
    assert client.post("/auth/login", json=wrong).json() == client.post(
        "/auth/login", json=unknown
    ).json()
    codes = [client.post("/auth/login", json=wrong).status_code for _ in range(6)]
    assert codes[-1] == 429
    # Bloqueado mesmo com a senha certa.
    right = {"email": "bia@exemplo.org", "password": PASSWORD}
    assert client.post("/auth/login", json=right).status_code == 429


def test_csrf_and_origin_are_required(hosted) -> None:
    _user(hosted.runtime, "caio@exemplo.org")
    client, csrf = _login(hosted.module, "caio@exemplo.org")
    body = {"source": "snis", "params": {}}
    assert client.post("/jobs", json=body).status_code == 403
    assert (
        client.post(
            "/jobs", json=body, headers={"X-CSRF-Token": csrf, "Origin": "https://malicioso.example"}
        ).status_code
        == 403
    )
    created = client.post("/jobs", json=body, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 202
    _wait(hosted.module, created.json()["job_id"])


def test_jobs_are_isolated_and_paths_hidden(hosted) -> None:
    _user(hosted.runtime, "dora@exemplo.org")
    _user(hosted.runtime, "edu@exemplo.org")
    dora, csrf = _login(hosted.module, "dora@exemplo.org")
    edu, _ = _login(hosted.module, "edu@exemplo.org")

    created = dora.post(
        "/jobs",
        json={"source": "snis", "params": {"output_dir": "/etc"}},
        headers={"X-CSRF-Token": csrf},
    ).json()
    job_id = created["job_id"]
    _wait(hosted.module, job_id)

    job = dora.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert job["output_dir"] is None
    assert "output_dir" not in job["params"]
    root = str(hosted.tmp / "saidas")
    assert root not in str(job) and root.replace("\\", "/") not in str(job)
    output = dora.get(f"/jobs/{job_id}/output").json()
    assert root not in str(output)

    assert edu.get(f"/jobs/{job_id}").status_code == 404
    assert edu.get(f"/jobs/{job_id}/files").status_code == 404
    assert edu.get("/jobs").json() == []
    assert dora.post(f"/jobs/{job_id}/open-output").status_code == 404


def test_signed_downloads(hosted) -> None:
    _user(hosted.runtime, "fabi@exemplo.org")
    client, csrf = _login(hosted.module, "fabi@exemplo.org")
    job_id = client.post(
        "/jobs", json={"source": "snis", "params": {}}, headers={"X-CSRF-Token": csrf}
    ).json()["job_id"]
    _wait(hosted.module, job_id)

    listing = client.get(f"/jobs/{job_id}/files").json()
    names = sorted(item["name"] for item in listing["files"])
    assert names == ["dados.csv", "sub/extra.txt"]  # pasta oculta fica de fora

    item = next(item for item in listing["files"] if item["name"] == "dados.csv")
    anonymous = TestClient(hosted.module.app)
    assert anonymous.get(item["url"]).text == "a,b\n1,2\n"

    parsed = urlparse(item["url"])
    query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    query["name"] = "../../estado/guaraci.db"
    assert anonymous.get(parsed.path, params=query).status_code == 403
    query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    query["sig"] = query["sig"][:-2] + "AA"
    assert anonymous.get(parsed.path, params=query).status_code == 403

    archive = zipfile.ZipFile(io.BytesIO(anonymous.get(listing["zip_url"]).content))
    assert sorted(archive.namelist()) == ["dados.csv", "sub/extra.txt"]
    assert archive.read("sub/extra.txt") == b"ok"

    later = datetime.now(timezone.utc) + timedelta(hours=72)
    hosted.module.job_service.purge_expired_outputs(now=later)
    assert anonymous.get(item["url"]).status_code == 410


def test_admin_panel_and_tracking(hosted) -> None:
    admin_user = _user(hosted.runtime, "admin@exemplo.org", role="admin")
    regular = _user(hosted.runtime, "gil@exemplo.org")
    user_client, user_csrf = _login(hosted.module, "gil@exemplo.org")
    assert user_client.get("/admin/stats").status_code == 403

    view = user_client.post(
        "/events/view", json={"view": "catalogo", "source": "snis"}, headers={"X-CSRF-Token": user_csrf}
    )
    assert view.status_code == 204

    admin, csrf = _login(hosted.module, "admin@exemplo.org")
    stats = admin.get("/admin/stats").json()
    assert stats["users_total"] == 2
    assert stats["logins"] == 2
    assert {"view": "catalogo", "n": 1, "users": 1} in stats["top_views"]

    journey = admin.get("/admin/journey", params={"user_id": regular.id}).json()
    assert [event["kind"] for event in journey][:2] == ["page_view", "login_ok"]

    quota = admin.post(
        f"/admin/users/{regular.id}/quota", json={"quota_jobs_day": 0}, headers={"X-CSRF-Token": csrf}
    )
    assert quota.status_code == 200
    blocked = user_client.post(
        "/jobs", json={"source": "snis", "params": {}}, headers={"X-CSRF-Token": user_csrf}
    )
    assert blocked.status_code == 429

    self_block = admin.post(
        f"/admin/users/{admin_user.id}/status", json={"status": "disabled"}, headers={"X-CSRF-Token": csrf}
    )
    assert self_block.status_code == 400

    disabled = admin.post(
        f"/admin/users/{regular.id}/status", json={"status": "disabled"}, headers={"X-CSRF-Token": csrf}
    )
    assert disabled.status_code == 200
    assert user_client.get("/jobs").status_code == 401  # sessão revogada


def test_logout_revokes_session(hosted) -> None:
    _user(hosted.runtime, "hel@exemplo.org")
    client, csrf = _login(hosted.module, "hel@exemplo.org")
    assert client.get("/jobs").status_code == 200
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/jobs").status_code == 401


def test_local_mode_is_back_after_hosted_tests() -> None:
    assert api_main.HOSTED is False
    assert api_main.runtime is None
    client = TestClient(api_main.app)
    assert client.get("/jobs").status_code == 200
