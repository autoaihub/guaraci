"""Cliente CKAN genérico (``/api/3/action/``) dos portais de dados abertos.

Generaliza o cliente do MonitorAr (``guaraci/mma/monitorar.py``), que continua
preso ao conjunto ``ar-puro-monitorar``. Aqui o conjunto é parâmetro e o
transporte cobre o que os portais mostraram nas sondagens de 2026-10:

- ``package_show`` e ``package_search`` devolvem o ``result`` do CKAN; o
  ``datastore_search`` não é usado (em MG ele devolve ``total`` 0), baixa-se
  sempre o ``resource.url``;
- alguns portais (MAPA, MG, BH) só respondem a um User-Agent de navegador:
  ``user_agent`` por cliente;
- o download pode redirecionar (302) para um S3 assinado (Recife). O
  ``urllib`` segue o redirecionamento e a URL assinada não é guardada nem
  registrada em lugar nenhum (nem em mensagem de erro, que sai sem query);
- o recurso é gravado em ``<destino>.part`` e só então renomeado; arquivo
  zip/xlsx truncado ou página de erro no lugar do dado viram erro
  classificado e retentável.
"""

from __future__ import annotations

import http.client
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from guaraci import __version__
from guaraci.arquivos.http_files import transport_error
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)

__all__ = [
    "BROWSER_USER_AGENT",
    "CkanClient",
    "CkanClientError",
    "CkanResource",
    "resources_from_package",
]

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_ARCHIVE_SUFFIXES = (".zip", ".xlsx")
_ERROR_PAGE = re.compile(rb"<!doctype html|<html|request rejected", re.IGNORECASE)


class CkanClientError(ApiClientError):
    """Falha ao consultar ou baixar dados de um portal CKAN."""


@dataclass(frozen=True)
class CkanResource:
    """Recurso de um conjunto CKAN, como o portal o anuncia."""

    package_id: str
    id: str
    name: str
    url: str
    format: str = ""
    size: Optional[int] = None
    last_modified: Optional[str] = None
    package_title: str = ""


def resources_from_package(package: Dict[str, Any]) -> List[CkanResource]:
    """Recursos de um ``package`` (``result`` do ``package_show``), na ordem do portal."""
    package_id = str(package.get("name") or package.get("id") or "")
    found: List[CkanResource] = []
    for item in package.get("resources") or ():
        url = str(item.get("url") or "").strip()
        if not url or str(item.get("state") or "active").lower() == "deleted":
            continue
        size = item.get("size")
        found.append(
            CkanResource(
                package_id=package_id,
                id=str(item.get("id") or ""),
                name=str(item.get("name") or "").strip(),
                url=url,
                format=str(item.get("format") or "").strip(),
                size=int(size) if isinstance(size, (int, float)) and size else None,
                last_modified=str(item.get("last_modified") or item.get("created") or "") or None,
                package_title=str(package.get("title") or ""),
            )
        )
    return found


