"""Integrador RHC do INCA: base por caso dos Registros Hospitalares de Câncer.

O Integrador publica, sem login nem captcha, um zip por ano de diagnóstico com
todos os estados (``local=todosho_sp``). O fluxo é HTTP puro com sessão:

1. POST em ``downloadTabWin!bases.action`` pede a geração do ano (a resposta
   abre a sessão ``JSESSIONID``) e devolve ``{'status':'1'}`` (gerando) ou
   ``{'status':'2'}`` (pronto), repetido até 2;
2. com o cookie ``downloadToken`` igual ao campo de mesmo nome do formulário
   (a hora do cliente em milissegundos), um GET no mesmo endereço devolve o
   zip, com ``rhcNN.dbf`` e ``rhcGeral.def``. Sem esse cookie o GET devolve a
   página HTML do formulário, não o zip.

Os anos publicados saem de ``selecionaDownloadTabWin.action`` (há lacunas, como
1987). O DBF vem em cp1252 e sai sem remoção de colunas, com os nomes como o INCA publica.
"""

from __future__ import annotations

import ast
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import polars as pl

from guaraci import __version__
from guaraci.arquivos.http_files import _normalize_format
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)
from guaraci.datasus.frames import write_frame

__all__ = [
    "BASE_URL",
    "INCA_SPECS",
    "MAX_YEAR_FALLBACK",
    "MIN_YEAR",
    "IncaClient",
    "IncaClientError",
    "IncaRhcDataSource",
    "datasource_for",
]

BASE_URL = "https://irhc.inca.gov.br/RHCNet/"
SESSION_URL = BASE_URL + "visualizaTabNetExterno.action"
YEARS_URL = BASE_URL + "selecionaDownloadTabWin.action"
BASES_URL = BASE_URL + "downloadTabWin!bases.action"
MIN_YEAR = 1985
MAX_YEAR_FALLBACK = 2023
ENCODING = "cp1252"
SOURCE_URL = SESSION_URL

_STATUS = re.compile(r"""['"]status['"]\s*:\s*['"]?(\d+)""")


class IncaClientError(ApiClientError):
    """Falha ao gerar ou baixar um arquivo do Integrador RHC."""


@dataclass(frozen=True)
class IncaSpec:
    key: str
    title: str
    local: str


INCA_SPECS: Dict[str, IncaSpec] = {
    "inca_rhc": IncaSpec(
        "inca_rhc",
        "INCA Registros Hospitalares de Câncer (base por caso, todos os estados)",
        "todosho_sp",
    ),
}


def parse_status(body: str) -> int:
    """Lê o ``status`` do JSON com aspas simples devolvido pelo POST."""
    match = _STATUS.search(body)
    if match:
        return int(match.group(1))
    try:
        return int(ast.literal_eval(body.strip())["status"])
    except Exception as exc:
        raise IncaClientError(
            f"Resposta inesperada do Integrador RHC: {body[:120]!r}",
            category="parse",
            retryable=False,
            hint="O fluxo de download do Integrador RHC pode ter mudado.",
        ) from exc


