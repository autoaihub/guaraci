"""Séries municipais mensais de TabNets clássicos com um ``.dbf`` por mês.

SIAB (``siab/cnv/SIAB*br.def``, 1998-2015) e HIPERDIA (``hiperdia/cnv/hd<uf>.def``,
2002-2013) seguem o mesmo molde do SIOPS: o formulário do ``.def`` lista os
``.dbf`` em ``Arquivos`` (rótulos ``Dez/2015``) e os indicadores em
``Incremento``. Aqui cada ``.dbf`` mensal vira um POST com linha por município e
todos os incrementos. O CSV traz ``ano``, ``mes``, ``uf``, ``cod_ibge``,
``municipio`` e as medidas com os nomes que o prn publica. Valores como no
TabNet: ``-`` para zero e ``...`` para dado não disponível.

Os cadastros do SIAB (famílias e saneamento) têm um arquivo de dezembro por ano
até 2014 e arquivos mensais de jun a dez/2015; o ``mes`` é o do arquivo.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.core.http import ApiClientError
from guaraci.datasus.frames import write_sqlite
from guaraci.tabnet import (
    PrnTable,
    TabnetClient,
    TabnetForm,
    TabnetNoTableError,
    parse_form,
    parse_prn,
)

__all__ = ["TabnetMensalDataSource", "TabnetMensalSpec", "UF_POR_CODIGO", "split_municipio"]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")
_COLUNA_INATIVA = "--Não-Ativa--"
_MISSING_FIELD = "nao encontrado"
_MUNICIPIO_RE = re.compile(r"^(\d{6})\s+(.+)$")
_SUFIXO_UF_RE = re.compile(r"\s-\s([A-Z]{2})$")

#: Código IBGE da UF -> sigla.
UF_POR_CODIGO: Dict[str, str] = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
_CODIGO_POR_UF = {sigla: codigo for codigo, sigla in UF_POR_CODIGO.items()}


@dataclass(frozen=True)
class TabnetMensalSpec:
    dataset: str
    title: str
    #: Caminho do ``.def``; com ``{uf}`` há um ``.def`` por UF (HIPERDIA).
    def_path: str
    min_year: int
    max_year: int
    linha: str = "Município"
    per_uf_def: bool = False

    @property
    def key_columns(self) -> Tuple[str, ...]:
        return ("ano", "mes", "uf", "cod_ibge", "municipio")


def split_municipio(label: str) -> Tuple[str, str, str]:
    """(uf, código IBGE de 6 dígitos, nome); sem código para ``MUNICIPIO IGNORADO - UF``."""
    text = label.strip()
    match = _MUNICIPIO_RE.match(text)
    if match:
        return UF_POR_CODIGO.get(match.group(1)[:2], ""), match.group(1), match.group(2).strip()
    suffix = _SUFIXO_UF_RE.search(text)
    return (suffix.group(1) if suffix else ""), "", text


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def parse_ufs(value: Optional[object]) -> List[str]:
    """Siglas pedidas (lista ou texto separado por vírgula); vazio = todas."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    ufs = [str(item).strip().upper() for item in items if str(item).strip()]
    unknown = [uf for uf in ufs if uf not in _CODIGO_POR_UF]
    if unknown:
        raise ValueError(f"UF desconhecida: {unknown}. Use siglas como PR, SP, AC.")
    return ufs


