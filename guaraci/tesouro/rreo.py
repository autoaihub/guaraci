"""RREO (Relatório Resumido da Execução Orçamentária), despesa na função Saúde.

Verificado ao vivo em 2026-10-13: o ``RREO-Anexo 12`` (ASPS) e o ``RREO-Anexo 08``
(MDE) NÃO são servidos por ``/tt/rreo``; os anexos presentes são 01 a 04, 06, 07,
09, 10 (RPPS), 11, 13 e 14. A despesa em Saúde sai do ``RREO-Anexo 02`` (despesa
por função), linhas com ``conta == "Saúde"`` (``cod_conta`` ``RREO2TotalDespesas``
e ``RREO2TotalDespesasIntra``), em 11 colunas (dotação inicial e atualizada,
empenhada, liquidada, saldos, restos a pagar). O tipo de demonstrativo é sempre
``RREO`` (``RREO Simplificado`` volta vazio, inclusive para município pequeno).
Periodicidade bimestral (``nr_periodo`` 1 a 6); exercícios desde 2015 (2013 e 2014
voltam vazios). Valor numérico com ponto decimal, como a API publica.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import polars as pl

from guaraci.core.datasource import DataSource
from guaraci.core.http import ApiClientError
from guaraci.datasus.frames import write_sqlite
from guaraci.tesouro.siconfi import SiconfiClient, _as_list, _normalize_format, _text

COLUMNS = [
    "exercicio", "demonstrativo", "periodo", "periodicidade", "instituicao",
    "cod_ibge", "uf", "populacao", "anexo", "esfera", "rotulo", "coluna",
    "cod_conta", "conta", "valor",
]


class SiconfiRreoSaudeDataSource(DataSource):
    """RREO Anexo 02, filtrado localmente pela função Saúde."""

    DATASET = "siconfi_rreo_saude"
    ANEXO = "RREO-Anexo 02"
    TIPO = "RREO"
    MIN_YEAR = 2015
    DEFAULT_TIMEOUT = SiconfiClient.DEFAULT_TIMEOUT
    DEFAULT_CONTA = "Saúde"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[SiconfiClient] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(name=self.DATASET, output_path=output_path)
        self._client = client
        self._sleep = sleep

    def load_dataframe(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    def _select_entes(self, client, ufs: Sequence[str], entes: Sequence[str]) -> List[str]:
        if entes:
            return list(dict.fromkeys(entes))
        wanted = {uf.upper() for uf in ufs}
        found: Dict[str, None] = {}
        for item in client.list_entes():
            if wanted and str(item.get("uf", "")).upper() not in wanted:
                continue
            if item.get("cod_ibge") is not None:
                found[str(item["cod_ibge"])] = None
        return list(found)

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
        periodos: Optional[Sequence[object]] = None,
        uf: Optional[Sequence[str]] = None,
        entes: Optional[Sequence[str]] = None,
        conta: Optional[str] = DEFAULT_CONTA,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = 0,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < self.MIN_YEAR or last < first:
            raise ValueError(f"Invalid year range {first}-{last}; RREO starts in {self.MIN_YEAR}.")
        bimestres = sorted({int(p) for p in _as_list(periodos)}) or [1, 2, 3, 4, 5, 6]
        if any(p < 1 or p > 6 for p in bimestres):
            raise ValueError("periodos must be between 1 and 6 (bimestres).")
        fmt = _normalize_format(output_format) or "csv"
        wanted = (conta or "").strip()
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or SiconfiClient(base_url=api_base_url, timeout_seconds=timeout)

        targets = self._select_entes(client, _as_list(uf), _as_list(entes))
        units = [(y, p, e) for y in range(first, last + 1) for p in bimestres for e in targets]
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(units)}
            )
        csv_path = base_dir / f"{self.name}.csv"
        raw_path = base_dir / f"{self.name}.raw.jsonl"
        downloaded = failed = rows_written = 0
        failures: List[str] = []
        with open(csv_path, "w", encoding="utf-8", newline="") as sink:
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(COLUMNS)
            raw_sink = open(raw_path, "w", encoding="utf-8") if keep_raw else None
            try:
                for done, (year, period, ente) in enumerate(units, start=1):
                    try:
                        items = list(client.paginate("rreo", {
                            "an_exercicio": year, "nr_periodo": period,
                            "co_tipo_demonstrativo": self.TIPO,
                            "no_anexo": self.ANEXO, "id_ente": ente,
                        }))
                    except ApiClientError as exc:
                        failed += 1
                        failures.append(f"{year}/{period}/{ente}: {exc.message}")
                        items = []
                    else:
                        downloaded += 1
                    for item in items:
                        if raw_sink is not None:
                            raw_sink.write(json.dumps(item, ensure_ascii=False) + "\n")
                        if wanted and _text(item.get("conta")).strip() != wanted:
                            continue
                        writer.writerow([_text(item.get(col)).strip() for col in COLUMNS])
                        rows_written += 1
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name,
                            "documents_total": len(units), "files_completed": done,
                            "file_path": f"{year}/{period}/{ente}",
                        })
                    if pause_ms and int(pause_ms) > 0:
                        self._sleep(int(pause_ms) / 1000)
            finally:
                if raw_sink is not None:
                    raw_sink.close()

        exported = [str(csv_path)]
        if fmt != "csv":
            frame = pl.scan_csv(csv_path, infer_schema=False)
            if fmt == "parquet":
                dest = base_dir / f"{self.name}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(
                    frame, db_path=base_dir / f"{self.name}.sqlite", table=self.name
                )
                if written is None:
                    raise ValueError("SICONFI export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]
        warnings: List[str] = []
        if failures:
            warnings.append(
                f"{failed} consulta(s) falharam (primeiras: {'; '.join(failures[:3])})."
            )
        if rows_written == 0 and not failed:
            warnings.append("Nenhuma linha encontrada para os filtros informados.")
        return {
            "documents_found": len(units),
            "downloaded_count": downloaded,
            "skipped_count": 0,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": f"{client.base_url}/rreo",
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "rows": rows_written,
            "raw_file": str(raw_path) if keep_raw else None,
            "export_warning": " ".join(warnings) or None,
        }
