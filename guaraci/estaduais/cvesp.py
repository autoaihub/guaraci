"""TabNet do CVE-SP (Centro de Vigilância Epidemiológica, Secretaria da Saúde de São Paulo).

O CVE-SP publica casos notificados de HIV, aids e sífilis num TabNet Win32 3.0
em ``tabnetcve.saude.sp.gov.br``. A página do formulário sai de
``deftohtm.exe`` e o POST vai para o ``tabcgi.exe`` apontado pela ``ACTION`` do
próprio formulário (relativa à raiz do host), por isso a URL do POST é lida do
HTML e não montada. O transporte é o de :mod:`guaraci.tabnet`.

Cada ``.def`` traz um único arquivo ``.dbf`` (a série inteira, até o ano
corrente) e o ano é uma dimensão da tabela. Um POST com ``Linha`` igual ao
município de residência no estado de São Paulo, ``Coluna`` igual ao ano de
notificação e o incremento ``Nº de Casos`` devolve a matriz município x ano.
O CSV de saída vira formato longo (um par município e ano por linha), com o
código IBGE de 6 dígitos e o nome do município como o TabNet publica; o ano
filtra as colunas da matriz, sem nova consulta. A coluna ``Total`` da matriz
é descartada.

Verificado ao vivo em 2026-10-23 (ver ``docs/sondagem_2026-10/``).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.datasus.frames import write_sqlite
from guaraci.tabnet import (
    TabnetClient,
    clean_header,
    parse_form,
    parse_prn,
)

__all__ = ["CvespCasosDataSource", "CvespSpec", "CVESP_SPECS", "cvesp_datasource_for"]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")
_MUNICIPIO_RE = re.compile(r"^(\d{6})\s+(.+)$")
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_COLUNA_INATIVA = "--Não-Ativa--"

DEFAULT_BASE_URL = "https://tabnetcve.saude.sp.gov.br/deftohtm.exe"
LINHA_MUNICIPIO_RESIDENCIA = "Mun_Resid_SP"


@dataclass(frozen=True)
class CvespSpec:
    dataset: str
    title: str
    #: Caminho do ``.def`` depois de ``deftohtm.exe?``.
    def_path: str
    #: Campo ``Coluna`` com o ano de notificação (o nome muda de um ``.def`` para outro).
    coluna: str
    #: Primeiro ano com casos, conferido ao vivo na matriz de 2026-10-23.
    min_year: int
    linha: str = LINHA_MUNICIPIO_RESIDENCIA


def _spec(key: str, nome: str, def_path: str, coluna: str, min_year: int) -> CvespSpec:
    return CvespSpec(
        dataset=key,
        title=f"CVE-SP TabNet - {nome} (casos por município de residência e ano de notificação)",
        def_path=def_path,
        coluna=coluna,
        min_year=min_year,
    )


#: Séries do TabNet do CVE-SP com município de residência. ``min_year`` foi lido
#: do cabeçalho da matriz em 2026-10-23.
CVESP_SPECS: Dict[str, CvespSpec] = {
    spec.dataset: spec
    for spec in (
        _spec("cvesp_sifilis_congenita", "Sífilis congênita", "cvetab/defs/crt/sifilisnet.def",
              "Ano_da_Notific", 2007),
        _spec("cvesp_sifilis_gestante", "Sífilis em gestante", "cvetab/defs/crt/sifges.def",
              "Ano_da_Notific", 2007),
        _spec("cvesp_sifilis_adquirida", "Sífilis adquirida", "cvetab/defs/crt/sifadq.def",
              "Ano_da_Notific", 2007),
        _spec("cvesp_hiv_gestante", "Gestante HIV", "cvetab/defs/crt/hivgestnet.def",
              "Ano_da_Notif", 2002),
        _spec("cvesp_aids_adulto", "Aids em adultos", "cvetab/defs/crt/aidsa.def",
              "Ano_da_Notific", 1980),
        _spec("cvesp_hiv", "Infecção pelo HIV", "cvetab/defs/crt/hiv.def",
              "Ano_da_Notific", 2000),
    )
}


def _split_municipio(label: str) -> List[str]:
    match = _MUNICIPIO_RE.match(label.strip())
    if not match:
        return ["", label.strip()]
    return [match.group(1), match.group(2).strip()]


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


class CvespCasosDataSource(DataSource):
    """Uma consulta ao ``.def`` do SPEC; o intervalo de anos filtra a matriz."""

    SPEC: CvespSpec
    DEFAULT_TIMEOUT = TabnetClient.DEFAULT_TIMEOUT

    def __init__(
        self, output_path: Optional[str] = None, *, client: Optional[TabnetClient] = None
    ) -> None:
        super().__init__(name=self.SPEC.dataset, output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

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
        page_url = f"{(base_url or DEFAULT_BASE_URL).strip()}?{spec.def_path}"

        form = parse_form(client.text(page_url))
        if not form.action:
            raise ValueError(f"Formulário do CVE-SP sem ACTION em '{page_url}'.")
        post_url = urljoin(page_url, form.action)
        arquivos = form.values("Arquivos")
        incrementos = form.values("Incremento")
        if not arquivos or not incrementos:
            raise ValueError(f"Formulário do CVE-SP sem arquivo ou incremento em '{page_url}'.")
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": 1}
            )
        body = form.build_body(
            linha=spec.linha,
            coluna=spec.coluna,
            incrementos=incrementos[:1],
            arquivos=arquivos[:1],
        )
        page = client.text(post_url, body)
        table = parse_prn(page)
        value_label = clean_header(
            next(o.label for o in form.selects["Incremento"] if o.value == incrementos[0])
        )

        year_columns = [
            (index, name)
            for index, name in enumerate(table.header)
            if index > 0 and _YEAR_RE.match(name)
        ]
        other = [n for i, n in enumerate(table.header) if i > 0 and not _YEAR_RE.match(n)]
        selected = [(i, n) for i, n in year_columns if first <= int(n) <= last]
        available = [int(n) for _, n in year_columns]

        raw_files: List[str] = []
        if keep_raw:
            raw_path = base_dir / f"{self.name}.raw.html"
            raw_path.write_text(page, encoding="utf-8")
            raw_files.append(str(raw_path))

        csv_path = base_dir / f"{self.name}.csv"
        rows_written = 0
        with open(csv_path, "w", encoding="utf-8", newline="") as sink:
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(["cod_ibge", "municipio", "ano", value_label])
            for row in table.rows:
                key = _split_municipio(row[0])
                for index, name in selected:
                    value = row[index] if index < len(row) else ""
                    writer.writerow([*key, name, value])
                    rows_written += 1

        warnings: List[str] = []
        if not year_columns:
            warnings.append("A matriz não trouxe colunas de ano.")
        elif not selected:
            warnings.append(
                f"Nenhum ano entre {first} e {last}; a série vai de {min(available)} a {max(available)}."
            )
        elif last > max(available):
            warnings.append(
                f"Ano(s) acima de {max(available)} ainda não publicado(s) no TabNet."
            )
        dropped = [n for n in other if n != "Total"]
        if dropped:
            warnings.append(f"Colunas fora do formato de ano descartadas: {dropped}.")

        exported = [str(csv_path)]
        if rows_written == 0:
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
                    raise ValueError("CVE-SP export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]

        if progress_callback is not None:
            progress_callback({
                "event": "file_progress", "source": self.name, "documents_total": 1,
                "files_completed": 1, "file_path": spec.def_path,
            })
        return {
            "documents_found": 1,
            "downloaded_count": 1 if rows_written else 0,
            "skipped_count": 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": page_url,
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "rows": rows_written,
            "raw_files": raw_files,
            "partial_years": [],
            "export_warning": " ".join(warnings) or None,
        }


def cvesp_datasource_for(spec: CvespSpec) -> type:
    """Classe de datasource para uma série, com o ``SPEC`` preso à classe."""
    return type(
        "Cvesp" + "".join(p.title() for p in spec.dataset.split("_")[1:]) + "DataSource",
        (CvespCasosDataSource,),
        {"SPEC": spec},
    )
