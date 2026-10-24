"""Compras.gov.br: catálogo de materiais (CATMAT) do grupo 65 (saúde).

``https://dadosabertos.compras.gov.br/modulo-material/4_consultarItemMaterial``
pagina por ``pagina`` (a partir de 1) e ``tamanhoPagina`` (10 a 500); a resposta
traz ``resultado``, ``totalRegistros``, ``totalPaginas`` e ``paginasRestantes``.
Verificado ao vivo em 2026-10-23: o grupo 65 (equipamentos e artigos para uso
médico, dentário e veterinário) tem 108.747 itens, 218 páginas de 500. O preço
(``modulo-pesquisa-preco/1_consultarMaterial``) exige ``tipo`` e ``codigo`` do
item, ou seja, uma chamada por item; com mais de 5 mil itens, só o catálogo
entra. ``codigo_classe`` restringe a uma classe (ex.: 6505, drogas e
medicamentos). Tudo sai como texto, com os nomes de coluna como a API publica.
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

__all__ = ["ComprasCatmatSaudeDataSource"]

ProgressCallback = Callable[[Dict[str, object]], None]

DEFAULT_BASE_URL = "https://dadosabertos.compras.gov.br"
ENDPOINT = "modulo-material/4_consultarItemMaterial"
GRUPO_SAUDE = 65
MIN_PAGE_SIZE, MAX_PAGE_SIZE = 10, 500


class ComprasCatmatSaudeDataSource(DataSource):
    DATASET = "compras_gov_catmat_saude"
    DEFAULT_TIMEOUT = 120
    PAGE_SIZE = MAX_PAGE_SIZE

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
        codigo_grupo: int = GRUPO_SAUDE,
        codigo_classe: Optional[int] = None,
        tamanho_pagina: int = PAGE_SIZE,
        max_paginas: Optional[int] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        size = min(MAX_PAGE_SIZE, max(MIN_PAGE_SIZE, int(tamanho_pagina)))
        limit = int(max_paginas) if max_paginas else None
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or JsonApiClient(
            api_base_url or DEFAULT_BASE_URL, timeout_seconds=timeout, label="Compras.gov.br"
        )
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": 0})

        spool = RowSpool(base_dir, self.name)
        pages = 0
        truncated = False
        try:
            page = 1
            while True:
                params: Dict[str, object] = {
                    "pagina": page, "tamanhoPagina": size, "codigoGrupo": int(codigo_grupo),
                }
                if codigo_classe is not None:
                    params["codigoClasse"] = int(codigo_classe)
                body = client.get_json(ENDPOINT, params)
                items = body.get("resultado") if isinstance(body, dict) else None
                if not items:
                    break
                pages += 1
                for item in items:
                    spool.add(item)
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": 0, "files_completed": pages,
                        "file_path": f"pagina={page}",
                    })
                total_pages = int(body.get("totalPaginas") or 0)
                pause(self._sleep, pause_ms)
                if total_pages and page >= total_pages:
                    break
                if limit is not None and page >= limit:
                    truncated = True
                    break
                page += 1
        except BaseException:
            spool.discard()
            raise

        rows = spool.rows
        csv_path = spool.write_csv(base_dir / f"{self.name}.csv")
        exported = finalize_export(csv_path, fmt, self.name)
        warnings: List[str] = []
        if truncated:
            warnings.append(f"Leitura interrompida em max_paginas={limit}; há mais páginas.")
        if rows == 0:
            warnings.append("Nenhum item retornado.")
        return {
            "documents_found": rows,
            "downloaded_count": pages,
            "skipped_count": 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": f"{client.base_url}/{ENDPOINT}",
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows,
            "pages": pages,
            "export_warning": " ".join(warnings) or None,
        }
