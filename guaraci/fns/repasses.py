"""Repasses fundo a fundo do FNS (Fundo Nacional de Saúde), um arquivo por ano.

O portal ``https://portalfns.saude.gov.br/downloads/`` lista, entre outros, os
arquivos "REPASSE FAF COM POPULAÇÃO – <ano>", de 2002 em diante. Não há API nem
URL previsível: o nome muda de um ano para o outro (``-2021-1``, ``v4-2022``,
``REPASSE_FAF_COM_POPULACAO-2024``), parte dos links aponta direto para
``wp-content/uploads`` e parte passa por ``idg_download/<slug>/``, que
redireciona para o arquivo. Por isso a descoberta lê a página a cada execução.

Cada ano vira um CSV UTF-8 (vírgula), com todas as colunas como texto e os
nomes como o FNS publica, apenas com ``strip()``. O que muda entre os anos e
é resolvido aqui, sem alterar valor:

* separador: ``,`` com aspas (2020) ou ``;`` (2022 e 2024), achado na primeira linha;
* codificação: cp1252 nos arquivos antigos, UTF-8 com BOM nos recentes;
* formato: CSV até 2024, XLSX em 2025 e 2026 (lido por ``guaraci.fns.xlsx``).

O que continua diferente de um ano para outro fica para a camada prata:
decimal com vírgula nos CSV e com ponto no XLSX, data ``dd/mm/aaaa`` nuns e
``aaaa-mm-dd hh:mm:ss.ffffff`` noutros, e ``ESTRATÉGIA`` com e sem acento.
O arquivo do ano corrente é parcial (acumulado até o mês publicado).
"""

from __future__ import annotations

import codecs
import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)
from guaraci.datasus.frames import write_sqlite
from guaraci.fns.xlsx import xlsx_to_csv

__all__ = [
    "FNS_REPASSES_KEY",
    "FnsClient",
    "FnsClientError",
    "FnsRepassesDataSource",
    "RemoteFile",
    "discover_links",
]

FNS_REPASSES_KEY = "fns_repasses_fundo_a_fundo"
MIN_YEAR = 2002
ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")
_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


class FnsClientError(ApiClientError):
    """Falha ao consultar ou baixar um arquivo do portal do FNS."""


@dataclass(frozen=True)
class RemoteFile:
    url: str  # já depois dos redirecionamentos
    size: Optional[int]
    last_modified: Optional[str]


