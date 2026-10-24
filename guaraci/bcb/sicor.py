"""SICOR (Banco Central, Olinda OData v2): crédito rural por município e produto.

``https://olinda.bcb.gov.br/olinda/servico/SICOR/versao/v2/odata/`` publica 17
conjuntos de dados; aqui entram três: ``CusteioMunicipioProduto``,
``InvestMunicipioProduto`` e ``ComercRegiaoUFProduto``. Verificado ao vivo em
2026-10-23: ``AnoEmissao`` e ``MesEmissao`` são texto ('2024', '03'); o filtro
``$filter=AnoEmissao eq '2024' and MesEmissao eq '03'`` funciona, enquanto
``$skip`` (com ou sem ``$top``) devolve 500 "Erro desconhecido", e ``$top`` grande
com filtro de mês devolve o mês inteiro (36.483 linhas em InvestMunicipioProduto
de 2024-03). Por isso a paginação é por mês de emissão: uma requisição por
(ano, mês), sem ``$skip``. Mês sem linhas é pulado. Os valores saem como a API
publica (texto), inclusive as aspas dentro de ``nomeProduto``.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.gestao_publica.rest import (
    JsonApiClient,
    RowSpool,
    as_list,
    finalize_export,
    normalize_format,
    pause,
)

__all__ = [
    "SicorComercializacaoUfDataSource",
    "SicorCusteioMunicipioDataSource",
    "SicorInvestimentoMunicipioDataSource",
]

ProgressCallback = Callable[[Dict[str, object]], None]

DEFAULT_BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/SICOR/versao/v2/odata"
MIN_YEAR = 2013
#: ``$top`` acima do maior mês publicado (o serviço não aceita ``$skip``).
TOP = 1_000_000


class SicorDataSource(DataSource):
    """Base comum: subclasses fixam ``DATASET`` e ``ENTITY``."""

    DATASET = ""
    ENTITY = ""
    DEFAULT_TIMEOUT = 180
    MIN_YEAR = MIN_YEAR

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[JsonApiClient] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name=self.DATASET, output_path=output_path)
        self._client = client
        self._sleep = sleep

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    @staticmethod
    def month_filter(year: int, month: int) -> str:
        return f"AnoEmissao eq '{year}' and MesEmissao eq '{month:02d}'"

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
        meses: Optional[Sequence[object]] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < MIN_YEAR or last < first:
            raise ValueError(f"Intervalo de anos inválido ({first}-{last}); mínimo {MIN_YEAR}.")
        months = sorted({int(m) for m in as_list(meses)}) or list(range(1, 13))
        if any(m < 1 or m > 12 for m in months):
            raise ValueError("meses deve conter números de 1 a 12.")
        today = datetime.now()
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or JsonApiClient(
            api_base_url or DEFAULT_BASE_URL, timeout_seconds=timeout, label="SICOR"
        )
        slots = [
            (year, month)
            for year in range(first, last + 1)
            for month in months
            if (year, month) <= (today.year, today.month)
        ]
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": len(slots)})

        spool = RowSpool(base_dir, self.name)
        empty: List[str] = []
        try:
            for done, (year, month) in enumerate(slots, start=1):
                body = client.get_json(
                    self.ENTITY,
                    {"$format": "json", "$top": TOP, "$filter": self.month_filter(year, month)},
                )
                rows = (body.get("value") if isinstance(body, dict) else body) or []
                if not rows:
                    empty.append(f"{year}-{month:02d}")
                for row in rows:
                    spool.add(row)
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": len(slots), "files_completed": done,
                        "file_path": f"{year}-{month:02d}",
                    })
                pause(self._sleep, pause_ms)
        except BaseException:
            spool.discard()
            raise

        rows_total = spool.rows
        stem = f"{self.name}_{first}" if first == last else f"{self.name}_{first}_{last}"
        csv_path = spool.write_csv(base_dir / f"{stem}.csv")
        exported = finalize_export(csv_path, fmt, self.name)
        warnings: List[str] = []
        if empty:
            warnings.append(f"Sem linhas em {len(empty)} mês(es): {', '.join(empty[:12])}.")
        if rows_total == 0:
            warnings.append("Nenhuma linha retornada.")
        return {
            "documents_found": rows_total,
            "downloaded_count": len(slots) - len(empty),
            "skipped_count": len(empty),
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": f"{client.base_url}/{self.ENTITY}",
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows_total,
            "export_warning": " ".join(warnings) or None,
        }


class SicorCusteioMunicipioDataSource(SicorDataSource):
    DATASET = "bcb_sicor_custeio_municipio"
    ENTITY = "CusteioMunicipioProduto"


class SicorInvestimentoMunicipioDataSource(SicorDataSource):
    DATASET = "bcb_sicor_investimento_municipio"
    ENTITY = "InvestMunicipioProduto"


class SicorComercializacaoUfDataSource(SicorDataSource):
    DATASET = "bcb_sicor_comercializacao_uf"
    ENTITY = "ComercRegiaoUFProduto"
