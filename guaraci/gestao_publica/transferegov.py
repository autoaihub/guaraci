"""Transferegov (PostgREST, sem chave): transferências especiais e fundo a fundo.

Cada base é uma API PostgREST em ``https://api.transferegov.gestao.gov.br/<base>/``.
A raiz devolve o OpenAPI (``Accept: application/openapi+json``), de onde saem as
tabelas (``paths``) e, em ``definitions``, as colunas e a chave primária de cada
uma. Verificado ao vivo em 2026-10-23: 14 tabelas em ``transferenciasespeciais`` e
21 em ``fundoafundo``.

Paginação por ``limit``/``offset``. O servidor limita cada resposta a 1.000
linhas, mesmo com ``limit`` maior (``content-range: 0-999/*``), e uma página além
do fim volta como ``[]``. Por isso o deslocamento avança pelo número de linhas
recebidas e a leitura só termina na página vazia. Sem ordem estável o PostgREST
repete e pula linhas entre páginas: a ordem é a chave primária quando a tabela
tem uma, e todas as colunas quando não tem (tabelas sem chave existem nas duas
bases). Tudo sai como texto, com os nomes de coluna como a API publica.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

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

__all__ = [
    "TransferegovFundoAFundoDataSource",
    "TransferegovTransferenciasEspeciaisDataSource",
]

ProgressCallback = Callable[[Dict[str, object]], None]

API_ROOT = "https://api.transferegov.gestao.gov.br"
OPENAPI_HEADERS = {"Accept": "application/openapi+json"}
#: Teto de linhas por resposta imposto pelo servidor.
PAGE_SIZE = 1000


class TransferegovDataSource(DataSource):
    """Base comum: subclasses fixam ``DATASET`` e ``BASE`` (nome da API)."""

    DATASET = ""
    BASE = ""
    DEFAULT_TIMEOUT = 120

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
        if self._client is not None:
            return self._client
        return JsonApiClient(
            api_base_url or f"{API_ROOT}/{self.BASE}",
            timeout_seconds=timeout,
            label="Transferegov",
        )

    @staticmethod
    def parse_openapi(spec: Dict[str, object]) -> Dict[str, Tuple[List[str], List[str]]]:
        """``{tabela: (colunas, chave primária)}`` a partir do OpenAPI do PostgREST."""
        definitions = spec.get("definitions") or {}
        tables: Dict[str, Tuple[List[str], List[str]]] = {}
        for path in (spec.get("paths") or {}):
            name = str(path).strip("/")
            if not name or "/" in name:
                continue  # raiz e rotas ``rpc/...``
            props = (definitions.get(name) or {}).get("properties") or {}
            columns = list(props)
            keys = [
                col for col, meta in props.items()
                if "Primary Key" in str((meta or {}).get("description", ""))
            ]
            tables[name] = (columns, keys)
        return tables

    @staticmethod
    def order_clause(columns: Sequence[str], keys: Sequence[str]) -> str:
        chosen = list(keys) or list(columns)
        return ",".join(f"{col}.asc" for col in chosen)

    def fetch_table(
        self, client: JsonApiClient, table: str, order: str, spool: RowSpool,
        *, pause_ms: int = 0,
    ) -> int:
        """Lê a tabela inteira, página a página, até a página vazia. Devolve as linhas lidas."""
        offset = 0
        params: Dict[str, object] = {"limit": PAGE_SIZE, "offset": 0}
        if order:
            params["order"] = order
        while True:
            params["offset"] = offset
            items = client.get_json(table, params)
            if not items:
                return offset
            for item in items:
                spool.add(item)
            offset += len(items)
            pause(self._sleep, pause_ms)

    def download(
        self,
        *,
        tabelas: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._make_client(timeout, api_base_url)

        available = self.parse_openapi(client.get_json("", None, headers=OPENAPI_HEADERS))
        if not available:
            raise ApiClientError(
                f"Transferegov '{self.BASE}' não listou nenhuma tabela no OpenAPI.",
                category="api_error",
                retryable=False,
            )
        wanted = as_list(tabelas)
        unknown = [name for name in wanted if name not in available]
        if unknown:
            raise ValueError(
                f"Tabela(s) desconhecida(s) em '{self.BASE}': {', '.join(unknown)}. "
                f"Disponíveis: {', '.join(available)}."
            )
        targets = wanted or list(available)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(targets)}
            )

        exported: List[str] = []
        rows_by_table: Dict[str, int] = {}
        failures: List[str] = []
        for done, table in enumerate(targets, start=1):
            columns, keys = available[table]
            spool = RowSpool(base_dir, f"{self.name}_{table}")
            try:
                rows = self.fetch_table(
                    client, table, self.order_clause(columns, keys), spool, pause_ms=pause_ms
                )
            except ApiClientError as exc:
                spool.discard()
                failures.append(f"{table}: {exc.message}")
                continue
            except BaseException:
                spool.discard()
                raise
            rows_by_table[table] = rows
            csv_path = spool.write_csv(base_dir / f"{self.name}_{table}.csv", columns or None)
            exported.extend(finalize_export(csv_path, fmt, f"{self.name}_{table}"))
            if progress_callback is not None:
                progress_callback({
                    "event": "file_progress", "source": self.name,
                    "documents_total": len(targets), "files_completed": done,
                    "file_path": table,
                })

        warnings: List[str] = []
        if failures:
            warnings.append(f"{len(failures)} tabela(s) falharam: {'; '.join(failures[:3])}.")
        empty = [name for name, count in rows_by_table.items() if count == 0]
        if empty:
            warnings.append(f"Tabela(s) sem linhas: {', '.join(empty)}.")
        return {
            "documents_found": len(targets),
            "downloaded_count": len(rows_by_table),
            "skipped_count": 0,
            "failed_count": len(failures),
            "output_dir": str(base_dir),
            "source_url": client.base_url,
            "output_format": fmt,
            "exported_files": exported,
            "rows": sum(rows_by_table.values()),
            "rows_by_table": rows_by_table,
            "export_warning": " ".join(warnings) or None,
        }


class TransferegovTransferenciasEspeciaisDataSource(TransferegovDataSource):
    DATASET = "transferegov_transferencias_especiais"
    BASE = "transferenciasespeciais"


class TransferegovFundoAFundoDataSource(TransferegovDataSource):
    DATASET = "transferegov_fundo_a_fundo"
    BASE = "fundoafundo"