class IncaClient:
    DEFAULT_TIMEOUT = 600
    DEFAULT_WAIT = 600
    POLL_SECONDS = 3.0
    USER_AGENT = "Mozilla/5.0 (compatible; guaraci/" + __version__ + ")"

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_wait_seconds: int = DEFAULT_WAIT,
        poll_seconds: float = POLL_SECONDS,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_wait_seconds = max(1, int(max_wait_seconds))
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._jar))
        self._session_ready = False

    def _open(self, request: Request):
        request.add_header("User-Agent", self.USER_AGENT)
        try:
            return self._opener.open(request, timeout=self.timeout_seconds)
        except HTTPError as exc:
            raise self._http_error(exc, request.full_url) from exc
        except URLError as exc:
            raise self._url_error(exc, request.full_url) from exc

    def _ensure_session(self, local: str) -> None:
        if self._session_ready:
            return

        def send() -> None:
            with self._open(Request(SESSION_URL)) as response:
                response.read()
            # A página de anos fixa a base escolhida na sessão antes do POST.
            query = urlencode({"local": local, "unidFed": "", "anoPrimeiraConsulta": ""})
            with self._open(Request(YEARS_URL + "?" + query)) as response:
                response.read()

        request_with_retry(send, max_attempts=self.max_attempts)
        self._session_ready = True

    def _post_status(self, local: str, year: int, token: str) -> int:
        form = urlencode({
            "local": local,
            "unidFed": "",
            "anoPrimeiraConsulta": "",
            "downloadToken": token,
            "anosSelecionados": str(year),
            "arquivoDef": "true",
            "wwajax": "1",
            "wwresult": "0",
        }).encode("ascii")

        def send() -> int:
            request = Request(BASES_URL, data=form, method="POST")
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            request.add_header("X-Requested-With", "XMLHttpRequest")
            with self._open(request) as response:
                return parse_status(response.read().decode("utf-8", errors="replace"))

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(
        self,
        year: int,
        destination: Path,
        *,
        local: str = "todosho_sp",
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        self._ensure_session(local)
        token = str(int(time.time() * 1000))
        deadline = time.monotonic() + self.max_wait_seconds
        while self._post_status(local, year, token) != 2:
            if time.monotonic() >= deadline:
                raise IncaClientError(
                    f"O Integrador RHC não terminou de gerar {year} em {self.max_wait_seconds}s.",
                    category="timeout",
                    retryable=True,
                    hint="Aumente o parâmetro timeout ou tente de novo mais tarde.",
                )
            self._sleep(self.poll_seconds)

        self._set_token_cookie(token)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def fetch() -> int:
            written = 0
            with self._open(Request(BASES_URL)) as response, open(partial, "wb") as sink:
                if "text/html" in (response.headers.get("Content-Type") or ""):
                    raise IncaClientError(
                        f"O Integrador RHC devolveu HTML no lugar do zip de {year}.",
                        category="parse",
                        retryable=False,
                        hint="A sessão pode ter expirado ou o fluxo mudou.",
                    )
                for block in iter(lambda: response.read(chunk_size), b""):
                    sink.write(block)
                    written += len(block)
                    if progress_callback is not None:
                        progress_callback(written)
            return written

        try:
            written = request_with_retry(fetch, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    def _set_token_cookie(self, token: str) -> None:
        self._jar.set_cookie(Cookie(
            0, "downloadToken", token, None, False, "irhc.inca.gov.br", True, False,
            "/RHCNet", True, True, None, False, None, None, {},
        ))

    @staticmethod
    def _http_error(exc: HTTPError, what: str) -> IncaClientError:
        category, retryable = classify_http_status(exc.code)
        return IncaClientError(
            f"Request failed ({exc.code}) for '{what}'.",
            category=category,
            retryable=retryable,
            hint="Confira o Integrador RHC em irhc.inca.gov.br.",
        )

    @staticmethod
    def _url_error(exc: URLError, what: str) -> IncaClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return IncaClientError(
            f"Could not reach '{what}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


def _read_dbf(zip_path: Path, workdir: Path) -> pl.DataFrame:
    from guaraci.datasus.ftp import dbc

    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".dbf")]
        if not members:
            raise ValueError(f"{zip_path.name} não contém arquivo .dbf.")
        target = workdir / Path(members[0]).name
        with archive.open(members[0]) as src, open(target, "wb") as sink:
            for block in iter(lambda: src.read(1 << 20), b""):
                sink.write(block)
    return dbc.read(target, encoding=ENCODING)


class IncaRhcDataSource(DataSource):
    """Um zip por ano de diagnóstico; subclasses fixam ``DATASET``."""

    DATASET: str = ""
    MIN_YEAR = MIN_YEAR
    DEFAULT_TIMEOUT = IncaClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[IncaClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in INCA_SPECS:
            raise ValueError(f"Unknown INCA dataset '{key}'. Known: {sorted(INCA_SPECS)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = INCA_SPECS[key]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported file with polars.scan_*.")

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < MIN_YEAR or last < first:
            raise ValueError(f"Intervalo de anos inválido: {first}-{last} (desde {MIN_YEAR}).")
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or IncaClient(timeout_seconds=timeout, max_wait_seconds=timeout)
        years = list(range(first, last + 1))
        total = len(years)

        def emit(event: Dict[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({"source": self.name, "documents_total": total, **event})

        emit({"event": "download_start"})
        exported: List[str] = []
        warnings: List[str] = []
        downloaded = failed = 0
        for index, year in enumerate(years, start=1):
            raw_path = base_dir / f"{self.name}_{year}.zip"
            try:

                def on_bytes(written: int, _p=raw_path, _i=index) -> None:
                    emit({
                        "event": "file_progress", "document_index": _i,
                        "file_path": str(_p), "file_bytes_downloaded": written,
                    })

                client.download(year, raw_path, local=self.spec.local, progress_callback=on_bytes)
                downloaded += 1
                emit({"event": "file_completed", "document_index": index, "file_path": str(raw_path)})
                if requested:
                    exported.append(str(self._export(raw_path, base_dir, requested, year)))
                    if not keep_raw:
                        raw_path.unlink(missing_ok=True)
            except (ApiClientError, ValueError, zipfile.BadZipFile) as exc:
                if total == 1:
                    raise
                failed += 1
                warnings.append(f"{year}: {exc}")
        if not requested and not keep_raw:
            warnings.append(
                "Raw zip kept as published; set output_format to also export "
                "csv, parquet or sqlite."
            )
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": 0,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": SOURCE_URL,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(self, raw_path: Path, base_dir: Path, fmt: str, year: int) -> Path:
        name = f"{self.name}_{year}"
        with tempfile.TemporaryDirectory(prefix="guaraci_inca_") as tmp:
            frame = _read_dbf(raw_path, Path(tmp))
            if frame.is_empty():
                raise ValueError(f"{raw_path.name} has no rows to export.")
            dest = write_frame(frame, output_dir=base_dir, stem=name, format=fmt)
        if dest is None:
            raise ValueError(f"{raw_path.name} has no rows to export.")
        return dest


def datasource_for(key: str) -> type:
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (IncaRhcDataSource,), {"DATASET": key})
