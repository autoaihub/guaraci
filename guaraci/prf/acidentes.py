"""Acidentes em rodovias federais da PRF (Boletim de Acidente de Trânsito).

A PRF publica, na página de dados abertos, um zip por ano e por agrupamento
(por ocorrência, ``datatran``; por pessoa, ``acidentes``), hospedado no Google
Drive. Os identificadores do Drive não seguem regra, então a descoberta lê a
página: cada linha da tabela traz o rótulo ("Documento CSV de Acidentes 2025
(Agrupados por pessoa)") e o link. O download usa
``https://drive.google.com/uc?export=download&id=<id>``, que atende sem login;
para arquivo grande o Drive devolve uma página de aviso de vírus, e o
formulário dela é seguido (``confirm``/``uuid``).

Os CSV vêm em latin-1, separados por ``;``, com ``NA`` para vazio e decimal com
vírgula. Tudo sai como texto, com os nomes de coluna como publicados. Os
arquivos "Todas as causas e tipos de acidentes" ficam de fora: são variantes
do agrupamento por pessoa.
"""

from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.arquivos.http_files import HttpFile, _normalize_format, _to_utf8
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)
from guaraci.datasus.frames import write_sqlite

__all__ = [
    "MIN_YEAR",
    "PAGE_URL",
    "PRF_SPECS",
    "PrfAcidentesDataSource",
    "PrfClient",
    "PrfClientError",
    "datasource_for",
    "parse_page",
]

PAGE_URL = (
    "https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf"
)
DRIVE_URL = "https://drive.google.com/uc?export=download&id="
MIN_YEAR = 2007

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_ANCHOR = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_DRIVE_ID = re.compile(r"drive\.google\.com/file/d/([\w-]+)")
_LABEL = re.compile(r"Acidentes\s+(\d{4})\s+\(Agrupados por (ocorrência|pessoa)\)\s*$")
_FORM = re.compile(r'<form[^>]*action="([^"]+)"[^>]*>(.*?)</form>', re.S)
_HIDDEN = re.compile(r'<input[^>]*type="hidden"[^>]*>', re.S)


class PrfClientError(ApiClientError):
    """Falha ao descobrir ou baixar um arquivo da PRF."""


@dataclass(frozen=True)
class PrfSpec:
    key: str
    kind: str  # "ocorrencia" | "pessoa"
    title: str
    file_spec: HttpFile


def _file_spec(key: str, title: str) -> HttpFile:
    return HttpFile(key, title, title, (), separator=";", encoding="latin-1")


PRF_SPECS: Dict[str, PrfSpec] = {
    "prf_acidentes_ocorrencias": PrfSpec(
        "prf_acidentes_ocorrencias",
        "ocorrencia",
        "PRF Acidentes em rodovias federais - Ocorrências",
        _file_spec("prf_acidentes_ocorrencias", "PRF Acidentes - Ocorrências"),
    ),
    "prf_acidentes_pessoas": PrfSpec(
        "prf_acidentes_pessoas",
        "pessoa",
        "PRF Acidentes em rodovias federais - Pessoas envolvidas",
        _file_spec("prf_acidentes_pessoas", "PRF Acidentes - Pessoas"),
    ),
}


def parse_page(page: str) -> Dict[Tuple[str, int], str]:
    """Mapa (``ocorrencia``|``pessoa``, ano) para o id do arquivo no Drive."""
    found: Dict[Tuple[str, int], str] = {}
    for row in _ROW.findall(page):
        cells = _CELL.findall(row)
        if len(cells) < 2:
            continue
        label = html.unescape(re.sub(r"<[^>]+>", "", cells[0])).strip()
        match = _LABEL.search(label)
        if not match:
            continue
        link_id = None
        for href, text in _ANCHOR.findall(row):
            drive = _DRIVE_ID.search(href)
            # Linhas trazem âncoras vazias herdadas de outras linhas: vale a que tem texto.
            if drive and re.sub(r"<[^>]+>", "", text).strip():
                link_id = drive.group(1)
                break
        if link_id:
            kind = "ocorrencia" if match.group(2) == "ocorrência" else "pessoa"
            found[(kind, int(match.group(1)))] = link_id
    return found