class FnsClient:
    LISTING_URL = "https://portalfns.saude.gov.br/downloads/"
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(self, *, listing_url: Optional[str] = None, timeout_seconds: int = DEFAULT_TIMEOUT,
                 max_attempts: int = 3) -> None:
        self.listing_url = (listing_url or self.LISTING_URL).strip()
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def listing_html(self) -> str:
        def send() -> str:
            request = Request(self.listing_url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8", errors="replace")
            except HTTPError as exc:
                raise self._http_error(exc, self.listing_url) from exc
            except URLError as exc:
                raise self._url_error(exc, self.listing_url) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def head(self, url: str) -> RemoteFile:
        def send() -> RemoteFile:
            request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    length = response.headers.get("Content-Length")
                    return RemoteFile(
                        url=response.geturl(),
                        size=int(length) if length and length.isdigit() else None,
                        last_modified=response.headers.get("Last-Modified"),
                    )
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(self, url: str, destination: Path, *,
                 progress_callback: Optional[Callable[[int], None]] = None,
                 chunk_size: int = 1 << 20) -> int:
        """Baixa em fluxo para ``destination``, passando por um ``.part``."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def send() -> int:
            written = 0
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response, open(partial, "wb") as sink:
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
                raise FnsClientError(
                    f"Timed out downloading '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout", retryable=True,
                    hint="O arquivo de 2025 passa de 16 MB; aumente o timeout.",
                ) from exc
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    @staticmethod
    def _http_error(exc: HTTPError, url: str) -> FnsClientError:
        category, retryable = classify_http_status(exc.code)
        return FnsClientError(
            f"FNS request failed ({exc.code}) for '{url}'.", category=category, retryable=retryable,
            hint="Confira o link em https://portalfns.saude.gov.br/downloads/.",
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> FnsClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return FnsClientError(
            f"Could not reach '{url}': {exc.reason}", category=category, retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


def discover_links(page: str, base_url: str = FnsClient.LISTING_URL) -> Dict[int, str]:
    """Ano -> URL (absoluta) dos arquivos "REPASSE FAF COM POPULAÇÃO" da página.

    Vale o texto da âncora, não o nome do arquivo, que muda de ano para ano.
    Se o ano aparecer em mais de um link, fica o primeiro da página.
    """
    links: Dict[int, str] = {}
    for attrs, inner in _ANCHOR.findall(page):
        text = " ".join(html.unescape(_TAGS.sub(" ", inner)).split())
        marker = text.upper().find("REPASSE FAF COM POPULA")
        href = _HREF.search(attrs)
        if marker < 0 or not href:
            continue
        year = _YEAR.search(text[marker:])
        if not year:
            continue
        url = urljoin(base_url, html.unescape(href.group(1) or href.group(2) or "").strip())
        links.setdefault(int(year.group(1)), url)
    return links


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def _detect_encoding(raw: Path) -> str:
    """UTF-8 (com ou sem BOM) se o arquivo inteiro decodifica como tal; senão cp1252."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        with open(raw, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                decoder.decode(block)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def _csv_to_utf8(raw: Path, target: Path) -> int:
    """Regrava o CSV do FNS como CSV UTF-8 com vírgula. Devolve as linhas de dados."""
    encoding = _detect_encoding(raw)
    count = 0
    with open(raw, "r", encoding=encoding, errors="replace", newline="") as source, \
            open(target, "w", encoding="utf-8", newline="") as sink:
        first = source.readline()
        delimiter = ";" if first.count(";") > first.count(",") else ","
        source.seek(0)
        reader = csv.reader(source, delimiter=delimiter, quotechar='"')
        writer = csv.writer(sink, lineterminator="\n")
        width = 0
        for number, row in enumerate(reader, start=1):
            if number == 1:
                row = [name.strip() for name in row]
                width = len(row)
            else:
                if not any(cell.strip() for cell in row):
                    continue
                if len(row) != width:
                    raise ValueError(
                        f"{raw.name}: line {reader.line_num} has {len(row)} fields, header has {width}."
                    )
                count += 1
            writer.writerow(row)
    return count


class FnsRepassesDataSource(DataSource):
    """Repasses fundo a fundo do FNS, um CSV por ano."""

    DATASET = FNS_REPASSES_KEY
    MIN_YEAR = MIN_YEAR
    DEFAULT_TIMEOUT = FnsClient.DEFAULT_TIMEOUT

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[FnsClient] = None) -> None:
        super().__init__(name=self.DATASET, output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported yearly files with polars.scan_*.")

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < MIN_YEAR or last < first:
            raise ValueError(f"Invalid year range {first}-{last}; the FNS series starts in {MIN_YEAR}.")
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or FnsClient(timeout_seconds=timeout)

        links = discover_links(client.listing_html(), client.listing_url)
        years = [y for y in range(first, last + 1) if y in links]
        missing = [y for y in range(first, last + 1) if y not in links]
        if not years:
            raise ValueError(
                f"No FNS repasses file listed for {first}-{last}. Listed years: {sorted(links)}."
            )
        warnings: List[str] = []
        if missing:
            warnings.append(f"Anos sem arquivo na página do FNS: {missing}.")

        total = len(years)
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": total})
        downloaded = skipped = 0
        exported: List[str] = []
        sizes: Dict[str, Optional[int]] = {}
        for index, year in enumerate(years, start=1):
            remote = client.head(links[year])
            extension = Path(urlsplit(remote.url).path).suffix.lower() or ".csv"
            raw_path = base_dir / f"{self.name}_{year}_original{extension}"
            sizes[str(year)] = remote.size
            same = raw_path.exists() and remote.size is not None and raw_path.stat().st_size == remote.size
            if not same:
                def on_bytes(written: int, _path=raw_path, _total=remote.size, _index=index) -> None:
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name, "documents_total": total,
                            "document_index": _index, "file_path": str(_path),
                            "file_bytes_downloaded": written, "file_total_bytes": _total or 0,
                        })

                client.download(remote.url, raw_path, progress_callback=on_bytes)
                downloaded += 1
            else:
                skipped += 1
            if progress_callback is not None:
                progress_callback({
                    "event": "file_skipped" if same else "file_completed", "source": self.name,
                    "documents_total": total, "document_index": index, "file_path": str(raw_path),
                })
            if requested:
                exported.append(str(self._export(raw_path, base_dir, year, requested)))
                if not keep_raw:
                    raw_path.unlink(missing_ok=True)
        if not requested and not keep_raw:
            warnings.append(
                "Arquivos mantidos como o FNS publica (CSV ou XLSX, codificação e separador variam "
                "por ano); defina output_format para exportar CSV UTF-8, parquet ou sqlite."
            )
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": client.listing_url,
            "source_sizes": sizes,
            "years": years,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(self, raw_path: Path, base_dir: Path, year: int, fmt: str) -> Path:
        stem = f"{self.name}_{year}"
        csv_path = base_dir / f"{stem}.csv"
        staging = csv_path if fmt == "csv" else base_dir / f"{stem}.utf8.tmp.csv"
        try:
            if raw_path.suffix.lower() == ".xlsx":
                xlsx_to_csv(raw_path, staging)
            else:
                _csv_to_utf8(raw_path, staging)
            if fmt == "csv":
                return csv_path
            frame = pl.scan_csv(staging, infer_schema=False)
            if fmt == "parquet":
                dest = base_dir / f"{stem}.parquet"
                frame.sink_parquet(dest)
                return dest
            written = write_sqlite(frame, db_path=base_dir / f"{stem}.sqlite", table=self.name)
            if written is None:
                raise ValueError(f"{raw_path.name} has no rows to export to sqlite.")
            return written
        finally:
            if fmt != "csv":
                staging.unlink(missing_ok=True)