class CkanClient:
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
    ) -> None:
        selected = str(base_url).strip()
        if not selected:
            raise ValueError("base_url is required for a CKAN client.")
        self.base_url = selected if selected.endswith("/") else selected + "/"
        self.user_agent = user_agent or self.USER_AGENT
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    # -- ação da API ------------------------------------------------------
    def action_url(self, action: str, **params: object) -> str:
        query = {k: v for k, v in params.items() if v is not None}
        return f"{self.base_url}{action}" + (f"?{urlencode(query)}" if query else "")

    def package_show(self, id: str) -> Dict[str, Any]:  # noqa: A002 - nome da API CKAN
        return self._action("package_show", id=id)

    def package_search(
        self,
        q: Optional[str] = None,
        fq: Optional[str] = None,
        rows: int = 1000,
        start: int = 0,
    ) -> Dict[str, Any]:
        """``result`` da busca: ``count`` e ``results`` (lista de conjuntos)."""
        return self._action("package_search", q=q, fq=fq, rows=rows, start=start)

    def iter_packages(
        self, q: Optional[str] = None, fq: Optional[str] = None, rows: int = 1000
    ) -> Iterator[Dict[str, Any]]:
        """Todos os conjuntos da busca, paginando até esgotar."""
        start = 0
        while True:
            result = self.package_search(q=q, fq=fq, rows=rows, start=start)
            page = result.get("results") or []
            yield from page
            start += len(page)
            if not page or start >= int(result.get("count") or 0):
                return

    def resources(self, package_id: str) -> List[CkanResource]:
        return resources_from_package(self.package_show(package_id))

    def _action(self, action: str, **params: object) -> Dict[str, Any]:
        url = self.action_url(action, **params)

        def send() -> bytes:
            request = Request(url, headers={"User-Agent": self.user_agent})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return response.read()
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc
            except TimeoutError as exc:
                raise self._timeout(url) from exc
            except (OSError, http.client.HTTPException) as exc:
                error = transport_error(exc, url, self.timeout_seconds, CkanClientError)
                if error is None:
                    raise
                raise error from exc

        raw = request_with_retry(send, max_attempts=self.max_attempts)
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
            if not payload.get("success", True):
                raise ValueError(str(payload.get("error")))
            result = payload["result"]
            if not isinstance(result, dict):
                raise TypeError("result is not an object")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise CkanClientError(
                f"CKAN {action} returned an unexpected payload from '{self.base_url}'.",
                category="response_format",
                hint="Confira se o conjunto existe no portal e se a base_url termina em /api/3/action/.",
            ) from exc
        return result

    # -- download -----------------------------------------------------------
    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa ``url`` em fluxo para ``destination`` (via ``.part``). Devolve os bytes gravados.

        Segue redirecionamento (S3 assinado) sem guardar a URL final. Se o
        destino é zip ou xlsx, confere que o arquivo recebido é um zip válido.
        """
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        needs_zip = destination.suffix.lower() in _ARCHIVE_SUFFIXES

        def send() -> int:
            written = 0
            expected: Optional[int] = None
            request = Request(url, headers={"User-Agent": self.user_agent})
            head = b""
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response, open(
                    partial, "wb"
                ) as sink:
                    length = response.headers.get("Content-Length")
                    expected = int(length) if length and length.isdigit() else None
                    for block in iter(lambda: response.read(chunk_size), b""):
                        if not head:
                            head = block[:2048]
                        sink.write(block)
                        written += len(block)
                        if progress_callback is not None:
                            progress_callback(written)
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc
            except TimeoutError as exc:
                raise self._timeout(url) from exc
            except (OSError, http.client.HTTPException) as exc:
                error = transport_error(exc, url, self.timeout_seconds, CkanClientError)
                if error is None:
                    raise
                raise error from exc
            if expected is not None and written < expected:
                raise CkanClientError(
                    f"Download of '{_clean(url)}' was truncated: {written} of {expected} bytes.",
                    category="incomplete",
                    retryable=True,
                    hint="O servidor encerrou a conexão antes do fim; tente de novo.",
                )
            if needs_zip and not zipfile.is_zipfile(partial):
                raise CkanClientError(
                    f"'{_clean(url)}' should be a zip/xlsx but the {written} bytes received "
                    "are not a valid archive (truncated or an error page).",
                    category="incomplete",
                    retryable=True,
                    hint="Baixe de novo; se persistir, confira o recurso no portal.",
                )
            if not needs_zip and _ERROR_PAGE.search(head):
                raise CkanClientError(
                    f"'{_clean(url)}' returned an HTML page instead of data.",
                    category="response_format",
                    hint="O portal devolveu página de erro ou bloqueio; não é o arquivo de dados.",
                )
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    # -- erros ----------------------------------------------------------------
    def _timeout(self, url: str) -> CkanClientError:
        return CkanClientError(
            f"Timed out reaching '{_clean(url)}' after {self.timeout_seconds} seconds.",
            category="timeout",
            retryable=True,
            hint="Aumente o timeout.",
        )

    @staticmethod
    def _http_error(exc: HTTPError, url: str) -> CkanClientError:
        category, retryable = classify_http_status(exc.code)
        return CkanClientError(
            f"CKAN request failed ({exc.code}) for '{_clean(url)}'.",
            category=category,
            retryable=retryable,
            hint=(
                "Confira o conjunto e o recurso no portal; 403 costuma ser User-Agent "
                "ou arquivo que o portal anuncia e não publica."
            ),
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> CkanClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return CkanClientError(
            f"Could not reach '{_clean(url)}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


def _clean(url: str) -> str:
    """URL sem query string (a de um S3 assinado leva credencial nela)."""
    parts = urlsplit(url)
    return parts._replace(query="", fragment="").geturl()
