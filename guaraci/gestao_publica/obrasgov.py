"""Obrasgov: projetos de investimento (Cadastro Integrado, Seges/MGI).

``https://api.obrasgov.gestao.gov.br/obrasgov/api/projeto-investimento`` pagina
por ``pagina`` (a partir de 0) e ``tamanhoDaPagina``. Verificado ao vivo em
2026-10-23: o host ``api-publica.obrasgov...`` dá 404; a página sai sem ordenação
declarada; ``totalElements`` repete o tamanho da página (100 com
``tamanhoDaPagina=100``), por isso não serve de contagem; tamanhos grandes
(1.000) estouram o tempo e uma página além do fim volta com ``content`` vazio.
A leitura vai então até a página vazia, descarta repetições por ``idUnico`` e
informa quantas houve. Campos aninhados (``executores``, ``repassadores``,
``fontesDeRecurso``, ``tipos`` e afins) viram texto JSON em uma coluna. Tudo sai
como texto, com os nomes de coluna como a API publica.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.gestao_publica.rest import (
    JsonApiClient,
    RowSpool,
    finalize_export,
    normalize_format,
    pause,
)

__all__ = ["ObrasgovProjetosDataSource"]

ProgressCallback = Callable[[Dict[str, object]], None]

DEFAULT_BASE_URL = "https://api.obrasgov.gestao.gov.br/obrasgov/api"
ENDPOINT = "projeto-investimento"
KEY = "idUnico"


class ObrasgovProjetosDataSource(DataSource):
    DATASET = "obrasgov_projetos_investimento"
    DEFAULT_TIMEOUT = 180
    PAGE_SIZE = 100

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

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        tamanho_pagina: int = PAGE_SIZE,
        max_paginas: Optional[int] = None,
        pause_ms: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or JsonApiClient(
            api_base_url or DEFAULT_BASE_URL, timeout_seconds=timeout, label="Obrasgov"
        )
        size = max(1, int(tamanho_pagina))
        limit = int(max_paginas) if max_paginas else None
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": 0})

        spool = RowSpool(base_dir, self.name)
        seen: set = set()
        duplicates = pages = 0
        try:
            page = 0
            while limit is None or page < limit:
                body = client.get_json(ENDPOINT, {"pagina": page, "tamanhoDaPagina": size})
                items = body.get("content") if isinstance(body, dict) else body
                if not items:
                    break
                pages += 1
                for item in items:
                    key = item.get(KEY)
                    if key is not None:
                        if key in seen:
                            duplicates += 1
                            continue
                        seen.add(key)
                    spool.add(item)
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": 0, "files_completed": pages,
                        "file_path": f"pagina={page}",
                    })
                page += 1
                pause(self._sleep, pause_ms)
        except BaseException:
            spool.discard()
            raise

        rows = spool.rows
        csv_path = spool.write_csv(base_dir / f"{self.name}.csv")
        exported = finalize_export(csv_path, fmt, self.name)
        warnings: List[str] = []
        if duplicates:
            warnings.append(
                f"{duplicates} projeto(s) repetido(s) entre páginas descartado(s) por idUnico "
                "(a API não ordena a paginação)."
            )
        if limit is not None and pages >= limit:
            warnings.append(f"Leitura interrompida em max_paginas={limit}; há mais páginas.")
        if rows == 0:
            warnings.append("Nenhum projeto retornado.")
        return {
            "documents_found": rows,
            "downloaded_count": pages,
            "skipped_count": duplicates,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": f"{client.base_url}/{ENDPOINT}",
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows,
            "pages": pages,
            "duplicates": duplicates,
            "export_warning": " ".join(warnings) or None,
        }
