"""Datasource CKAN genérico: um CSV por recurso (ou por membro do zip).

``ckan_datasource_for(spec)`` devolve uma subclasse de :class:`CkanDataSource`
com a spec fixa, que o ``ApiDownloadSource`` instancia só com ``output_path``.

Convenções (as mesmas do ENANI e do MonitorAr):

- cada recurso vira um arquivo irmão no payload, ``<chave>__<arquivo>``;
  zip com vários CSV (``member_pattern`` ou, sem ele, todo ``.csv``/``.txt``)
  vira um arquivo por membro. Zip que traz o mesmo dado em csv, json e xml
  (INSS CAT) exige ``member_pattern`` ou cai no padrão de csv, que ignora o resto;
- tudo sai como texto, nomes de coluna como publicados (nome repetido no
  cabeçalho ganha o sufixo ``_duplicated_N`` do polars e entra no aviso);
- sem ``anos``, ``meses`` nem ``recursos``: chave com ``default_latest`` baixa
  só o período mais novo (recuando até 3 períodos se o mais novo falhar),
  chave com ``period_required`` recusa, as demais baixam todos os recursos;
- o ``datastore_search`` nunca é usado: baixa-se o ``resource.url``.
"""

from __future__ import annotations

import codecs
import csv
import re
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.arquivos.http_files import _sink_atomic, encoding_warnings, transcode_lines
from guaraci.ckan.client import (
    BROWSER_USER_AGENT,
    CkanClient,
    CkanClientError,
    CkanResource,
    resources_from_package,
)
from guaraci.ckan.datasets import CkanDataset, Period, resource_kind, resource_period, url_basename
from guaraci.core.datasource import DataSource
from guaraci.core.http import ApiClientError
from guaraci.fns.xlsx import XlsxError, iter_xlsx_rows

__all__ = ["CkanDataSource", "ckan_datasource_for", "select_resources"]

_FORMATS = ("csv", "parquet", "sqlite")
_FALLBACK_PERIODS = 3
_DUPLICATED = re.compile(r"_duplicated_\d+$")
_TEXT_MEMBER = re.compile(r"\.(csv|txt)$", re.IGNORECASE)
ProgressCallback = Callable[[Dict[str, object]], None]


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def _ints(values: Optional[Sequence[object]], label: str) -> List[int]:
    try:
        return [int(v) for v in values or ()]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{label}' deve ser lista de números: {exc}") from exc


def _matches(resource: CkanResource, wanted: Sequence[str]) -> bool:
    haystack = f"{resource.id} {resource.name} {resource.url}".lower()
    return any(w.strip().lower() in haystack for w in wanted if w.strip())


