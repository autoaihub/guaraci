"""IQAR diário da cidade do Rio de Janeiro (Prefeitura, camada ArcGIS REST).

O catálogo ``data.rio`` (ArcGIS Hub) lista "Dados diários do Índice de
Qualidade do Ar - IQAR (2017 - 2024)" e aponta para a camada 1 do serviço
``Meio_Ambiente/Dados_diários_do_Índice_de_Qualidade_do_ar_IQAR`` em
``pgeo3.rio.rj.gov.br``. A camada é uma tabela sem geometria com os campos
``data``, ``estação`` (sigla), ``estacao_nome``, ``poluente``, ``classificação``,
``iqar`` e ``codnum`` (``maxRecordCount`` 2000). Verificado ao vivo em
2026-10-23: 23.241 registros, de 2017-01-01 a 2024-12-31; o Hub marca a última
edição em 2026-02, sem dado novo depois de 2024.

A coleta lê a camada inteira em páginas (``resultOffset``) ordenadas pelo OID.
Os nomes dos campos saem como o serviço publica. A data, que o ArcGIS entrega
em milissegundos desde a época Unix, vira ``AAAA-MM-DD`` (data UTC); os demais
valores seguem como texto.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Dict, List, Optional

import polars as pl

from guaraci.arcgis import ArcgisClient, epoch_ms_to_iso_date
from guaraci.core.datasource import DataSource
from guaraci.datasus.frames import write_sqlite

__all__ = ["RioIqarDiarioDataSource"]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")

DEFAULT_LAYER_URL = (
    "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Meio_Ambiente/"
    "Dados_di%C3%A1rios_do_%C3%8Dndice_de_Qualidade_do_ar_IQAR/MapServer/1"
)


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


class RioIqarDiarioDataSource(DataSource):
    DATASET = "rio_iqar_diario"
    TITLE = "Rio de Janeiro - Índice de Qualidade do Ar (IQAR) diário por estação e poluente"
    MIN_YEAR = 2017
    DEFAULT_TIMEOUT = ArcgisClient.DEFAULT_TIMEOUT

    def __init__(
        self, output_path: Optional[str] = None, *, client: Optional[ArcgisClient] = None
    ) -> None:
        super().__init__(name=self.DATASET, output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        layer_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = _normalize_format(output_format) or "csv"
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or ArcgisClient(timeout_seconds=timeout)
        url = (layer_url or DEFAULT_LAYER_URL).strip().rstrip("/")

        layer = client.layer(url)
        if not layer.fields:
            raise ValueError(f"Camada sem campos em '{url}'.")
        total = client.count(url)
        pages_total = -(-total // layer.max_record_count) if total else 0
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": pages_total}
            )
        date_fields = set(layer.date_fields())
        columns = layer.field_names
        csv_path = base_dir / f"{self.name}.csv"
        rows_written = 0
        with open(csv_path, "w", encoding="utf-8", newline="") as sink:
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(columns)
            for attributes in client.iter_features(url, layer):
                writer.writerow([
                    epoch_ms_to_iso_date(attributes.get(name))
                    if name in date_fields
                    else _text(attributes.get(name))
                    for name in columns
                ])
                rows_written += 1
                if progress_callback is not None and rows_written % layer.max_record_count == 0:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": pages_total,
                        "files_completed": rows_written // layer.max_record_count,
                        "file_path": url,
                    })

        warnings: List[str] = []
        if rows_written != total:
            warnings.append(
                f"A camada declarou {total} registros e a leitura trouxe {rows_written}."
            )
        exported = [str(csv_path)]
        if rows_written == 0:
            csv_path.unlink(missing_ok=True)
            exported = []
            warnings.append("Nenhum registro encontrado.")
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
                    raise ValueError("IQAR export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]
        return {
            "documents_found": pages_total,
            "downloaded_count": 1 if rows_written else 0,
            "skipped_count": 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": url,
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows_written,
            "export_warning": " ".join(warnings) or None,
        }


def _text(value: object) -> str:
    return "" if value is None else str(value)
