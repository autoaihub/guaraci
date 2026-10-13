"""Arquivos de dados abertos em URL fixa, publicados por HTTP.

Cada fonte aponta para um ou mais arquivos (CSV ou zip) cuja URL não muda; o
conteúdo é que é republicado por cima. O download faz ``HEAD`` antes para não
baixar de novo o que não mudou, grava em fluxo e, com ``output_format``,
converte para CSV UTF-8, Parquet ou SQLite sem carregar o arquivo na memória.
Todas as colunas ficam como texto e os nomes de coluna saem como publicados
(só ``strip``): número em formato pt-BR (``1.874,061``), negativos e brancos
passam intactos, pois interpretar é papel da camada prata, não do bronze.

Fontes:

- ``vigitel``: Vigitel 2006-2024 com peso de pós-estratificação (rake), um zip
  de 87 MB com um CSV de 577 MB. Colunas esparsas por ano são esperadas.
- ``ibama_agrotoxicos_comercializacao``: relatórios de comercialização de
  agrotóxicos do IBAMA (UTF-8 com BOM, ``;``, 33 colunas largas).
- ``farmacia_popular_indicadores``: 14 indicadores do Programa Farmácia
  Popular (bucket S3 do DEMAS), um zip com um CSV por indicador.
"""

from __future__ import annotations

import codecs
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
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
    "FARMACIA_INDICADORES",
    "HTTP_FILES",
    "HttpFile",
    "HttpFileClient",
    "HttpFileClientError",
    "HttpFileDataSource",
    "HttpResource",
    "RemoteFile",
    "datasource_for",
]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")
_SNIFF_BYTES = 1 << 20


class HttpFileClientError(ApiClientError):
    """Falha ao consultar ou baixar um arquivo de URL fixa."""


@dataclass(frozen=True)
class RemoteFile:
    url: str
    size: Optional[int]
    last_modified: Optional[str]
    etag: Optional[str] = None


