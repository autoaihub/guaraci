"""Acumulador de registros paginados que derrama para disco.

A coleta pela API DEMAS junta as páginas numa lista de dicionários e só a
converte em DataFrame no fim. Medido sobre ``/arboviroses/dengue``, cada
registro ocupa cerca de 11 KB nessa forma, então o ano de 2024, que tem mais
de 4 milhões de registros, exigiria cerca de 45 GB de memória. A coleta morria
por falta de memória depois de horas de espera, sem deixar nada aproveitável.

Aqui os registros seguem em memória enquanto a coleta é pequena, que é o caso
da maioria das fontes, e passam a ser gravados em partes parquet assim que
cruzam :data:`DEFAULT_SPILL_THRESHOLD`. O consumidor recebe sempre um
DataFrame ou um plano lazy, sem precisar saber qual dos dois caminhos foi
usado.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Union

import polars as pl
from loguru import logger

Record = Dict[str, object]

#: A partir de quantos registros acumulados a gravação em disco começa. Abaixo
#: disto o custo de memória é irrelevante e manter tudo em memória evita I/O
#: desnecessário para as fontes pequenas.
#:
#: Medido sobre 60 000 registros de ``/arboviroses/dengue``: sem derramar, o
#: pico é de 1696 MB em 219 s; com limiar de 5000, cai para 593 MB em 245 s;
#: com 1000, chega a 497 MB mas o tempo sobe para 322 s. O ganho satura em
#: 5000, que colhe 65% da redução por 12% de tempo a mais.
DEFAULT_SPILL_THRESHOLD = 5_000


class PagedRecordBuffer:
    """Junta os registros das páginas, derramando para disco quando cresce."""

    def __init__(
        self,
        *,
        spill_threshold: int = DEFAULT_SPILL_THRESHOLD,
        spill_dir: Optional[Path] = None,
    ) -> None:
        self._threshold = max(1, int(spill_threshold))
        self._pending: List[Record] = []
        self._parts: List[Path] = []
        self._count = 0
        self._spill_root: Optional[Path] = Path(spill_dir) if spill_dir else None
        self._owns_spill_root = spill_dir is None

    # --- acumulação ---------------------------------------------------------

    def extend(self, rows: Iterable[Record]) -> None:
        novos = list(rows)
        if not novos:
            return
        self._pending.extend(novos)
        self._count += len(novos)
        if len(self._pending) >= self._threshold:
            self._flush()

    def _spill_path(self) -> Path:
        if self._spill_root is None:
            self._spill_root = Path(tempfile.mkdtemp(prefix="guaraci_ods_"))
        self._spill_root.mkdir(parents=True, exist_ok=True)
        return self._spill_root / f"part_{len(self._parts):05d}.parquet"

    def _flush(self) -> None:
        if not self._pending:
            return
        part = self._spill_path()
        _frame_from_records(self._pending).write_parquet(part)
        self._parts.append(part)
        logger.debug(
            "Spilled {} records to {} (total so far: {})",
            len(self._pending),
            part.name,
            self._count,
        )
        self._pending = []

    # --- consulta -----------------------------------------------------------

    def __len__(self) -> int:
        return self._count

    def __bool__(self) -> bool:
        return self._count > 0

    @property
    def spilled(self) -> bool:
        """Diz se algum lote já foi para o disco."""
        return bool(self._parts)

    @property
    def records(self) -> List[Record]:
        """Registros ainda em memória.

        Vazio depois de um derramamento: quem precisa do conteúdo completo
        deve usar :meth:`frame` ou :meth:`iter_records`.
        """
        return [] if self.spilled else list(self._pending)

    def iter_records(self) -> Iterator[Record]:
        """Percorre todos os registros, um a um, sem materializar o conjunto."""
        for part in self._parts:
            for row in pl.read_parquet(part).iter_rows(named=True):
                yield row
        yield from self._pending

    def frame(self) -> Union[pl.DataFrame, pl.LazyFrame]:
        """Conjunto completo: DataFrame quando coube em memória, plano lazy quando não.

        O plano lazy permite que a escrita do arquivo final seja feita em
        streaming, sem reunir tudo de novo.
        """
        if not self.spilled:
            return _frame_from_records(self._pending)
        self._flush()
        if len(self._parts) == 1:
            return pl.scan_parquet(self._parts[0])
        return pl.concat(
            [pl.scan_parquet(part) for part in self._parts], how="diagonal_relaxed"
        )

    def write_jsonl(self, path: Path) -> Path:
        """Grava o conteúdo como JSON Lines, lendo por partes."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handler:
            for row in self.iter_records():
                handler.write(json.dumps(row, ensure_ascii=False, default=str))
                handler.write("\n")
        return path

    def cleanup(self) -> None:
        """Remove as partes temporárias, se este buffer é dono do diretório."""
        if self._owns_spill_root and self._spill_root and self._spill_root.exists():
            shutil.rmtree(self._spill_root, ignore_errors=True)
        self._parts = []
        self._spill_root = None


def _frame_from_records(records: Sequence[Record]) -> pl.DataFrame:
    """DataFrame a partir dos dicionários da API, tolerante a tipos mistos."""
    if not records:
        return pl.DataFrame()
    try:
        return pl.DataFrame(list(records), infer_schema_length=None)
    except Exception:
        import pandas as pd

        return pl.from_pandas(pd.DataFrame.from_records(list(records)))
