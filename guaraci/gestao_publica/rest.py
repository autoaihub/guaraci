"""Peças comuns das APIs JSON públicas do pacote (Transferegov, Obrasgov, IPEADATA).

``JsonApiClient`` faz um GET que devolve JSON, com nova tentativa e erro
classificado, no padrão de ``guaraci/tesouro/siconfi.py``. ``RowSpool`` grava as
linhas, já como texto, num arquivo temporário e depois escreve o CSV com a união
das colunas vistas, de modo que a coleta em fluxo não precisa conhecer o
esquema de antemão e uma coluna que só aparece numa página tardia não se perde.
Valores aninhados (listas e objetos) viram texto JSON numa só coluna.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.arquivos.http_files import _sink_atomic
from guaraci.core.http import (
    READ_ERRORS,
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)

__all__ = [
    "JsonApiClient",
    "JsonApiError",
    "RowSpool",
    "as_list",
    "finalize_export",
    "normalize_format",
    "pause",
    "to_text",
]

FORMATS = ("csv", "parquet", "sqlite")


class JsonApiError(ApiClientError):
    """Falha ao consultar uma API JSON pública."""


def as_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(item).strip() for item in value if str(item).strip()]  # type: ignore[union-attr]


def normalize_format(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        return "csv"
    normalized = str(value).strip().lower()
    if normalized not in FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {FORMATS}.")
    return normalized


def to_text(value: object) -> str:
    """Texto do valor como a API publicou: ``None`` vira vazio, estrutura vira JSON."""
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


class JsonApiClient:
    DEFAULT_TIMEOUT = 60
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 4,
        headers: Optional[Mapping[str, str]] = None,
        label: str = "API",
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts
        self.headers = dict(headers or {})
        self.label = label

    def build_url(self, path: str = "", params: Optional[Mapping[str, object]] = None) -> str:
        url = self.base_url + ("/" + path.lstrip("/") if path else "")
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params, safe="$,.()'")
        return url

    def get_json(
        self,
        path: str = "",
        params: Optional[Mapping[str, object]] = None,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """GET com JSON de volta; números ficam como texto (``parse_float=str``)."""
        url = self.build_url(path, params)
        request_headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        request_headers.update(self.headers)
        request_headers.update(headers or {})

        def send() -> Any:
            request = Request(url, headers=request_headers)
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
            except HTTPError as exc:
                category, retryable = classify_http_status(exc.code)
                raise JsonApiError(
                    f"{self.label} request failed ({exc.code}) for '{url}'.",
                    category=category,
                    retryable=retryable,
                    hint="Confira os parâmetros da consulta.",
                ) from exc
            except URLError as exc:
                category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
                raise JsonApiError(
                    f"Could not reach '{url}': {exc.reason}",
                    category=category,
                    retryable=True,
                    hint="Verifique acesso à internet, DNS e regras de proxy.",
                ) from exc
            except TimeoutError as exc:
                raise JsonApiError(
                    f"Timed out on '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                ) from exc
            except READ_ERRORS as exc:
                raise JsonApiError(
                    f"Connection dropped on '{url}': {exc}",
                    category="connectivity",
                    retryable=True,
                ) from exc
            try:
                return json.loads(raw.decode("utf-8-sig"), parse_float=str, parse_int=str)
            except ValueError as exc:
                raise JsonApiError(
                    f"Invalid JSON from '{url}'.", category="api_error", retryable=True
                ) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)


class RowSpool:
    """Acumula linhas como texto num JSONL temporário e escreve o CSV com a união das colunas."""

    def __init__(self, directory: Path, stem: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=f"{stem}.", suffix=".spool", dir=str(directory))
        os.close(handle)
        self._path = Path(name)
        self._sink = open(self._path, "w", encoding="utf-8")
        self.columns: Dict[str, None] = {}
        self.rows = 0

    def add(self, row: Mapping[str, object]) -> None:
        text = {str(key): to_text(value) for key, value in row.items()}
        for key in text:
            self.columns.setdefault(key, None)
        self._sink.write(json.dumps(text, ensure_ascii=False) + "\n")
        self.rows += 1

    def write_csv(self, dest: Path, columns: Optional[Sequence[str]] = None) -> Optional[Path]:
        """CSV atômico (``.part`` e troca). Sem linhas, não cria arquivo e devolve ``None``."""
        self._sink.close()
        try:
            if self.rows == 0:
                return None
            header = list(columns) if columns else list(self.columns)
            partial = dest.with_name(dest.name + ".part")
            try:
                with open(self._path, encoding="utf-8") as source, open(
                    partial, "w", encoding="utf-8", newline=""
                ) as sink:
                    writer = csv.writer(sink, lineterminator="\n")
                    writer.writerow(header)
                    for line in source:
                        record = json.loads(line)
                        writer.writerow([record.get(col, "") for col in header])
                os.replace(partial, dest)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
            return dest
        finally:
            self._path.unlink(missing_ok=True)

    def discard(self) -> None:
        try:
            self._sink.close()
        finally:
            self._path.unlink(missing_ok=True)


def finalize_export(csv_path: Optional[Path], fmt: str, table: str) -> List[str]:
    """Converte o CSV para parquet ou sqlite quando pedido e devolve os arquivos exportados."""
    if csv_path is None:
        return []
    if fmt == "csv":
        return [str(csv_path)]
    frame = pl.scan_csv(csv_path, infer_schema=False)
    suffix = ".parquet" if fmt == "parquet" else ".sqlite"
    dest = _sink_atomic(frame, csv_path.with_suffix(suffix), fmt, table, csv_path.name)
    csv_path.unlink(missing_ok=True)
    return [str(dest)]


def pause(sleep: Callable[[float], None], pause_ms: int) -> None:
    if pause_ms and int(pause_ms) > 0:
        sleep(int(pause_ms) / 1000)
