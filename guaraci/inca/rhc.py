"""Integrador RHC do INCA: base por caso dos Registros Hospitalares de Câncer.

Desde 2026 o Integrador RHC antigo (``irhc.inca.gov.br/RHCNet``) só redireciona
(301) para o RHCWeb (``app.inca.gov.br/RHCWeb``), um sistema JSF/PrimeFaces. O
Tabulador Hospitalar do RHCWeb abre a janela "Download", pública e sem login,
que entrega um zip por ano de diagnóstico, em DBF ou CSV, para uma unidade da
federação ou para "TODOS OS ESTADOS" (código ``-1``, o padrão aqui). O fluxo é
HTTP puro com sessão, nas requisições parciais (AJAX) do JSF:

1. GET na página do Tabulador abre a sessão e traz o ``javax.faces.ViewState``;
2. a escolha da base (``formDownloadTabulador:estado``) devolve os anos
   publicados;
3. "Gerar" (``btConsultar``) pede o arquivo do ano. A resposta já traz o botão
   ``btDownload`` quando o arquivo está pronto; senão traz um ``poll`` que se
   repete até o botão aparecer;
4. um POST comum com ``btDownload`` devolve o zip (``rhcAAAA.dbf``).

Os anos publicados vêm da própria página (1937 em diante). O DBF vem em cp1252 e
sai sem remoção de colunas, com os nomes como o INCA publica.

Atenção: o RHCWeb ainda está sendo carregado pelo INCA (atualizações de 2026 no
próprio Tabulador) e, na conferência de 03/11/2026, os anos recentes vinham com
poucas centenas de casos, bem abaixo do que o Integrador antigo publicava. A
conferência de volume fica a cargo de quem usa o arquivo.
"""

from __future__ import annotations

import re
import tempfile
import time
import zipfile
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
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

BASE_URL = "https://app.inca.gov.br/RHCWeb/"
PAGE_URL = BASE_URL + "pages/TabuladorHospitalar/consultar.xhtml?faces-redirect=true&initial=true"
MIN_YEAR = 1985
MAX_YEAR_FALLBACK = 2023
ENCODING = "cp1252"
SOURCE_URL = BASE_URL
ALL_STATES = "-1"

_FORM = "formDownloadTabulador"
_VIEW_STATE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')
_VIEW_STATE_UPDATE = re.compile(
    r'<update id="j_id1:javax\.faces\.ViewState:\d+"><!\[CDATA\[([^\]]+)\]\]>'
)
_FORM_ACTION = re.compile(r'id="formDownloadTabulador"[^>]*action="([^"]+)"')
_YEAR_BOX = re.compile(r'name="formDownloadTabulador:anos"[^>]*value="(\d+)"')
_POLL_ID = re.compile(r'id="(formDownloadTabulador:[^"]+)"[^>]*>\s*atualizarDownload')
_TAGS = re.compile(r"<[^>]+>|\s+")


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
        ALL_STATES,
    ),
}


def _flow_changed(detail: str) -> IncaClientError:
    return IncaClientError(
        f"Resposta inesperada do RHCWeb do INCA: {detail}",
        category="parse",
        retryable=False,
        hint=(
            "O fluxo de download do RHCWeb (app.inca.gov.br/RHCWeb, Tabulador "
            "Hospitalar, botão Download) pode ter mudado ou o serviço está fora do ar. "
            "Confira no navegador; o Integrador antigo (irhc.inca.gov.br/RHCNet) foi "
            "desativado e redireciona para o RHCWeb."
        ),
    )


