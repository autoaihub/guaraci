"""Indicadores do SIOPS (municípios e estados) pelo TabNet do DATASUS.

O SIOPS publica a série histórica de indicadores de receita e despesa em saúde
num TabNet Win32 3.0 em ``siops-asp.datasus.gov.br`` (IIS/6.0, só HTTP). O
servidor põe uma linha ``<!DOCTYPE>`` dentro dos cabeçalhos, por isso o
transporte é o cliente HTTP/1.0 cru de :mod:`guaraci.tabnet`.

Para cada ano sai um POST no próprio ``.def`` com todos os indicadores do
formulário (31, lidos do GET do ``.def``), linha por município ou UF e
``formato=prn``. Verificado ao vivo em 2026-10-13: municípios 2000-2025
(``indmun00.dbf`` a ``indmun25.dbf``; 2024 tem 5.558 municípios declarantes,
cerca de 5 s e 1,2 MB por ano) e estados 2002-2025 (``induf02.dbf`` a
``induf25.dbf``). Quem não declarou no ano não aparece.

Saída: um CSV UTF-8 com o ano, a chave geográfica (código IBGE de 6 dígitos e
nome do município; ou código, sigla e nome da UF) e os indicadores com os nomes
publicados. Valores como no TabNet: decimal com vírgula e ``...`` para dado
não disponível.
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
    clean_header,
    parse_form,
    parse_prn,
)

__all__ = [
    "SiopsIndicadoresDataSource",
    "SiopsIndicadoresEstadosDataSource",
    "SiopsIndicadoresMunicipiosDataSource",
    "SiopsSpec",
]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")
_MUNICIPIO_RE = re.compile(r"^(\d{6})\s+(.+)$")
_COLUNA_INATIVA = "--Não-Ativa--"
#: Trecho da página de erro quando o .dbf do ano não tem o campo pedido.
_MISSING_FIELD = "nao encontrado"

#: Nome da UF como o SIOPS publica -> (código IBGE, sigla).
UF_POR_NOME: Dict[str, Tuple[str, str]] = {
    "Rondônia": ("11", "RO"), "Acre": ("12", "AC"), "Amazonas": ("13", "AM"),
    "Roraima": ("14", "RR"), "Pará": ("15", "PA"), "Amapá": ("16", "AP"),
    "Tocantins": ("17", "TO"), "Maranhão": ("21", "MA"), "Piauí": ("22", "PI"),
    "Ceará": ("23", "CE"), "Rio Grande do Norte": ("24", "RN"), "Paraíba": ("25", "PB"),
    "Pernambuco": ("26", "PE"), "Alagoas": ("27", "AL"), "Sergipe": ("28", "SE"),
    "Bahia": ("29", "BA"), "Minas Gerais": ("31", "MG"), "Espírito Santo": ("32", "ES"),
    "Rio de Janeiro": ("33", "RJ"), "São Paulo": ("35", "SP"), "Paraná": ("41", "PR"),
    "Santa Catarina": ("42", "SC"), "Rio Grande do Sul": ("43", "RS"),
    "Mato Grosso do Sul": ("50", "MS"), "Mato Grosso": ("51", "MT"),
    "Goiás": ("52", "GO"), "Distrito Federal": ("53", "DF"),
}


@dataclass(frozen=True)
class SiopsSpec:
    dataset: str
    title: str
    def_path: str
    linha: str
    min_year: int
    key_columns: Tuple[str, ...]


def _split_municipio(label: str) -> List[str]:
    match = _MUNICIPIO_RE.match(label.strip())
    if not match:
        return ["", label.strip()]
    return [match.group(1), match.group(2).strip()]


def _split_uf(label: str) -> List[str]:
    name = label.strip()
    code, sigla = UF_POR_NOME.get(name, ("", ""))
    return [code, sigla, name]


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


class SiopsIndicadoresDataSource(DataSource):
    """Base: um POST por ano no ``.def`` do SPEC, com todos os indicadores."""

    SPEC: SiopsSpec
    DEFAULT_BASE_URL = "http://siops-asp.datasus.gov.br/CGI/tabcgi.exe"
    DEFAULT_TIMEOUT = TabnetClient.DEFAULT_TIMEOUT

    def __init__(
        self, output_path: Optional[str] = None, *, client: Optional[TabnetClient] = None
    ) -> None:
        super().__init__(name=self.SPEC.dataset, output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    def _split_key(self, label: str) -> List[str]:
        raise NotImplementedError

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
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
        fmt = _normalize_format(output_format) or "csv"
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or TabnetClient(timeout_seconds=timeout)
        url = f"{(base_url or self.DEFAULT_BASE_URL).strip()}?{spec.def_path}"

        form = parse_form(client.text(url))
        offered = form.years()
        incrementos = form.values("Incremento")
        if not offered or not incrementos:
            raise ValueError(f"Formulário do SIOPS sem anos ou indicadores em '{url}'.")

        years = list(range(first, last + 1))
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(years)}
            )

        csv_path = base_dir / f"{self.name}.csv"
        # Colunas fixas: todos os indicadores do formulário, na ordem dele. Ano
        # cujo .dbf não tem algum indicador deixa a coluna vazia.
        labels = {o.value: clean_header(o.label) for o in form.selects["Incremento"]}
        indicators = [labels[item] for item in incrementos]
        downloaded = failed = rows_written = 0
        failures: List[str] = []
        partial: List[str] = []
        raw_files: List[str] = []
        with open(csv_path, "w", encoding="utf-8", newline="") as sink:
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(["ano", *spec.key_columns, *indicators])
            for done, year in enumerate(years, start=1):
                arquivo = offered.get(year)
                if arquivo is None:
                    failed += 1
                    failures.append(f"{year}: ano não oferecido pelo formulário")
                    continue
                try:
                    page, table, missing = self._fetch_year(
                        client, url, form, arquivo, incrementos
                    )
                except (ApiClientError, TabnetNoTableError) as exc:
                    failed += 1
                    failures.append(f"{year}: {getattr(exc, 'message', exc)}")
                    continue
                if missing:
                    partial.append(f"{year} sem {len(missing)}")
                if keep_raw:
                    raw_path = base_dir / f"{self.name}_{year}.raw.html"
                    raw_path.write_text(page, encoding="utf-8")
                    raw_files.append(str(raw_path))
                position = {name: index for index, name in enumerate(table.header)}
                unknown = [name for name in table.header[1:] if name not in indicators]
                if unknown:
                    failed += 1
                    failures.append(f"{year}: colunas fora do formulário {unknown[:3]}")
                    continue
                downloaded += 1
                for row in table.rows:
                    values = [
                        row[position[name]] if name in position and position[name] < len(row) else ""
                        for name in indicators
                    ]
                    writer.writerow([str(year), *self._split_key(row[0]), *values])
                    rows_written += 1
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": len(years), "files_completed": done,
                        "file_path": f"{spec.def_path} {year}",
                    })

        exported = [str(csv_path)]
        if downloaded == 0:
            csv_path.unlink(missing_ok=True)
            exported = []
        elif fmt != "csv":
            frame = pl.scan_csv(csv_path, infer_schema=False)
            if fmt == "parquet":
                dest = base_dir / f"{self.name}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(
                    frame, db_path=base_dir / f"{self.name}.sqlite", table=self.name
                )
                if written is None:
                    raise ValueError("SIOPS export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]

        warnings: List[str] = []
        if failures:
            warnings.append(
                f"{failed} ano(s) falharam (primeiros: {'; '.join(failures[:3])})."
            )
        if rows_written == 0 and not failed:
            warnings.append("Nenhuma linha encontrada para os anos informados.")
        return {
            "documents_found": len(years),
            "downloaded_count": downloaded,
            "skipped_count": 0,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": url,
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "rows": rows_written,
            "raw_files": raw_files,
            "partial_years": partial,
            "export_warning": " ".join(warnings) or None,
        }

    def _fetch_year(
        self,
        client: TabnetClient,
        url: str,
        form: TabnetForm,
        arquivo: str,
        incrementos: Sequence[str],
    ) -> Tuple[str, PrnTable, List[str]]:
        """POST do ano com todos os indicadores; se o .dbf recusar algum, refaz sem eles.

        Os .dbf antigos não têm todos os campos (``Campo Incremento INDNUM1 nao
        encontrado em ...indmun00.dbf``) e o TabNet não diz qual opção caiu.
        Nesse caso cada indicador é testado sozinho com ``Linha=Ano`` (uma
        linha só, resposta pequena) e o POST final leva só os aceitos.
        """
        linha = self.SPEC.linha

        def post(items: Sequence[str], row: str) -> Tuple[str, PrnTable]:
            body = form.build_body(
                linha=row, coluna=_COLUNA_INATIVA, incrementos=items, arquivos=[arquivo]
            )
            page = client.text(url, body)
            return page, parse_prn(page)

        try:
            page, table = post(incrementos, linha)
            return page, table, []
        except TabnetNoTableError as exc:
            if _MISSING_FIELD not in str(exc).lower():
                raise
        accepted: List[str] = []
        for item in incrementos:
            try:
                post([item], "Ano")
            except TabnetNoTableError as exc:
                if _MISSING_FIELD not in str(exc).lower():
                    raise
                continue
            accepted.append(item)
        if not accepted:
            raise TabnetNoTableError(f"Nenhum indicador disponível em {arquivo}.")
        page, table = post(accepted, linha)
        return page, table, [item for item in incrementos if item not in accepted]


class SiopsIndicadoresMunicipiosDataSource(SiopsIndicadoresDataSource):
    SPEC = SiopsSpec(
        dataset="siops_indicadores_municipios",
        title="SIOPS - Indicadores Municipais (série histórica)",
        def_path="SIOPS/serhist/municipio/mIndicadores.def",
        linha="Munic-BR",
        min_year=2000,
        key_columns=("cod_ibge", "municipio"),
    )

    def _split_key(self, label: str) -> List[str]:
        return _split_municipio(label)


class SiopsIndicadoresEstadosDataSource(SiopsIndicadoresDataSource):
    SPEC = SiopsSpec(
        dataset="siops_indicadores_estados",
        title="SIOPS - Indicadores Estaduais (série histórica)",
        def_path="SIOPS/serhist/estado/indicuf.def",
        linha="UF",
        min_year=2002,
        key_columns=("cod_uf", "uf", "nome_uf"),
    )

    def _split_key(self, label: str) -> List[str]:
        return _split_uf(label)
