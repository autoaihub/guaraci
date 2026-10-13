"""MonitorAr (MMA): qualidade do ar medida pelas redes estaduais.

O conjunto ``ar-puro-monitorar`` do portal ``dados.mma.gov.br`` (CKAN) publica
um zip por ano (2022 em diante) com um único CSV: uma linha por hora, estação e
item monitorado. As 19 colunas são ``no_fonte_dados, dh_medicao, nu_iqar,
nu_concentracao, st_situacao, cd_flag, ds_flag, st_situacao_iqar,
no_item_monitorado, cd_normalizado, id_estacao, cod_estacao, no_estacao,
nu_latitude, nu_longitude, st_estacao, id_municipio, no_municipio, sg_uf``.

Pontos que mudam o resultado se forem ignorados:

- o zip de 2025 tem 31,8 MB e o CSV interno 1,135 GB; a leitura é em fluxo
  (``zipfile.open`` com decodificador incremental), nunca em memória;
- verificado ao vivo em 2026-10-13: os quatro anos (2022-2025) têm as mesmas 19
  colunas e os trechos iniciais decodificam como UTF-8 (o plano supunha
  cp1252). Por segurança, a codificação é detectada no primeiro bloco, com
  cp1252 como reserva;
- ``nu_iqar`` fica vazio para itens meteorológicos;
- ``cd_normalizado`` é o código do item (por exemplo ``PRESS``), não a
  unidade; o CSV não tem coluna de unidade, que só consta no dicionário de
  dados em PDF, e por isso nenhuma é inventada aqui;
- ``dh_medicao`` vem como ``AAAA-MM-DD HH:MM:SS.000``.

Tudo sai como texto, com os nomes de coluna como publicados.
"""

from __future__ import annotations

import codecs
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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

__all__ = [
    "MIN_YEAR",
    "MonitorArClient",
    "MonitorArClientError",
    "MonitorArDataSource",
    "MonitorArResource",
]

MIN_YEAR = 2022
PACKAGE_ID = "ar-puro-monitorar"
ENCODING = "utf-8"
FALLBACK_ENCODING = "cp1252"
_FORMATS = ("csv", "parquet", "sqlite")
_YEAR_RE = re.compile(r"-\s*((?:19|20)\d{2})\s*$")
ProgressCallback = Callable[[Dict[str, object]], None]


class MonitorArClientError(ApiClientError):
    """Falha ao consultar ou baixar dados do MonitorAr."""


@dataclass(frozen=True)
class MonitorArResource:
    year: int
    name: str
    url: str
    size: Optional[int] = None