class TabnetMensalDataSource(DataSource):
    """Um POST por ``.dbf`` mensal (e por UF, quando o ``.def`` é por UF)."""

    SPEC: TabnetMensalSpec
    DEFAULT_BASE_URL = "http://tabnet.datasus.gov.br/cgi/tabcgi.exe"
    FORM_URL = "http://tabnet.datasus.gov.br/cgi/deftohtm.exe"
    DEFAULT_TIMEOUT = TabnetClient.DEFAULT_TIMEOUT

    def __init__(
        self, output_path: Optional[str] = None, *, client: Optional[TabnetClient] = None
    ) -> None:
        super().__init__(name=self.SPEC.dataset, output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    def _def_paths(self, ufs: Sequence[str]) -> List[Tuple[str, str]]:
        """(UF do ``.def`` ou ``""``, caminho do ``.def``) na ordem de coleta."""
        spec = self.SPEC
        if not spec.per_uf_def:
            return [("", spec.def_path)]
        chosen = list(ufs) or sorted(_CODIGO_POR_UF)
        return [(uf, spec.def_path.format(uf=uf.lower())) for uf in chosen]

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
        uf: Optional[object] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        spec = self.SPEC
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < spec.min_year or last < first:
            raise ValueError(
                f"Invalid year range {first}-{last}; {spec.dataset} starts in {spec.min_year}."
            )
        ufs = parse_ufs(uf)
        fmt = _normalize_format(output_format) or "csv"
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or TabnetClient(timeout_seconds=timeout)
        post_base = (base_url or self.DEFAULT_BASE_URL).strip()
        form_base = post_base if base_url else self.FORM_URL
        units = self._def_paths(ufs)

        csv_path = base_dir / f"{self.name}.csv"
        downloaded = failed = rows_written = 0
        failures: List[str] = []
        partial: List[str] = []
        not_published: List[int] = []
        raw_files: List[str] = []
        measures: Optional[List[str]] = None
        total = 0
        writer = None
        sink = None
        try:
            for unit_uf, def_path in units:
                url = f"{post_base}?{def_path}"
                try:
                    form = parse_form(client.text(f"{form_base}?{def_path}"))
                except (ApiClientError, TabnetNoTableError, ValueError) as exc:
                    failed += 1
                    failures.append(f"{unit_uf or def_path}: {getattr(exc, 'message', exc)}")
                    continue
                periods = form.periods()
                incrementos = form.values("Incremento")
                if not periods or not incrementos:
                    failed += 1
                    failures.append(f"{unit_uf or def_path}: formulário sem períodos ou medidas")
                    continue
                wanted = sorted(p for p in periods if first <= p[0] <= last)
                if not wanted:
                    not_published.extend(y for y in range(first, last + 1) if y > max(periods)[0])
                    continue
                if measures is None:
                    try:
                        measures = self._probe_measures(
                            client, url, form, periods[max(periods)], incrementos
                        )
                    except (ApiClientError, TabnetNoTableError, ValueError) as exc:
                        failed += 1
                        failures.append(f"{unit_uf or def_path}: {getattr(exc, 'message', exc)}")
                        continue
                    sink = open(csv_path, "w", encoding="utf-8", newline="")
                    writer = csv.writer(sink, lineterminator="\n")
                    writer.writerow([*spec.key_columns, *measures])
                filtros = self._uf_filter(form, ufs) if not spec.per_uf_def else None
                total += len(wanted)
                for year, month in wanted:
                    arquivo = periods[(year, month)]
                    try:
                        page, table, missing = self._fetch(
                            client, url, form, arquivo, incrementos, filtros
                        )
                    except (ApiClientError, TabnetNoTableError, ValueError) as exc:
                        failed += 1
                        failures.append(
                            f"{unit_uf} {year}-{month:02d}: {getattr(exc, 'message', exc)}".strip()
                        )
                        continue
                    unknown = [name for name in table.header[1:] if name not in measures]
                    if unknown:
                        failed += 1
                        failures.append(f"{year}-{month:02d}: colunas fora do esperado {unknown[:3]}")
                        continue
                    if missing:
                        partial.append(f"{unit_uf} {year}-{month:02d} sem {len(missing)}".strip())
                    if keep_raw:
                        raw_path = base_dir / f"{self.name}_{unit_uf or 'br'}_{year}{month:02d}.raw.html"
                        raw_path.write_text(page, encoding="utf-8")
                        raw_files.append(str(raw_path))
                    position = {name: index for index, name in enumerate(table.header)}
                    downloaded += 1
                    for row in table.rows:
                        key_uf, code, name = split_municipio(row[0])
                        values = [
                            row[position[m]] if m in position and position[m] < len(row) else ""
                            for m in measures
                        ]
                        writer.writerow(
                            [str(year), str(month), key_uf or unit_uf, code, name, *values]
                        )
                        rows_written += 1
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name,
                            "documents_total": total, "files_completed": downloaded + failed,
                            "file_path": f"{def_path} {year}-{month:02d}",
                        })
        finally:
            if sink is not None:
                sink.close()

        exported = [str(csv_path)] if downloaded else []
        if sink is not None and not downloaded:
            csv_path.unlink(missing_ok=True)
        elif downloaded and fmt != "csv":
            frame = pl.scan_csv(csv_path, infer_schema=False)
            if fmt == "parquet":
                dest = base_dir / f"{self.name}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(
                    frame, db_path=base_dir / f"{self.name}.sqlite", table=self.name
                )
                if written is None:
                    raise ValueError("TabNet export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]

        warnings: List[str] = []
        if failures:
            warnings.append(f"{failed} consulta(s) falharam (primeiras: {'; '.join(failures[:3])}).")
        if partial:
            warnings.append(f"Meses parciais: {'; '.join(partial[:10])}.")
        if not_published:
            warnings.append(
                f"Ano(s) {', '.join(str(y) for y in sorted(set(not_published)))} "
                f"posterior(es) ao último publicado ({spec.max_year})."
            )
        if rows_written == 0 and not failed and not not_published:
            warnings.append("Nenhuma linha encontrada para os anos informados.")
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": 0,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": f"{post_base}?{units[0][1]}",
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "rows": rows_written,
            "raw_files": raw_files,
            "partial_years": partial,
            "export_warning": " ".join(warnings) or None,
        }

    def _uf_filter(self, form: TabnetForm, ufs: Sequence[str]) -> Optional[Dict[str, List[str]]]:
        """Categorias do campo de município que pertencem às UFs pedidas."""
        if not ufs:
            return None
        codes = {_CODIGO_POR_UF[u] for u in ufs}
        field_name = f"S{self.SPEC.linha}"
        values: List[str] = []
        for option in form.selects.get(field_name, []):
            uf_label, code, _ = split_municipio(option.label)
            if (code and code[:2] in codes) or (not code and uf_label in ufs):
                values.append(option.value)
        if not values:
            raise ValueError(f"Nenhum município das UFs {list(ufs)} no formulário.")
        return {field_name: values}

    def _probe_measures(
        self, client: TabnetClient, url: str, form: TabnetForm, arquivo: str,
        incrementos: Sequence[str],
    ) -> List[str]:
        """Nomes completos das medidas, lidos de uma tabela de uma linha (``Linha=Ano``)."""
        _, table, missing = self._fetch(client, url, form, arquivo, incrementos, None, "Ano")
        if missing:
            raise ValueError(f"O arquivo mais recente ({arquivo}) recusa {len(missing)} medida(s).")
        return table.header[1:]

    def _fetch(
        self,
        client: TabnetClient,
        url: str,
        form: TabnetForm,
        arquivo: str,
        incrementos: Sequence[str],
        filtros: Optional[Dict[str, List[str]]],
        linha: Optional[str] = None,
    ) -> Tuple[str, PrnTable, List[str]]:
        """POST do mês; se o .dbf recusar algum campo, testa cada medida e refaz só com as aceitas."""
        linha = linha or self.SPEC.linha

        def post(items: Sequence[str], row: str, flt) -> Tuple[str, PrnTable]:
            body = form.build_body(
                linha=row, coluna=_COLUNA_INATIVA, incrementos=items,
                arquivos=[arquivo], filtros=flt,
            )
            page = client.text(url, body)
            return page, parse_prn(page)

        try:
            page, table = post(incrementos, linha, filtros)
            return page, table, []
        except TabnetNoTableError as exc:
            if _MISSING_FIELD not in str(exc).lower():
                raise
        accepted: List[str] = []
        for item in incrementos:
            try:
                post([item], "Ano", None)
            except TabnetNoTableError as exc:
                if _MISSING_FIELD not in str(exc).lower():
                    raise
                continue
            accepted.append(item)
        if not accepted:
            raise TabnetNoTableError(f"Nenhuma medida disponível em {arquivo}.")
        page, table = post(accepted, linha, filtros)
        return page, table, [item for item in incrementos if item not in accepted]
