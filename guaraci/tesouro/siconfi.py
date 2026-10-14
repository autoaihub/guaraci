"""Despesa por função (DCA, Anexo I-E) da API de dados abertos do SICONFI.

A API ``https://apidatalake.tesouro.gov.br/ords/siconfi/tt`` devolve a
Declaração de Contas Anuais de cada ente (município, estado, União). A consulta
exige ``id_ente``: sem ele a resposta vem vazia. Por isso a lista de entes sai
de ``/entes`` (cerca de 5,6 mil itens) e a DCA é pedida ente a ente, por
exercício. O Anexo I-E traz a despesa por função em três estágios (empenhada,
liquidada e paga); a função Saúde é o código ``10``, com subfunções ``10.301``
e seguintes.

A paginação usa ``offset``/``limit`` até ``hasMore`` ser falso. Os ``links`` da
resposta apontam para um host interno da Oracle (``oraclevcn.com``) e nunca são
seguidos: a URL de cada página é montada aqui.

O primeiro exercício com DCA de despesa por função é 2014 (verificado ao vivo
em 2026-10-13 para o município e o estado de São Paulo; 2013 volta vazio).
Tudo sai como texto UTF-8, com os nomes de coluna como a API publica.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)
from guaraci.datasus.frames import write_sqlite
from guaraci.utils.mapping import UF_TO_CODE

__all__ = ["SiconfiClient", "SiconfiClientError", "SiconfiDcaDespesaFuncaoDataSource"]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")

COLUMNS = [
    "exercicio", "instituicao", "cod_ibge", "uf", "anexo", "rotulo", "coluna",
    "cod_conta", "conta", "valor", "populacao",
]


class SiconfiClientError(ApiClientError):
    """Falha ao consultar a API do SICONFI."""


class SiconfiClient:
    DEFAULT_BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
    DEFAULT_TIMEOUT = 60
    PAGE_SIZE = 5000
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 4,
    ) -> None:
        self.base_url = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def get_json(self, path: str, params: Dict[str, object]) -> Dict[str, object]:
        url = f"{self.base_url}/{path}?{urlencode(params)}"

        def send() -> Dict[str, object]:
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                category, retryable = classify_http_status(exc.code)
                raise SiconfiClientError(
                    f"SICONFI request failed ({exc.code}) for '{url}'.",
                    category=category,
                    retryable=retryable,
                    hint="Confira o exercício, o anexo e o id_ente da consulta.",
                ) from exc
            except URLError as exc:
                category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
                raise SiconfiClientError(
                    f"Could not reach '{url}': {exc.reason}",
                    category=category,
                    retryable=True,
                    hint="Verifique acesso à internet, DNS e regras de proxy.",
                ) from exc
            except TimeoutError as exc:
                raise SiconfiClientError(
                    f"Timed out on '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                ) from exc
            except ValueError as exc:
                raise SiconfiClientError(
                    f"Invalid JSON from '{url}'.", category="api_error", retryable=True
                ) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def paginate(self, path: str, params: Dict[str, object]) -> Iterable[Dict[str, object]]:
        """Itens de todas as páginas; ``links`` da resposta são ignorados."""
        offset = 0
        while True:
            page = self.get_json(
                path, {**params, "offset": offset, "limit": self.PAGE_SIZE}
            )
            items = page.get("items") or []
            yield from items
            if not page.get("hasMore") or not items:
                return
            offset += len(items)

    def list_entes(self) -> List[Dict[str, object]]:
        return list(self.paginate("entes", {}))

    def dca_items(self, year: int, ente: object, anexo: str) -> List[Dict[str, object]]:
        return list(
            self.paginate(
                "dca", {"an_exercicio": year, "no_anexo": anexo, "id_ente": ente}
            )
        )


def _as_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(item).strip() for item in value if str(item).strip()]  # type: ignore[union-attr]


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def _text(value: object) -> str:
    return "" if value is None else str(value)


def select_entes(
    client: "SiconfiClient", ufs: Sequence[str], entes: Sequence[str]
) -> List[str]:
    """Códigos IBGE dos entes a consultar.

    Com ``entes`` explícitos, vale a lista. Com ``ufs``, entram os municípios cujo
    campo ``uf`` de ``/entes`` casa e também o próprio estado: o SICONFI publica
    os estados (esfera ``E``) e o Distrito Federal (esfera ``D``) com ``uf="BR"``,
    de modo que só o ``cod_ibge`` (igual ao código IBGE da UF) os identifica.
    """
    if entes:
        return list(dict.fromkeys(entes))
    wanted = {uf.upper() for uf in ufs}
    state_codes = {str(UF_TO_CODE[uf]) for uf in wanted if uf in UF_TO_CODE}
    found: Dict[str, None] = {}
    for item in client.list_entes():
        code = item.get("cod_ibge")
        if code is None:
            continue
        if wanted:
            in_uf = str(item.get("uf", "")).strip().upper() in wanted
            is_state = (
                str(item.get("esfera", "")).strip().upper() in {"E", "D"}
                and str(code).strip() in state_codes
            )
            if not (in_uf or is_state):
                continue
        found[str(code)] = None
    return list(found)


def _function_matches(conta: str, prefix: str) -> bool:
    """``conta`` é a função ``prefix`` ou uma subfunção dela, com fronteira.

    ``"1"`` casa ``"1 - Legislativa"`` e ``"1.031"``, mas não ``"10 - Saúde"``.
    """
    conta = conta.strip()
    return (
        conta == prefix
        or conta.startswith(prefix + " ")
        or conta.startswith(prefix + ".")
    )


class SiconfiDcaDespesaFuncaoDataSource(DataSource):
    """DCA Anexo I-E (despesa por função), com filtro local pela função."""

    DATASET = "siconfi_dca_despesa_funcao"
    ANEXO = "DCA-Anexo I-E"
    MIN_YEAR = 2014
    DEFAULT_TIMEOUT = SiconfiClient.DEFAULT_TIMEOUT
    DEFAULT_FUNCAO = "10"

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

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    def _select_entes(
        self, client: SiconfiClient, ufs: Sequence[str], entes: Sequence[str]
    ) -> List[str]:
        return select_entes(client, ufs, entes)

    def download(
        self,
        *,
        start_year: int,
        end_year: Optional[int] = None,
        uf: Optional[Sequence[str]] = None,
        entes: Optional[Sequence[str]] = None,
        funcao: Optional[str] = DEFAULT_FUNCAO,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        pause_ms: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < self.MIN_YEAR or last < first:
            raise ValueError(
                f"Invalid year range {first}-{last}; DCA by function starts in {self.MIN_YEAR}."
            )
        fmt = _normalize_format(output_format) or "csv"
        code = str(funcao).strip() if funcao is not None else ""
        prefix = "" if code.lower() in {"", "todas"} else code
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or SiconfiClient(base_url=api_base_url, timeout_seconds=timeout)

        targets = self._select_entes(client, _as_list(uf), _as_list(entes))
        years = list(range(first, last + 1))
        total = len(targets) * len(years)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": total}
            )

        csv_path = base_dir / f"{self.name}.csv"
        raw_path = base_dir / f"{self.name}.raw.jsonl"
        downloaded = failed = rows_written = done = 0
        failures: List[str] = []
        with open(csv_path, "w", encoding="utf-8", newline="") as sink:
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(COLUMNS)
            raw_sink = open(raw_path, "w", encoding="utf-8") if keep_raw else None
            try:
                for year in years:
                    for ente in targets:
                        done += 1
                        try:
                            items = client.dca_items(year, ente, self.ANEXO)
                        except ApiClientError as exc:
                            failed += 1
                            failures.append(f"{year}/{ente}: {exc.message}")
                            items = []
                        else:
                            downloaded += 1
                        for item in items:
                            if raw_sink is not None:
                                raw_sink.write(json.dumps(item, ensure_ascii=False) + "\n")
                            if prefix and not _function_matches(_text(item.get("conta")), prefix):
                                continue
                            writer.writerow([_text(item.get(col)).strip() for col in COLUMNS])
                            rows_written += 1
                        if progress_callback is not None:
                            progress_callback({
                                "event": "file_progress", "source": self.name,
                                "documents_total": total, "files_completed": done,
                                "file_path": f"{year}/{ente}",
                            })
                        if pause_ms and int(pause_ms) > 0:
                            self._sleep(int(pause_ms) / 1000)
            finally:
                if raw_sink is not None:
                    raw_sink.close()

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
                    raise ValueError("SICONFI export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]

        warnings: List[str] = []
        if failures:
            warnings.append(
                f"{failed} consulta(s) ente/ano falharam (primeiras: {'; '.join(failures[:3])})."
            )
        if rows_written == 0 and not failed:
            warnings.append("Nenhuma linha encontrada para os filtros informados.")
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": 0,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": f"{client.base_url}/dca",
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "rows": rows_written,
            "raw_file": str(raw_path) if keep_raw else None,
            "export_warning": " ".join(warnings) or None,
        }
