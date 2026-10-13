"""Cliente HTTP/1.0 cru, tolerante aos servidores TabNet antigos (IIS/6.0).

O ``tabcgi.exe`` do SIOPS responde ``HTTP/1.1 200`` com uma linha
``<!DOCTYPE ...>`` no meio do bloco de cabeçalhos. Clientes HTTP estritos
(httpx, ``http.client``) rejeitam a resposta. Aqui a requisição sai em
HTTP/1.0 com ``Connection: close`` e a resposta é lida inteira até o servidor
fechar o socket; no bloco de cabeçalhos, linha que não tem a forma
``Nome: valor`` é ignorada.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit

from guaraci import __version__
from guaraci.core.http import ApiClientError, classify_http_status, request_with_retry

__all__ = ["RawHttpResponse", "TabnetClient", "TabnetClientError", "parse_raw_response"]

#: Abre a conexão e devolve um objeto com ``sendall``, ``recv`` e ``close``.
ConnectFn = Callable[[str, int, bool, float], object]


class TabnetClientError(ApiClientError):
    """Falha ao consultar um TabNet."""


@dataclass
class RawHttpResponse:
    status: int
    reason: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def charset(self) -> str:
        content_type = self.headers.get("content-type", "")
        for part in content_type.split(";"):
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value.strip():
                return value.strip().strip('"')
        return "latin-1"


def parse_raw_response(raw: bytes) -> RawHttpResponse:
    """Separa status, cabeçalhos e corpo sem exigir cabeçalhos bem formados."""
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        head, sep, body = raw.partition(b"\n\n")
    lines = head.decode("latin-1").splitlines()
    if not lines or not lines[0].startswith("HTTP/"):
        raise TabnetClientError(
            "Resposta sem linha de status HTTP.", category="api_error", retryable=True
        )
    parts = lines[0].split(None, 2)
    try:
        status = int(parts[1])
    except (IndexError, ValueError) as exc:
        raise TabnetClientError(
            f"Linha de status inválida: {lines[0]!r}.", category="api_error", retryable=True
        ) from exc
    reason = parts[2] if len(parts) > 2 else ""
    headers: Dict[str, str] = {}
    for line in lines[1:]:
        name, colon, value = line.partition(":")
        # Linha estranha no bloco (o DOCTYPE do IIS/6.0) não é cabeçalho.
        if not colon or not name.strip() or " " in name.strip() or name.startswith("<"):
            continue
        headers[name.strip().lower()] = value.strip()
    return RawHttpResponse(status=status, reason=reason, headers=headers, body=body)


def _default_connect(host: str, port: int, use_tls: bool, timeout: float):
    sock = socket.create_connection((host, port), timeout=timeout)
    if use_tls:
        return ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    return sock


class TabnetClient:
    DEFAULT_TIMEOUT = 300
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
        connect: Optional[ConnectFn] = None,
    ) -> None:
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_attempts = max_attempts
        self._connect = connect or _default_connect

    def _exchange(self, url: str, body: Optional[bytes]) -> RawHttpResponse:
        parts = urlsplit(url)
        use_tls = parts.scheme == "https"
        host = parts.hostname or ""
        port = parts.port or (443 if use_tls else 80)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        method = "GET" if body is None else "POST"
        lines = [
            f"{method} {path} HTTP/1.0",
            f"Host: {host}",
            f"User-Agent: {self.USER_AGENT}",
            "Accept: text/html, */*",
            "Connection: close",
        ]
        if body is not None:
            lines.append("Content-Type: application/x-www-form-urlencoded")
            lines.append(f"Content-Length: {len(body)}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + (body or b"")
        try:
            conn = self._connect(host, port, use_tls, self.timeout_seconds)
        except socket.timeout as exc:
            raise TabnetClientError(
                f"Timed out connecting to '{host}'.", category="timeout", retryable=True
            ) from exc
        except OSError as exc:
            raise TabnetClientError(
                f"Could not reach '{host}': {exc}",
                category="connectivity",
                retryable=True,
                hint="Verifique acesso à internet, DNS e regras de proxy.",
            ) from exc
        chunks = []
        try:
            conn.sendall(request)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        except socket.timeout as exc:
            raise TabnetClientError(
                f"Timed out reading '{url}' after {self.timeout_seconds:.0f} seconds.",
                category="timeout",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise TabnetClientError(
                f"Connection to '{host}' failed: {exc}", category="connectivity", retryable=True
            ) from exc
        finally:
            try:
                conn.close()
            except OSError:
                pass
        response = parse_raw_response(b"".join(chunks))
        if response.status >= 400:
            category, retryable = classify_http_status(response.status)
            raise TabnetClientError(
                f"TabNet request failed ({response.status}) for '{url}'.",
                category=category,
                retryable=retryable,
                hint="Confira o caminho do .def e os campos do formulário.",
            )
        return response

    def request(self, url: str, body: Optional[bytes] = None) -> RawHttpResponse:
        """GET (``body=None``) ou POST de formulário, com retry nos erros transitórios."""
        return request_with_retry(
            lambda: self._exchange(url, body), max_attempts=self.max_attempts
        )

    def text(self, url: str, body: Optional[bytes] = None) -> str:
        response = self.request(url, body)
        return response.body.decode(response.charset, errors="replace")