class HttpFileClient:
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(self, *, timeout_seconds: int = DEFAULT_TIMEOUT, max_attempts: int = 3) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def head(self, url: str) -> RemoteFile:
        def send() -> RemoteFile:
            request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    length = response.headers.get("Content-Length")
                    return RemoteFile(
                        url=url,
                        size=int(length) if length and length.isdigit() else None,
                        last_modified=response.headers.get("Last-Modified"),
                        etag=response.headers.get("ETag"),
                    )
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(
        self,
        url: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa em fluxo para ``destination``, passando por um ``.part``."""
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
                raise HttpFileClientError(
                    f"Timed out downloading '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                    hint="Arquivos grandes (o zip do Vigitel tem 87 MB); aumente o timeout.",
                ) from exc
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            # BaseException: o cancelamento do job também limpa o .part.
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    @staticmethod
    def _http_error(exc: HTTPError, url: str) -> HttpFileClientError:
        category, retryable = classify_http_status(exc.code)
        return HttpFileClientError(
            f"Request failed ({exc.code}) for '{url}'.",
            category=category,
            retryable=retryable,
            hint="Confira se a URL do arquivo ainda existe no portal de origem.",
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> HttpFileClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return HttpFileClientError(
            f"Could not reach '{url}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


@dataclass(frozen=True)
class HttpResource:
    """Um arquivo remoto. ``code`` nomeia a saída quando a fonte tem vários."""

    code: str
    url: str
    title: str = ""


@dataclass(frozen=True)
class HttpFile:
    key: str
    title: str
    description: str
    resources: Tuple[HttpResource, ...]
    separator: str = ","
    # Membro do zip a ler; ``None`` aceita só um zip de membro único.
    member: Optional[str] = None
    # ``auto`` decide pelo conteúdo: BOM ou UTF-8 válido, senão cp1252.
    encoding: str = "auto"
    # Parâmetro que escolhe um subconjunto de ``resources`` pelo ``code``.
    selector: Optional[str] = None


_FARMACIA_BASE = "https://demas-dados-abertos.s3.amazonaws.com/csv/"
# Títulos do dataset mgdi-programa-farmacia-popular-do-brasil, raspados em 2026-10-13.
_FARMACIA = (
    ("atfpbcop", "Pessoas atendidas pelo PFPB na modalidade copagamento"),
    ("pfpbben", "Pessoas atendidas pelo PFPB"),
    ("pfpbbfam", "Pessoas atendidas pelo PFPB que são beneficiárias do Programa Bolsa Família"),
    (
        "pfpbbfcop",
        "Pessoas atendidas pelo PFPB com medicamentos e insumos de copagamento, "
        "beneficiárias do Bolsa Família",
    ),
    (
        "pfpbbfgrat",
        "Pessoas atendidas pelo PFPB com medicamentos gratuitos que são beneficiárias "
        "do Bolsa Família",
    ),
    ("pfpbdm", "Pessoas atendidas pelo PFPB com a aquisição de absorventes higiênicos"),
    ("pfpbdma", "Pessoas que foram atendidas pelo PFPB com a aquisição de absorventes higiênicos"),
    ("sntpba", "Pessoas atendidas pelo PFPB com medicamentos para asma"),
    ("sntpbcon", "Pessoas atendidas pelo PFPB com medicamentos para contracepção"),
    ("sntpbd", "Pessoas atendidas pelo PFPB com medicamentos para diabetes"),
    ("sntpbh", "Pessoas atendidas pelo PFPB com medicamentos para hipertensão"),
    ("sntpbih", "Pessoas atendidas pelo PFPB na modalidade gratuidade"),
    ("sntpbos", "Pessoas atendidas pelo PFPB com medicamentos para osteoporose"),
    ("sntpdhc", "Pessoas atendidas pelo PFPB com os medicamentos para hipertensão e diabetes"),
)
FARMACIA_INDICADORES: Tuple[str, ...] = tuple(code for code, _ in _FARMACIA)

HTTP_FILES: Dict[str, HttpFile] = {
    item.key: item
    for item in (
        HttpFile(
            "vigitel",
            "Vigitel 2006-2024 (inquérito telefônico, peso rake)",
            "Microdados do Vigitel (SVS/MS) de 2006 a 2024, sem 2022, com o peso de "
            "pós-estratificação. Colunas esparsas por ano.",
            (
                HttpResource(
                    "vigitel",
                    "https://svs.aids.gov.br/daent/cgdnt/vigitel/"
                    "vigitel-2006-2024-peso-rake-csv.zip",
                ),
            ),
            separator=",",
            member="vigitel-2006-2024-peso-rake_slabel.csv",
        ),
        HttpFile(
            "ibama_agrotoxicos_comercializacao",
            "IBAMA Agrotóxicos - Relatórios de comercialização",
            "Vendas semestrais de agrotóxicos por classe de uso e ingrediente ativo, "
            "em toneladas, com uma coluna de vendas por UF.",
            (
                HttpResource(
                    "relatorios_comercializacao_agrotoxicos",
                    "https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/"
                    "AGROTOXICOS/RelatoriosdeComercializacaodeAgrotoxicos/"
                    "relatorios_comercializacao_agrotoxicos.csv",
                ),
            ),
            separator=";",
        ),
        HttpFile(
            "farmacia_popular_indicadores",
            "Farmácia Popular - Indicadores",
            "Indicadores municipais do Programa Farmácia Popular do Brasil, um CSV por "
            "indicador (competência mensal).",
            tuple(
                HttpResource(code, f"{_FARMACIA_BASE}{code}.csv.zip", title)
                for code, title in _FARMACIA
            ),
            separator=",",
            selector="indicadores",
        ),
    )
}


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def _detect_encoding(sample: bytes, declared: str) -> str:
    if declared != "auto":
        return declared
    if sample.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    try:
        # final=False tolera o caractere partido no corte da amostra.
        decoder.decode(sample, final=False)
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


class _ZipMember:
    """Membro de zip que fecha o arquivo junto."""

    def __init__(self, archive: zipfile.ZipFile, name: str) -> None:
        self._archive = archive
        self._stream = archive.open(name)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self) -> "_ZipMember":
        return self

    def __exit__(self, *exc: object) -> None:
        self._stream.close()
        self._archive.close()


def _open_member(raw: Path, spec: HttpFile):
    """Abre os bytes do dado: o arquivo em si ou o membro do zip."""
    if not zipfile.is_zipfile(raw):
        return open(raw, "rb")
    archive = zipfile.ZipFile(raw)
    names = [n for n in archive.namelist() if not n.endswith("/")]
    if spec.member is not None:
        if spec.member not in names:
            archive.close()
            raise ValueError(f"Member '{spec.member}' not found in {raw.name}: {names}")
        chosen = spec.member
    elif len(names) == 1:
        chosen = names[0]
    else:
        archive.close()
        raise ValueError(f"{raw.name} has {len(names)} members; expected exactly one.")
    return _ZipMember(archive, chosen)


def _to_utf8(raw: Path, spec: HttpFile, target: Path) -> str:
    """Grava ``raw`` (ou seu membro do zip) em UTF-8, em blocos, sem BOM."""
    with _open_member(raw, spec) as source, open(target, "w", encoding="utf-8", newline="") as sink:
        first = source.read(_SNIFF_BYTES)
        encoding = _detect_encoding(first, spec.encoding)
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        block = first
        while block:
            sink.write(decoder.decode(block))
            block = source.read(1 << 20)
        sink.write(decoder.decode(b"", final=True))
    return encoding


class HttpFileDataSource(DataSource):
    """Fonte de arquivo(s) de URL fixa. Subclasses fixam ``DATASET`` (ver ``datasource_for``)."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = HttpFileClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[HttpFileClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in HTTP_FILES:
            raise ValueError(f"Unknown file dataset '{key}'. Known: {sorted(HTTP_FILES)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = HTTP_FILES[key]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported file with polars.scan_*.")

    def _select(self, indicadores: Optional[Sequence[str]]) -> List[HttpResource]:
        if not indicadores or not self.spec.selector:
            return list(self.spec.resources)
        wanted = [str(c).strip().lower() for c in indicadores]
        by_code = {r.code: r for r in self.spec.resources}
        unknown = [c for c in wanted if c not in by_code]
        if unknown:
            raise ValueError(f"Unknown indicadores {unknown}. Known: {sorted(by_code)}")
        return [by_code[c] for c in dict.fromkeys(wanted)]

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        indicadores: Optional[Sequence[str]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or HttpFileClient(timeout_seconds=timeout)
        resources = self._select(indicadores)
        multi = len(self.spec.resources) > 1
        total = len(resources)

        def emit(event: Dict[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({"source": self.name, "documents_total": total, **event})

        emit({"event": "download_start"})
        exported: List[str] = []
        warnings: List[str] = []
        downloaded = skipped_count = failed = 0
        remotes: List[RemoteFile] = []

        for index, resource in enumerate(resources, start=1):
            suffix = Path(resource.url).name
            raw_path = base_dir / (f"{self.name}__{suffix}" if multi else suffix)
            try:
                remote = client.head(resource.url)
                remotes.append(remote)
                skipped = (
                    raw_path.exists()
                    and remote.size is not None
                    and raw_path.stat().st_size == remote.size
                )
                if not skipped:

                    def on_bytes(written: int, _p=raw_path, _i=index, _r=remote) -> None:
                        emit({
                            "event": "file_progress", "document_index": _i,
                            "file_path": str(_p), "file_bytes_downloaded": written,
                            "file_total_bytes": _r.size or 0,
                        })

                    client.download(resource.url, raw_path, progress_callback=on_bytes)
                emit({
                    "event": "file_skipped" if skipped else "file_completed",
                    "document_index": index, "file_path": str(raw_path),
                })
                skipped_count += 1 if skipped else 0
                downloaded += 0 if skipped else 1
                if requested:
                    dest = self._export(raw_path, base_dir, requested, resource, multi)
                    exported.append(str(dest))
                    if not keep_raw:
                        raw_path.unlink(missing_ok=True)
            except (ApiClientError, ValueError, zipfile.BadZipFile) as exc:
                if not multi:
                    raise
                failed += 1
                warnings.append(f"{resource.code}: {exc}")

        if not requested and not keep_raw:
            warnings.append(
                "Raw file kept as published; set output_format to also export UTF-8 "
                "csv, parquet or sqlite."
            )
        first = remotes[0] if remotes else None
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped_count,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": first.url if first else None,
            "source_size": first.size if first else None,
            "source_last_modified": first.last_modified if first else None,
            "source_etag": first.etag if first else None,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(
        self, raw_path: Path, base_dir: Path, fmt: str, resource: HttpResource, multi: bool
    ) -> Path:
        name = f"{self.name}_{resource.code}" if multi else self.name
        utf8 = base_dir / f"{name}.utf8.tmp.csv"
        try:
            _to_utf8(raw_path, self.spec, utf8)
            frame = pl.scan_csv(
                utf8, separator=self.spec.separator, infer_schema=False, quote_char='"'
            )
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
    """Subclasse com ``DATASET`` fixo, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    spec = HTTP_FILES[key]
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (HttpFileDataSource,), {"DATASET": spec.key})