def select_resources(
    spec: CkanDataset,
    resources: Sequence[CkanResource],
    *,
    anos: Optional[Sequence[object]] = None,
    meses: Optional[Sequence[object]] = None,
    recursos: Optional[Sequence[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> Tuple[List[Tuple[CkanResource, Optional[Period]]], List[str], bool]:
    """Recursos escolhidos como ``(recurso, período)``, avisos e se vale o recuo "mais novo".

    Mais novo primeiro quando o recorte é por padrão (``default_latest``);
    senão, na ordem do portal.
    """
    include = re.compile(spec.resource_pattern, re.IGNORECASE) if spec.resource_pattern else None
    exclude = re.compile(spec.exclude_pattern, re.IGNORECASE) if spec.exclude_pattern else None
    candidates: List[Tuple[CkanResource, Optional[Period]]] = []
    seen = set()
    for resource in resources:
        if resource_kind(resource) != spec.file_format:
            continue
        text = f"{resource.name} {resource.url}"
        if include and not include.search(text):
            continue
        if exclude and exclude.search(text):
            continue
        if resource.url in seen:
            continue
        seen.add(resource.url)
        candidates.append((resource, resource_period(resource, spec.period_pattern)))

    warnings: List[str] = []
    wanted_years = set(_ints(anos, "anos"))
    wanted_months = set(_ints(meses, "meses"))
    if start_year is not None or end_year is not None:
        low = int(start_year) if start_year is not None else 0
        high = int(end_year) if end_year is not None else (low if start_year is not None else 9999)
        if high < low:
            raise ValueError("end_year must be greater than or equal to start_year.")
        window = set(range(max(low, 1900), min(high, 2200) + 1))
        wanted_years = wanted_years & window if wanted_years else window
    period_filter = bool(wanted_years or wanted_months)
    if recursos:
        candidates = [c for c in candidates if _matches(c[0], recursos)]

    if spec.period_required and not wanted_years:
        raise ValueError(
            f"'{spec.key}' tem arquivos grandes por período; informe 'anos' "
            "(e, se quiser, 'meses') para escolher o que baixar."
        )
    if period_filter:
        picked = [
            c
            for c in candidates
            if c[1] is not None
            and (not wanted_years or c[1][0] in wanted_years)
            and (not wanted_months or (c[1][1] is not None and c[1][1] in wanted_months))
        ]
        found_years = {c[1][0] for c in picked if c[1]}
        missing = sorted(set(_ints(anos, "anos")) - found_years)
        if picked and missing:
            warnings.append(f"Anos sem recurso em '{spec.key}': {missing}.")
        return _newest_first(picked) if spec.default_latest else picked, warnings, False

    if spec.default_latest and not recursos:
        dated = [c for c in candidates if c[1] is not None]
        if dated:
            return _newest_first(dated), warnings, True
    return candidates, warnings, False


def _newest_first(items):
    return sorted(items, key=lambda c: (c[1][0], c[1][1] or 0), reverse=True)


def _period_label(period: Optional[Period]) -> str:
    if period is None:
        return "sem período"
    return f"{period[0]}-{period[1]:02d}" if period[1] else str(period[0])


class CkanDataSource(DataSource):
    """Um conjunto CKAN como fonte: ver o docstring do módulo."""

    SPEC: Optional[CkanDataset] = None
    DEFAULT_TIMEOUT = CkanClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        spec: Optional[CkanDataset] = None,
        client: Optional[CkanClient] = None,
    ) -> None:
        selected = spec or self.SPEC
        if selected is None:
            raise ValueError("CkanDataSource needs a CkanDataset spec.")
        super().__init__(name=selected.key, output_path=output_path)
        self.spec = selected
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported file with polars.scan_*.")

    # -- descoberta -----------------------------------------------------------
    def _make_client(self, timeout: int) -> CkanClient:
        return CkanClient(
            self.spec.base_url,
            user_agent=BROWSER_USER_AGENT if self.spec.browser_user_agent else None,
            timeout_seconds=timeout,
        )

    def list_resources(self, client: CkanClient) -> List[CkanResource]:
        found: List[CkanResource] = []
        for package_id in self.spec.package_ids:
            found.extend(client.resources(package_id))
        if self.spec.package_query:
            start = 0
            while True:
                result = client.package_search(fq=self.spec.package_query, rows=1000, start=start)
                page = result.get("results") or []
                for package in page:
                    found.extend(resources_from_package(package))
                start += len(page)
                if not page or start >= int(result.get("count") or 0):
                    break
        return found

    # -- download ---------------------------------------------------------------
    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        anos: Optional[Sequence[object]] = None,
        meses: Optional[Sequence[object]] = None,
        recursos: Optional[Sequence[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or self._make_client(timeout)

        everything = self.list_resources(client)
        chosen, warnings, latest_mode = select_resources(
            self.spec,
            everything,
            anos=anos,
            meses=meses,
            recursos=recursos,
            start_year=start_year,
            end_year=end_year,
        )
        if not chosen:
            raise ValueError(
                f"Nenhum recurso {self.spec.file_format} de '{self.spec.key}' casa com o "
                f"pedido ({len(everything)} recursos no portal)."
            )
        groups = self._groups(chosen, latest_mode)
        total = sum(len(g) for g in groups) if not latest_mode else len(groups[0])
        isolate = total > 1 or latest_mode

        def emit(event: Dict[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({"source": self.name, "documents_total": total, **event})

        emit({"event": "download_start"})
        exported: List[str] = []
        used: set = set()
        downloaded = skipped_count = failed = 0
        periods: List[str] = []
        last_error: Optional[BaseException] = None
        done_group = False
        for group in groups:
            group_failed = 0
            for index, (resource, period) in enumerate(group, start=1):
                stem = self._stem(resource, used)
                ext = {"csv": ".csv", "zip": ".zip", "xlsx": ".xlsx"}[self.spec.file_format]
                # Com exportação o original leva ``.orig`` para não colidir com o CSV de saída.
                raw_path = base_dir / (f"{stem}.orig{ext}" if requested else f"{stem}{ext}")
                try:
                    skipped = (
                        raw_path.exists()
                        and resource.size is not None
                        and raw_path.stat().st_size == resource.size
                    )
                    if not skipped:

                        def on_bytes(written: int, _p=raw_path, _i=index, _r=resource) -> None:
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
                        exported.extend(
                            str(p)
                            for p in self._export(raw_path, base_dir, stem, requested, warnings)
                        )
                        if not keep_raw:
                            raw_path.unlink(missing_ok=True)
                    periods.append(_period_label(period))
                except (ApiClientError, ValueError, zipfile.BadZipFile, XlsxError) as exc:
                    if not isolate:
                        raise
                    last_error = exc
                    group_failed += 1
                    failed += 1
                    warnings.append(f"{resource.name or resource.id}: {exc}")
            if not latest_mode or group_failed < len(group):
                done_group = True
                break
        if latest_mode and not done_group and last_error is not None:
            raise last_error
        if not requested and not keep_raw:
            warnings.append(
                "Raw file kept as published; set output_format to also export UTF-8 "
                "csv, parquet or sqlite."
            )
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped_count,
            "failed_count": failed if not latest_mode or not done_group else 0,
            "output_dir": str(base_dir),
            "source_url": client.action_url("package_show", id=self.spec.package_ids[0])
            if self.spec.package_ids and hasattr(client, "action_url")
            else self.spec.base_url,
            "periods": periods,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    @staticmethod
    def _groups(chosen, latest_mode: bool):
        """Em modo "mais novo", um grupo por período (até 3); senão, um grupo só."""
        if not latest_mode:
            return [list(chosen)]
        groups: List[list] = []
        for item in chosen:
            if groups and groups[-1][0][1] == item[1]:
                groups[-1].append(item)
            else:
                groups.append([item])
        return groups[:_FALLBACK_PERIODS]

    def _stem(self, resource: CkanResource, used: set) -> str:
        base = url_basename(resource.url)
        base = base.rsplit(".", 1)[0] if "." in base else base
        label = _slug(base)
        if not label or label.lower() in {"download", "file"}:
            label = _slug(resource.name) or resource.id[:8] or "recurso"
        stem = f"{self.name}__{label}"
        candidate, counter = stem, 2
        while candidate in used:
            candidate, counter = f"{stem}_{counter}", counter + 1
        used.add(candidate)
        return candidate

    # -- exportação -------------------------------------------------------------
    def _export(
        self, raw_path: Path, base_dir: Path, stem: str, fmt: str, warnings: List[str]
    ) -> List[Path]:
        suffix = {"csv": ".csv", "parquet": ".parquet"}.get(fmt, ".sqlite")
        spec = self.spec
        outputs: List[Path] = []
        if spec.file_format == "xlsx":
            utf8 = base_dir / f"{stem}.utf8.tmp.csv"
            try:
                _xlsx_to_csv(raw_path, utf8, spec.sheet, spec.skip_rows)
                outputs.append(
                    self._sink(utf8, ",", base_dir / f"{stem}{suffix}", fmt, stem, warnings)
                )
            finally:
                utf8.unlink(missing_ok=True)
            return outputs
        if spec.file_format == "csv":
            utf8 = base_dir / f"{stem}.utf8.tmp.csv"
            try:
                with open(raw_path, "rb") as source:
                    self._to_utf8(source, utf8, raw_path.name, warnings)
                outputs.append(
                    self._sink(utf8, spec.separator, base_dir / f"{stem}{suffix}", fmt, stem, warnings)
                )
            finally:
                utf8.unlink(missing_ok=True)
            return outputs
        with zipfile.ZipFile(raw_path) as archive:
            pattern = re.compile(spec.member_pattern, re.IGNORECASE) if spec.member_pattern else None
            members = [
                m
                for m in archive.infolist()
                if not m.is_dir() and (pattern.search(m.filename) if pattern else _TEXT_MEMBER.search(m.filename))
            ]
            if not members:
                raise ValueError(f"Nenhum membro do zip {raw_path.name} casa com o padrão.")
            for member in members:
                name = stem if len(members) == 1 else f"{stem}__{_slug(Path(member.filename).stem)}"
                utf8 = base_dir / f"{name}.utf8.tmp.csv"
                try:
                    with archive.open(member) as source:
                        self._to_utf8(source, utf8, member.filename, warnings)
                    outputs.append(
                        self._sink(utf8, spec.separator, base_dir / f"{name}{suffix}", fmt, name, warnings)
                    )
                finally:
                    utf8.unlink(missing_ok=True)
        return outputs

    def _to_utf8(self, source, target: Path, label: str, warnings: List[str]) -> None:
        stats: Dict[str, int] = {}
        with open(target, "w", encoding="utf-8", newline="") as sink:
            if self.spec.encoding == "auto":
                encoding = transcode_lines(source, sink, stats)
            else:
                encoding = self.spec.encoding
                replaced = 0
                decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
                for block in iter(lambda: source.read(1 << 20), b""):
                    text = decoder.decode(block)
                    replaced += text.count("�")
                    sink.write(text)
                text = decoder.decode(b"", final=True)
                replaced += text.count("�")
                sink.write(text)
                stats["replaced"] = replaced
        warnings.extend(encoding_warnings(label, stats, encoding))

    def _sink(
        self, utf8: Path, separator: str, dest: Path, fmt: str, table: str, warnings: List[str]
    ) -> Path:
        frame = pl.scan_csv(utf8, separator=separator, infer_schema=False, quote_char='"')
        names = frame.collect_schema().names()
        stripped = {n: n.strip() for n in names if n != n.strip()}
        if stripped:
            frame = frame.rename(stripped)
            names = [stripped.get(n, n) for n in names]
        repeated = [n for n in names if _DUPLICATED.search(n)]
        if repeated:
            warnings.append(
                f"{dest.name}: o cabeçalho de origem repete nomes de coluna; as repetições "
                f"ficaram como {repeated} (sufixo do polars)."
            )
        return _sink_atomic(frame, dest, fmt, table, dest.name)


def _xlsx_to_csv(path: Path, target: Path, sheet: Optional[str], skip_rows: int) -> int:
    """Aba como CSV UTF-8 com ``skip_rows`` linhas de preâmbulo descartadas antes do cabeçalho."""
    header_width = 0
    count = 0
    with open(target, "w", encoding="utf-8", newline="") as sink:
        writer = csv.writer(sink, lineterminator="\n")
        rows = iter_xlsx_rows(path, sheet)
        for number, row in enumerate(rows):
            if number < skip_rows:
                continue
            if number == skip_rows:
                row = [name.strip() for name in row]
                header_width = len(row)
            else:
                if len(row) > header_width and any(row[header_width:]):
                    raise XlsxError(f"Row {number + 1} has data beyond the {header_width} header columns.")
                row = (row + [""] * header_width)[:header_width]
                count += 1
            writer.writerow(row)
    return count


def ckan_datasource_for(spec: CkanDataset) -> type:
    """Subclasse com a spec fixa, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    class_name = "".join(part.title() for part in spec.key.split("_")) + "DataSource"
    return type(class_name, (CkanDataSource,), {"SPEC": spec})