class MonitorArClient:
    DEFAULT_BASE_URL = "https://dados.mma.gov.br/api/3/action/"
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

    def package_url(self) -> str:
        return f"{self.base_url}package_show?" + urlencode({"id": PACKAGE_ID})

    def list_resources(self) -> List[MonitorArResource]:
        """Recursos de dado (um por ano), ordenados por ano; o PDF fica de fora."""
        url = self.package_url()

        def send() -> bytes:
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return response.read()
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc
            except TimeoutError as exc:
                raise self._timeout(url) from exc

        raw = request_with_retry(send, max_attempts=self.max_attempts)
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
            items = payload["result"]["resources"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MonitorArClientError(
                "MMA package_show returned an unexpected payload.",
                category="response_format",
                hint="Confira o conjunto 'ar-puro-monitorar' em dados.mma.gov.br.",
            ) from exc
        found: Dict[int, MonitorArResource] = {}
        for item in items:
            name = str(item.get("name") or "").strip()
            link = str(item.get("url") or "").strip()
            fmt = str(item.get("format") or "").lower()
            match = _YEAR_RE.search(name)
            if not match or not link or "pdf" in fmt or not link.lower().endswith(".zip"):
                continue
            size = item.get("size")
            year = int(match.group(1))
            found[year] = MonitorArResource(
                year=year,
                name=name,
                url=link,
                size=int(size) if isinstance(size, (int, float)) else None,
            )
        return [found[year] for year in sorted(found)]

    def remote_size(self, resource: MonitorArResource) -> Optional[int]:
        """Tamanho do zip por HEAD (o CKAN não informa e o servidor devolve
        ``Content-Range: bytes 0-N/TOTAL`` em vez de ``Content-Length``)."""
        request = Request(resource.url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                length = response.headers.get("Content-Length")
                if length and length.isdigit():
                    return int(length)
                match = re.search(r"/(\d+)\s*$", response.headers.get("Content-Range") or "")
                return int(match.group(1)) if match else None
        except (HTTPError, URLError, TimeoutError):
            return None

    def download(
        self,
        resource: MonitorArResource,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa o zip em fluxo, passando por um ``.part``."""
        url = resource.url
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
                raise self._timeout(url) from exc
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    def _timeout(self, url: str) -> MonitorArClientError:
        return MonitorArClientError(
            f"Timed out reaching '{url}' after {self.timeout_seconds} seconds.",
            category="timeout",
            retryable=True,
            hint="Aumente o timeout.",
        )

    @staticmethod
    def _http_error(exc: HTTPError, url: str) -> MonitorArClientError:
        category, retryable = classify_http_status(exc.code)
        return MonitorArClientError(
            f"MMA request failed ({exc.code}) for '{url}'.",
            category=category,
            retryable=retryable,
            hint="Confira o conjunto em https://dados.mma.gov.br/dataset/ar-puro-monitorar.",
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> MonitorArClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return MonitorArClientError(
            f"Could not reach '{url}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def _sniff_encoding(block: bytes) -> str:
    """UTF-8 se o primeiro bloco decodifica como tal, senão cp1252.

    Um bloco cortado no meio de um caractere de vários bytes ainda conta como
    UTF-8: só o fim incompleto é tolerado.
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    try:
        decoder.decode(block, final=False)
    except UnicodeDecodeError:
        return FALLBACK_ENCODING
    return ENCODING


def zip_to_utf8(zip_path: Path, target: Path, encoding: Optional[str] = None) -> int:
    """Copia o CSV de dentro do zip para ``target`` em UTF-8, em blocos.

    Sem ``encoding``, a codificação é detectada no primeiro bloco. Byte que a
    codificação não define vira o caractere de substituição em vez de abortar.
    Devolve os bytes lidos do CSV descompactado.
    """
    decoder = None
    total = 0
    with zipfile.ZipFile(zip_path) as archive:
        members = [i for i in archive.infolist() if i.filename.lower().endswith(".csv")]
        if not members:
            raise ValueError(f"No CSV found inside {zip_path.name}.")
        member = max(members, key=lambda i: i.file_size)
        with archive.open(member) as source, open(
            target, "w", encoding="utf-8", newline=""
        ) as sink:
            for block in iter(lambda: source.read(1 << 20), b""):
                total += len(block)
                if decoder is None:
                    block = block.removeprefix(codecs.BOM_UTF8)
                    chosen = encoding or _sniff_encoding(block)
                    decoder = codecs.getincrementaldecoder(chosen)(errors="replace")
                sink.write(decoder.decode(block))
            if decoder is not None:
                sink.write(decoder.decode(b"", final=True))
    return total


class MonitorArDataSource(DataSource):
    """MonitorAr: um CSV por ano, hora x estação x item monitorado."""

    DEFAULT_TIMEOUT = MonitorArClient.DEFAULT_TIMEOUT
    MIN_YEAR = MIN_YEAR

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[MonitorArClient] = None,
    ) -> None:
        super().__init__(name="mma_monitorar", output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError(
            "MonitorAr years reach GBs; read the exported file with polars.scan_*."
        )

    def download(
        self,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        low = int(start_year) if start_year is not None else MIN_YEAR
        if end_year is not None:
            high = int(end_year)
        else:
            high = low if start_year is not None else 9999
        if high < low:
            raise ValueError("end_year must be greater than or equal to start_year.")
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or MonitorArClient(base_url=api_base_url, timeout_seconds=timeout)

        resources = [r for r in client.list_resources() if low <= r.year <= high]
        if not resources:
            raise ValueError(f"No MonitorAr resource between {low} and {high}.")
        total = len(resources)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": total}
            )

        exported: List[str] = []
        downloaded = skipped = 0
        warnings: List[str] = []
        for index, resource in enumerate(resources, start=1):
            raw_path = base_dir / f"dados_monitorar_{resource.year}.zip"
            size = resource.size
            if size is None and raw_path.exists() and hasattr(client, "remote_size"):
                size = client.remote_size(resource)
            have = raw_path.exists() and size is not None and raw_path.stat().st_size == size
            if have:
                skipped += 1
            else:

                def on_bytes(
                    written: int, _path=raw_path, _index=index, _size=resource.size
                ) -> None:
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name,
                            "documents_total": total, "document_index": _index,
                            "file_path": str(_path), "file_bytes_downloaded": written,
                            "file_total_bytes": _size or 0,
                        })

                client.download(resource, raw_path, progress_callback=on_bytes)
                downloaded += 1
            if progress_callback is not None:
                progress_callback({
                    "event": "file_skipped" if have else "file_completed",
                    "source": self.name, "documents_total": total,
                    "document_index": index, "file_path": str(raw_path),
                })
            if requested:
                exported.append(str(self._export(raw_path, base_dir, resource.year, requested)))
                if not keep_raw:
                    raw_path.unlink(missing_ok=True)
        if not requested and not keep_raw:
            warnings.append(
                "Zip files kept as published (CSV inside); set output_format to "
                "also export UTF-8 csv, parquet or sqlite."
            )

        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": client.package_url(),
            "years": [r.year for r in resources],
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(self, raw_path: Path, base_dir: Path, year: int, fmt: str) -> Path:
        utf8 = base_dir / f"mma_monitorar_{year}.utf8.tmp.csv"
        try:
            zip_to_utf8(raw_path, utf8)
            frame = pl.scan_csv(utf8, infer_schema=False, quote_char='"')
            names = frame.collect_schema().names()
            clean = {n: n.strip() for n in names if n != n.strip()}
            if clean:
                frame = frame.rename(clean)
            stem = f"{self.name}_{year}"
            if fmt == "csv":
                dest = base_dir / f"{stem}.csv"
                frame.sink_csv(dest)
            elif fmt == "parquet":
                dest = base_dir / f"{stem}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(
                    frame, db_path=base_dir / f"{stem}.sqlite", table=self.name
                )
                if written is None:
                    raise ValueError(f"MonitorAr {year} has no rows to export to sqlite.")
                dest = written
            return dest
        finally:
            utf8.unlink(missing_ok=True)