def _text(body: str, limit: int = 160) -> str:
    return _TAGS.sub(" ", body).strip()[:limit]


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
        self._action: Optional[str] = None
        self._view_state: Optional[str] = None

    def _open(self, request: Request):
        request.add_header("User-Agent", self.USER_AGENT)
        try:
            return self._opener.open(request, timeout=self.timeout_seconds)
        except HTTPError as exc:
            raise self._http_error(exc, request.full_url) from exc
        except URLError as exc:
            raise self._url_error(exc, request.full_url) from exc

    def _open_page(self) -> None:
        """Abre a sessão e guarda a ação do formulário e o ViewState."""

        def send() -> str:
            with self._open(Request(PAGE_URL)) as response:
                return response.read().decode("utf-8", errors="replace")

        html = request_with_retry(send, max_attempts=self.max_attempts)
        action = _FORM_ACTION.search(html)
        states = _VIEW_STATE.findall(html)
        if not action or not states:
            raise _flow_changed(f"a página do Tabulador não traz o formulário de download ({_text(html)!r}).")
        self._action = urljoin(BASE_URL, action.group(1))
        self._view_state = states[-1]

    def _ajax(self, fields: Dict[str, str]) -> str:
        """POST parcial do JSF; guarda o ViewState novo e devolve o XML."""
        form = urlencode({
            "javax.faces.partial.ajax": "true",
            _FORM: _FORM,
            "javax.faces.ViewState": self._view_state or "",
            **fields,
        }).encode("utf-8")

        def send() -> str:
            request = Request(self._action or "", data=form, method="POST")
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            request.add_header("Faces-Request", "partial/ajax")
            request.add_header("X-Requested-With", "XMLHttpRequest")
            with self._open(request) as response:
                return response.read().decode("utf-8", errors="replace")

        body = request_with_retry(send, max_attempts=self.max_attempts)
        if "<partial-response" not in body:
            raise _flow_changed(f"{_text(body)!r}.")
        state = _VIEW_STATE_UPDATE.search(body)
        if state:
            self._view_state = state.group(1)
        return body

    def available_years(self, local: str = ALL_STATES) -> List[int]:
        """Anos publicados para a base ``local`` (código da UF ou ``-1``)."""
        self._open_page()
        return self._select_base(local)

    def _select_base(self, local: str) -> List[int]:
        body = self._ajax({
            "javax.faces.source": f"{_FORM}:estado",
            "javax.faces.partial.execute": f"{_FORM}:estado",
            "javax.faces.partial.render": f"{_FORM}:panelAnos",
            "javax.faces.behavior.event": "change",
            "javax.faces.partial.event": "change",
            f"{_FORM}:estado": local,
        })
        return sorted({int(year) for year in _YEAR_BOX.findall(body)})

    def _generate(self, local: str, year: int) -> None:
        """Pede o arquivo e espera o botão ``btDownload`` aparecer."""
        deadline = time.monotonic() + self.max_wait_seconds
        body = self._ajax({
            "javax.faces.source": f"{_FORM}:btConsultar",
            "javax.faces.partial.execute": _FORM,
            "javax.faces.partial.render": _FORM,
            f"{_FORM}:btConsultar": f"{_FORM}:btConsultar",
            f"{_FORM}:estado": local,
            f"{_FORM}:anos": str(year),
            f"{_FORM}:formato": "DBF",
        })
        while f"{_FORM}:btDownload" not in body:
            poll = _POLL_ID.search(body)
            if not poll:
                raise _flow_changed(f"o pedido de {year} não gerou o arquivo ({_text(body)!r}).")
            if time.monotonic() >= deadline:
                raise IncaClientError(
                    f"O RHCWeb não terminou de gerar {year} em {self.max_wait_seconds}s.",
                    category="timeout",
                    retryable=True,
                    hint="Aumente o parâmetro timeout ou tente de novo mais tarde.",
                )
            self._sleep(self.poll_seconds)
            body = self._ajax({
                "javax.faces.source": poll.group(1),
                "javax.faces.partial.execute": "@none",
                "javax.faces.partial.render": _FORM,
                poll.group(1): poll.group(1),
            })

    def download(
        self,
        year: int,
        destination: Path,
        *,
        local: str = ALL_STATES,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        self._open_page()
        published = self._select_base(local)
        if published and year not in published:
            raise IncaClientError(
                f"O ano {year} não está publicado no RHCWeb ({published[0]}-{published[-1]}).",
                category="not_found",
                retryable=False,
                hint="Use um ano dentro da faixa publicada pelo INCA.",
            )
        self._generate(local, year)

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        form = urlencode({
            _FORM: _FORM,
            f"{_FORM}:btDownload": "",
            "javax.faces.ViewState": self._view_state or "",
        }).encode("utf-8")

        def fetch() -> int:
            written = 0
            request = Request(self._action or "", data=form, method="POST")
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            with self._open(request) as response, open(partial, "wb") as sink:
                content_type = response.headers.get("Content-Type") or ""
                if "zip" not in content_type and "octet-stream" not in content_type:
                    raise _flow_changed(
                        f"o download de {year} devolveu {content_type or 'conteúdo sem tipo'} no "
                        "lugar do zip."
                    )
                for block in iter(lambda: response.read(chunk_size), b""):
                    sink.write(block)
                    written += len(block)
                    if progress_callback is not None:
                        progress_callback(written)
            if not zipfile.is_zipfile(partial):
                raise IncaClientError(
                    f"O arquivo de {year} recebido ({written} bytes) não é um zip válido.",
                    category="incomplete",
                    retryable=True,
                    hint="Baixe de novo; se persistir, confira o RHCWeb no navegador.",
                )
            return written

        try:
            written = request_with_retry(fetch, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    @staticmethod
    def _http_error(exc: HTTPError, what: str) -> IncaClientError:
        category, retryable = classify_http_status(exc.code)
        return IncaClientError(
            f"Request failed ({exc.code}) for '{what}'.",
            category=category,
            retryable=retryable,
            hint="Confira o RHCWeb em app.inca.gov.br/RHCWeb.",
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