class PrfClient:
    DEFAULT_TIMEOUT = 600
    USER_AGENT = "Mozilla/5.0 (compatible; guaraci/" + __version__ + ")"

    def __init__(self, *, timeout_seconds: int = DEFAULT_TIMEOUT, max_attempts: int = 3) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def discover(self) -> Dict[Tuple[str, int], str]:
        def send() -> str:
            request = Request(PAGE_URL, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8", errors="replace")
            except HTTPError as exc:
                raise self._http_error(exc, PAGE_URL) from exc
            except URLError as exc:
                raise self._url_error(exc, PAGE_URL) from exc

        found = parse_page(request_with_retry(send, max_attempts=self.max_attempts))
        if not found:
            raise PrfClientError(
                "Nenhum arquivo de acidentes encontrado na página da PRF.",
                category="parse",
                retryable=False,
                hint="O layout da página de dados abertos da PRF pode ter mudado.",
            )
        return found

    def download(
        self,
        file_id: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def fetch(url: str):
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            return urlopen(request, timeout=self.timeout_seconds)

        def is_html(response) -> bool:
            return "text/html" in (response.headers.get("Content-Type") or "")

        def send() -> int:
            written = 0
            try:
                response = fetch(DRIVE_URL + file_id)
                if is_html(response):
                    # Aviso de vírus de arquivo grande: segue o formulário de confirmação.
                    body = response.read().decode("utf-8", errors="replace")
                    base = response.url
                    response.close()
                    response = fetch(self._confirm_url(body, base))
                with response, open(partial, "wb") as sink:
                    if is_html(response):
                        raise PrfClientError(
                            f"O Drive não liberou o arquivo '{file_id}' sem login.",
                            category="auth",
                            retryable=False,
                            hint="Confirme na página da PRF se o arquivo segue público.",
                        )
                    for block in iter(lambda: response.read(chunk_size), b""):
                        sink.write(block)
                        written += len(block)
                        if progress_callback is not None:
                            progress_callback(written)
            except HTTPError as exc:
                raise self._http_error(exc, file_id) from exc
            except URLError as exc:
                raise self._url_error(exc, file_id) from exc
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    @staticmethod
    def _confirm_url(body: str, base_url: str) -> str:
        form = _FORM.search(body)
        if not form:
            raise PrfClientError(
                "Página de confirmação do Drive sem formulário.",
                category="parse",
                retryable=False,
                hint="O Drive pode ter mudado o aviso de arquivo grande.",
            )
        fields: Dict[str, str] = {}
        for tag in _HIDDEN.findall(form.group(2)):
            name = re.search(r'name="([^"]+)"', tag)
            value = re.search(r'value="([^"]*)"', tag)
            if name:
                fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
        return urljoin(base_url, html.unescape(form.group(1))) + "?" + urlencode(fields)

    @staticmethod
    def _http_error(exc: HTTPError, what: str) -> PrfClientError:
        category, retryable = classify_http_status(exc.code)
        return PrfClientError(
            f"Request failed ({exc.code}) for '{what}'.",
            category=category,
            retryable=retryable,
            hint="Confira a página de dados abertos da PRF.",
        )

    @staticmethod
    def _url_error(exc: URLError, what: str) -> PrfClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return PrfClientError(
            f"Could not reach '{what}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


class PrfAcidentesDataSource(DataSource):
    """Um zip por ano; subclasses fixam ``DATASET`` (ver ``datasource_for``)."""

    DATASET: str = ""
    MIN_YEAR = MIN_YEAR
    DEFAULT_TIMEOUT = PrfClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[PrfClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in PRF_SPECS:
            raise ValueError(f"Unknown PRF dataset '{key}'. Known: {sorted(PRF_SPECS)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = PRF_SPECS[key]
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
        client = self._client or PrfClient(timeout_seconds=timeout)
        links = client.discover()
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
            file_id = links.get((self.spec.kind, year))
            if file_id is None:
                if total == 1:
                    raise ValueError(f"{year}: arquivo não publicado na página da PRF.")
                failed += 1
                warnings.append(f"{year}: arquivo não publicado na página da PRF.")
                continue
            raw_path = base_dir / f"{self.name}_{year}.zip"
            try:

                def on_bytes(written: int, _p=raw_path, _i=index) -> None:
                    emit({
                        "event": "file_progress", "document_index": _i,
                        "file_path": str(_p), "file_bytes_downloaded": written,
                    })

                client.download(file_id, raw_path, progress_callback=on_bytes)
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
                "Raw zip kept as published; set output_format to also export UTF-8 "
                "csv, parquet or sqlite."
            )
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": 0,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": PAGE_URL,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(self, raw_path: Path, base_dir: Path, fmt: str, year: int) -> Path:
        name = f"{self.name}_{year}"
        utf8 = base_dir / f"{name}.utf8.tmp.csv"
        try:
            _to_utf8(raw_path, self.spec.file_spec, utf8)
            frame = pl.scan_csv(utf8, separator=";", infer_schema=False, quote_char='"')
            names = frame.collect_schema().names()
            stripped = {n: n.strip() for n in names if n != n.strip()}
            if stripped:
                frame = frame.rename(stripped)
            if fmt == "csv":
                dest = base_dir / f"{name}.csv"
                frame.sink_csv(dest)
            elif fmt == "parquet":
                dest = base_dir / f"{name}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(frame, db_path=base_dir / f"{name}.sqlite", table=name)
                if written is None:
                    raise ValueError(f"{raw_path.name} has no rows to export to sqlite.")
                dest = written
            return dest
        finally:
            utf8.unlink(missing_ok=True)


def datasource_for(key: str) -> type:
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (PrfAcidentesDataSource,), {"DATASET": key})
