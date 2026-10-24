"""PNCP: contratações publicadas (Portal Nacional de Contratações Públicas, API de consulta).

``https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao`` exige
``dataInicial``, ``dataFinal`` (AAAAMMDD), ``codigoModalidadeContratacao`` e
``pagina`` (a partir de 1). Verificado ao vivo em 2026-10-23: ``tamanhoPagina``
aceita de 10 a 50 (500 dá 400 "Tamanho de página inválido"); a resposta traz
``data``, ``totalRegistros``, ``totalPaginas`` e ``numeroPagina``; modalidade ou
página sem registros voltam 204 sem corpo; requisições em rajada recebem 429
(o cliente repete com espera, e o padrão de pausa entre páginas é 300 ms).
O Swagger não descreve os códigos de modalidade; os 13 usados são os do manual
do PNCP (1 leilão eletrônico a 13 leilão presencial) e a modalidade 2 (diálogo
competitivo) costuma voltar vazia. A coleta percorre o período em janelas de
``janela_dias`` dias, cada uma por modalidade. Os objetos ``orgaoEntidade``,
``unidadeOrgao`` e ``amparoLegal`` são achatados em colunas
``<objeto>_<campo>``; listas (``fontesOrcamentarias``) viram texto JSON.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

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

__all__ = ["PncpContratacoesDataSource", "parse_date"]

ProgressCallback = Callable[[Dict[str, object]], None]

DEFAULT_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
ENDPOINT = "contratacoes/publicacao"
KEY = "numeroControlePNCP"
#: Códigos de modalidade do manual do PNCP.
MODALIDADES = {
    1: "Leilão - Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa de Licitação",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
}
MIN_PAGE_SIZE, MAX_PAGE_SIZE = 10, 50


def parse_date(value: object) -> date:
    """Aceita ``AAAAMMDD``, ``AAAA-MM-DD``, ``date`` ou ``datetime``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida '{value}'. Use AAAAMMDD ou AAAA-MM-DD.")


def flatten(row: Mapping[str, object]) -> Dict[str, object]:
    """Objetos de primeiro nível viram colunas ``<objeto>_<campo>``; o resto fica como está."""
    flat: Dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, dict):
            for sub, inner in value.items():
                flat[f"{key}_{sub}"] = inner
        else:
            flat[key] = value
    return flat


def windows(start: date, end: date, days: int):
    current = start
    step = timedelta(days=max(1, int(days)))
    while current <= end:
        stop = min(end, current + step - timedelta(days=1))
        yield current, stop
        current = stop + timedelta(days=1)


class PncpContratacoesDataSource(DataSource):
    DATASET = "pncp_contratacoes"
    DEFAULT_TIMEOUT = 120
    PAGE_SIZE = MAX_PAGE_SIZE
    JANELA_DIAS = 7
    PAUSE_MS = 300
    MIN_YEAR = 2021

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
        start_date: object,
        end_date: Optional[object] = None,
        modalidades: Optional[Sequence[object]] = None,
        janela_dias: int = JANELA_DIAS,
        tamanho_pagina: int = PAGE_SIZE,
        max_paginas: Optional[int] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = PAUSE_MS,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        first = parse_date(start_date)
        last = parse_date(end_date) if end_date else first
        if last < first:
            raise ValueError("end_date anterior a start_date.")
        codes = sorted({int(m) for m in as_list(modalidades)}) or sorted(MODALIDADES)
        unknown = [c for c in codes if c not in MODALIDADES]
        if unknown:
            raise ValueError(f"Modalidade(s) desconhecida(s): {unknown}. Use {sorted(MODALIDADES)}.")
        size = min(MAX_PAGE_SIZE, max(MIN_PAGE_SIZE, int(tamanho_pagina)))
        limit = int(max_paginas) if max_paginas else None
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or JsonApiClient(
            api_base_url or DEFAULT_BASE_URL, timeout_seconds=timeout, label="PNCP"
        )
        slots = [(lo, hi, code) for lo, hi in windows(first, last, janela_dias) for code in codes]
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": len(slots)})

        spool = RowSpool(base_dir, self.name)
        seen: set = set()
        duplicates = pages = 0
        truncated = False
        try:
            for done, (lo, hi, code) in enumerate(slots, start=1):
                page = 1
                while True:
                    body = client.get_json(ENDPOINT, {
                        "dataInicial": lo.strftime("%Y%m%d"),
                        "dataFinal": hi.strftime("%Y%m%d"),
                        "codigoModalidadeContratacao": code,
                        "pagina": page,
                        "tamanhoPagina": size,
                    })
                    items = body.get("data") if isinstance(body, dict) else None
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
                        spool.add(flatten(item))
                    total_pages = int(body.get("totalPaginas") or 0)
                    pause(self._sleep, pause_ms)
                    if total_pages and page >= total_pages:
                        break
                    if limit is not None and page >= limit:
                        truncated = True
                        break
                    page += 1
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": len(slots), "files_completed": done,
                        "file_path": f"{lo:%Y%m%d}-{hi:%Y%m%d} modalidade={code}",
                    })
        except BaseException:
            spool.discard()
            raise

        rows = spool.rows
        stem = f"{self.name}_{first:%Y%m%d}_{last:%Y%m%d}"
        csv_path = spool.write_csv(base_dir / f"{stem}.csv")
        exported = finalize_export(csv_path, fmt, self.name)
        warnings: List[str] = []
        if duplicates:
            warnings.append(f"{duplicates} contratação(ões) repetida(s) descartada(s) por {KEY}.")
        if truncated:
            warnings.append(f"Leitura limitada a max_paginas={limit} por janela e modalidade; há mais páginas.")
        if rows == 0:
            warnings.append("Nenhuma contratação retornada no período.")
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
