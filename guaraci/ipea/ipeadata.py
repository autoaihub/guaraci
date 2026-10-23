"""IPEADATA (OData v4): valores de séries selecionadas e catálogo de metadados.

API em ``http://www.ipeadata.gov.br/api/odata4/`` (só HTTP; sem chave). Verificado
ao vivo em 2026-10-23:

* ``Metadados`` devolve as 4.075 séries em uma resposta de 7,7 MB; ``$select``
  falha nesse recurso, então ele é lido inteiro;
* ``ValoresSerie(SERCODIGO='<código>')`` devolve todos os valores da série, com
  as colunas ``SERCODIGO, VALDATA, VALVALOR, NIVNOME, TERCODIGO``; código
  inexistente volta com ``value`` vazio e status 200;
* ``Territorios`` (3,3 MB) traz o nome de cada ``TERCODIGO`` por ``NIVNOME``;
* ``/Valores`` direto dá 404.

Tudo sai como texto: o JSON é lido com ``parse_float=str``, de modo que
``VALVALOR`` preserva os dígitos que a API publica. A lista padrão de séries e o
critério de seleção estão em :mod:`guaraci.ipea.series`.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.core.http import ApiClientError
from guaraci.gestao_publica.rest import (
    JsonApiClient,
    RowSpool,
    as_list,
    finalize_export,
    normalize_format,
    pause,
)
from guaraci.ipea.series import DEFAULT_SERIES_CODES

__all__ = ["IpeadataMetadadosDataSource", "IpeadataSeriesDataSource"]

ProgressCallback = Callable[[Dict[str, object]], None]

DEFAULT_BASE_URL = "http://www.ipeadata.gov.br/api/odata4"
_CODE = re.compile(r"^[A-Za-z0-9_]+$")


class _IpeadataBase(DataSource):
    DATASET = ""
    DEFAULT_TIMEOUT = 300

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

    def _make_client(self, timeout: int, api_base_url: Optional[str]) -> JsonApiClient:
        return self._client or JsonApiClient(
            api_base_url or DEFAULT_BASE_URL, timeout_seconds=timeout, label="IPEADATA"
        )

    @staticmethod
    def _values(body: object) -> List[Dict[str, object]]:
        if isinstance(body, dict):
            value = body.get("value")
            return list(value) if isinstance(value, list) else []
        return []


class IpeadataSeriesDataSource(_IpeadataBase):
    """Valores das séries pedidas (padrão: a lista congelada em ``series.py``) num só CSV."""

    DATASET = "ipeadata_series"

    def download(
        self,
        *,
        series: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = _IpeadataBase.DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        codes = list(dict.fromkeys(as_list(series))) or list(DEFAULT_SERIES_CODES)
        invalid = [code for code in codes if not _CODE.match(code)]
        if invalid:
            raise ValueError(f"Código(s) de série inválido(s): {', '.join(invalid)}.")
        client = self._make_client(timeout, api_base_url)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(codes)}
            )

        spool = RowSpool(base_dir, self.name)
        empty: List[str] = []
        failures: List[str] = []
        rows_by_series: Dict[str, int] = {}
        try:
            for done, code in enumerate(codes, start=1):
                try:
                    body = client.get_json(f"ValoresSerie(SERCODIGO='{code}')")
                except ApiClientError as exc:
                    failures.append(f"{code}: {exc.message}")
                    continue
                items = self._values(body)
                if not items:
                    empty.append(code)
                for item in items:
                    spool.add(item)
                rows_by_series[code] = len(items)
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": len(codes), "files_completed": done,
                        "file_path": code,
                    })
                pause(self._sleep, pause_ms)
        except BaseException:
            spool.discard()
            raise

        rows = spool.rows
        csv_path = spool.write_csv(base_dir / f"{self.name}.csv")
        exported = finalize_export(csv_path, fmt, self.name)
        warnings: List[str] = []
        if failures:
            warnings.append(f"{len(failures)} série(s) falharam: {'; '.join(failures[:3])}.")
        if empty:
            warnings.append(f"Série(s) sem valores (código inexistente?): {', '.join(empty)}.")
        return {
            "documents_found": len(codes),
            "downloaded_count": len(rows_by_series),
            "skipped_count": 0,
            "failed_count": len(failures),
            "output_dir": str(base_dir),
            "source_url": f"{client.base_url}/ValoresSerie",
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows,
            "rows_by_series": rows_by_series,
            "export_warning": " ".join(warnings) or None,
        }


class IpeadataMetadadosDataSource(_IpeadataBase):
    """Catálogo inteiro (``Metadados``) mais a tabela de territórios, dois CSV."""

    DATASET = "ipeadata_metadados"
    TABLES = (("Metadados", "ipeadata_metadados"), ("Territorios", "ipeadata_territorios"))

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = _IpeadataBase.DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._make_client(timeout, api_base_url)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(self.TABLES)}
            )
        exported: List[str] = []
        rows_by_table: Dict[str, int] = {}
        for done, (entity, stem) in enumerate(self.TABLES, start=1):
            spool = RowSpool(base_dir, stem)
            try:
                for item in self._values(client.get_json(entity)):
                    spool.add(item)
            except BaseException:
                spool.discard()
                raise
            rows_by_table[entity] = spool.rows
            csv_path = spool.write_csv(base_dir / f"{stem}.csv")
            exported.extend(finalize_export(csv_path, fmt, stem))
            if progress_callback is not None:
                progress_callback({
                    "event": "file_progress", "source": self.name,
                    "documents_total": len(self.TABLES), "files_completed": done,
                    "file_path": entity,
                })
        empty = [name for name, count in rows_by_table.items() if count == 0]
        return {
            "documents_found": len(self.TABLES),
            "downloaded_count": len(self.TABLES),
            "skipped_count": 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": client.base_url,
            "output_format": fmt,
            "exported_files": exported,
            "rows": sum(rows_by_table.values()),
            "rows_by_table": rows_by_table,
            "export_warning": f"Sem linhas: {', '.join(empty)}." if empty else None,
        }
