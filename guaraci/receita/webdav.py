"""Cliente mínimo do WebDAV público da Receita Federal (Nextcloud), só leitura.

O CNPJ aberto saiu do host ``dadosabertos.rfb.gov.br`` (hoje sem resposta) e
passou a um compartilhamento público de Nextcloud em
``https://arquivos.receitafederal.gov.br/index.php/s/<token>``. O mesmo token
abre o WebDAV em ``/public.php/webdav/``: usuário igual ao token e senha vazia
(Basic). Conferido ao vivo em 2026-10-23: ``PROPFIND`` com ``Depth: 1`` lista as
pastas ``AAAA-MM/`` (2023-05 em diante) e o ``GET`` entrega cada zip. O token
pode mudar a qualquer momento; por isso ele é parâmetro, e o 401 vira um erro
que diz isso.
"""

from __future__ import annotations

import base64
import http.client
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
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
    "DEFAULT_BASE_URL",
    "DEFAULT_TOKEN",
    "DavEntry",
    "ReceitaWebDavClient",
    "ReceitaWebDavError",
    "parse_propfind",
]

DEFAULT_BASE_URL = "https://arquivos.receitafederal.gov.br/public.php/webdav"
DEFAULT_TOKEN = "YggdBLfdninEJX9"
_DAV = "{DAV:}"


class ReceitaWebDavError(ApiClientError):
    """Falha ao listar ou baixar no WebDAV da Receita."""

    status: Optional[int] = None


@dataclass(frozen=True)
class DavEntry:
    name: str
    is_dir: bool
    size: Optional[int]
    last_modified: Optional[str]


class ReceitaWebDavClient:
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        *,
        token: str = DEFAULT_TOKEN,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
    ) -> None:
        self.token = (token or DEFAULT_TOKEN).strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def url(self, path: str) -> str:
        return f"{self.base_url}/{quote(path.strip('/'))}".rstrip("/")

    def _headers(self, extra: Optional[dict] = None) -> dict:
        raw = base64.b64encode(f"{self.token}:".encode("utf-8")).decode("ascii")
        headers = {"User-Agent": self.USER_AGENT, "Authorization": f"Basic {raw}"}
        headers.update(extra or {})
        return headers

    def _http_error(self, exc: HTTPError, url: str) -> ReceitaWebDavError:
        if exc.code in (401, 403):
            error = ReceitaWebDavError(
                f"A Receita recusou o token de compartilhamento ({exc.code}) em '{url}'.",
                category="configuration",
                retryable=False,
                hint=(
                    "O token do Nextcloud público pode ter mudado. Abra o link de dados "
                    "abertos do CNPJ em https://arquivos.receitafederal.gov.br/, copie o "
                    "código final do link de compartilhamento (/s/<token>) e passe-o no "
                    "parâmetro 'token'."
                ),
            )
        else:
            category, retryable = classify_http_status(exc.code)
            error = ReceitaWebDavError(
                f"Request failed ({exc.code}) for '{url}'.",
                category=category,
                retryable=retryable,
                hint="Confira se a competência e o arquivo existem no WebDAV da Receita.",
            )
        error.status = exc.code
        return error

    def _url_error(self, exc: URLError, url: str) -> ReceitaWebDavError:
        return ReceitaWebDavError(
            f"Could not reach '{url}': {exc.reason}",
            category="timeout" if is_timeout_reason(exc.reason) else "connectivity",
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )

    def _wrap(self, exc: BaseException, url: str) -> ApiClientError:
        if isinstance(exc, HTTPError):
            return self._http_error(exc, url)
        if isinstance(exc, URLError):
            return self._url_error(exc, url)
        error = transport_error(exc, url, self.timeout_seconds, ReceitaWebDavError)
        return error if error is not None else ReceitaWebDavError(str(exc), category="unknown")

    def list(self, path: str = "") -> List[DavEntry]:
        """Filhos diretos de ``path`` (``PROPFIND`` Depth 1), sem a própria pasta."""
        url = self.url(path)
        body = (
            b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
            b"<d:getcontentlength/><d:getlastmodified/><d:resourcetype/>"
            b"</d:prop></d:propfind>"
        )

        def send() -> bytes:
            request = Request(
                url,
                data=body,
                method="PROPFIND",
                headers=self._headers({"Depth": "1", "Content-Type": "application/xml"}),
            )
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return response.read()
            except (HTTPError, URLError, OSError, http.client.HTTPException) as exc:
                raise self._wrap(exc, url) from exc

        payload = request_with_retry(send, max_attempts=self.max_attempts)
        return parse_propfind(payload, self.base_url, path)

    def download(
        self,
        path: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa em fluxo para ``destination`` via ``.part``; valida o zip."""
        url = self.url(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def send() -> int:
            written = 0
            expected: Optional[int] = None
            request = Request(url, headers=self._headers())
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response, open(
                    partial, "wb"
                ) as sink:
                    length = response.headers.get("Content-Length")
                    expected = int(length) if length and length.isdigit() else None
                    for block in iter(lambda: response.read(chunk_size), b""):
                        sink.write(block)
                        written += len(block)
                        if progress_callback is not None:
                            progress_callback(written)
            except (HTTPError, URLError, http.client.HTTPException) as exc:
                raise self._wrap(exc, url) from exc
            except OSError as exc:
                if getattr(exc, "filename", None) is not None:
                    raise
                raise self._wrap(exc, url) from exc
            if expected is not None and written < expected:
                raise ReceitaWebDavError(
                    f"Download of '{url}' was truncated: {written} of {expected} bytes.",
                    category="incomplete",
                    retryable=True,
                    hint="O servidor encerrou a conexão antes do fim; tente de novo.",
                )
            if destination.suffix.lower() == ".zip" and not zipfile.is_zipfile(partial):
                raise ReceitaWebDavError(
                    f"'{url}' should be a zip but the {written} bytes received are not valid.",
                    category="incomplete",
                    retryable=True,
                    hint="Baixe de novo; se persistir, confira o arquivo no WebDAV da Receita.",
                )
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written


def parse_propfind(payload: bytes, base_url: str, path: str = "") -> List[DavEntry]:
    """Lê a resposta 207 do ``PROPFIND`` e devolve os filhos diretos."""
    root = ET.fromstring(payload)
    base_path = urlsplit(base_url).path.rstrip("/")
    own = f"{base_path}/{path.strip('/')}".rstrip("/")
    entries: List[DavEntry] = []
    for response in root.iter(f"{_DAV}response"):
        href = response.findtext(f"{_DAV}href") or ""
        href_path = unquote(urlsplit(href).path)
        if href_path.rstrip("/") == own:
            continue
        name = href_path.rstrip("/").rsplit("/", 1)[-1]
        size_text = response.findtext(f".//{_DAV}getcontentlength")
        modified = response.findtext(f".//{_DAV}getlastmodified")
        iso: Optional[str] = None
        if modified:
            try:
                iso = parsedate_to_datetime(modified).isoformat()
            except (TypeError, ValueError):
                iso = None
        entries.append(
            DavEntry(
                name=name,
                is_dir=response.find(f".//{_DAV}resourcetype/{_DAV}collection") is not None,
                size=int(size_text) if size_text and size_text.isdigit() else None,
                last_modified=iso,
            )
        )
    return entries
