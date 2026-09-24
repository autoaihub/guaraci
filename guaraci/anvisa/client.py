"""Cliente HTTP mínimo para os arquivos de dados abertos da ANVISA.

``https://dados.anvisa.gov.br/dados/`` é uma listagem de arquivos soltos, sem
API (``/api`` responde 404, verificado ao vivo em 2026-09-24). Cada arquivo
responde a ``HEAD`` com ``Content-Length`` e ``Last-Modified``, o que basta
para não baixar de novo o que não mudou. A ANVISA sobrescreve os arquivos a
cada atualização: histórico só existe se quem coleta guardar as cópias.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from guaraci import __version__
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)

__all__ = ["AnvisaClient", "AnvisaClientError", "RemoteFile"]


class AnvisaClientError(ApiClientError):
    """Falha ao consultar ou baixar um arquivo da ANVISA."""


@dataclass(frozen=True)
class RemoteFile:
    url: str
    size: Optional[int]
    last_modified: Optional[str]


class AnvisaClient:
    DEFAULT_BASE_URL = "https://dados.anvisa.gov.br/dados/"
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
    ) -> None:
        selected = (base_url or self.DEFAULT_BASE_URL).strip()
        self.base_url = selected if selected.endswith("/") else selected + "/"
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def url_for(self, filename: str) -> str:
        return self.base_url + quote(filename)

    def head(self, filename: str) -> RemoteFile:
        url = self.url_for(filename)

        def send() -> RemoteFile:
            request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    length = response.headers.get("Content-Length")
                    return RemoteFile(
                        url=url,
                        size=int(length) if length and length.isdigit() else None,
                        last_modified=response.headers.get("Last-Modified"),
                    )
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(
        self,
        filename: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa em fluxo para ``destination``, passando por um ``.part``."""
        url = self.url_for(filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def send() -> int:
            written = 0
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response, open(
                    partial, "wb"
                ) as sink:
                    for block in iter(lambda: response.read(chunk_size), b""):
                        sink.write(block)
                        written += len(block)
                        if progress_callback is not None:
                            progress_callback(written)
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc
            except TimeoutError as exc:
                raise AnvisaClientError(
                    f"Timed out downloading '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                    hint="Os arquivos do VigiMed passam de 100 MB; aumente o timeout.",
                ) from exc
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    @staticmethod
    def _http_error(exc: HTTPError, url: str) -> AnvisaClientError:
        category, retryable = classify_http_status(exc.code)
        return AnvisaClientError(
            f"ANVISA request failed ({exc.code}) for '{url}'.",
            category=category,
            retryable=retryable,
            hint="Confira se o arquivo ainda existe em https://dados.anvisa.gov.br/dados/.",
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> AnvisaClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return AnvisaClientError(
            f"Could not reach '{url}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )
