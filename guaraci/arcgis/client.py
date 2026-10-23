"""Cliente do ArcGIS REST para ler uma camada de tabela ou feição, página a página.

A consulta é ``<camada>/query?where=...&outFields=*&f=json`` com
``orderByFields=<campo OID>`` e ``resultOffset``/``resultRecordCount``. A página
respeita o ``maxRecordCount`` da camada (lido do JSON dela) e a leitura termina
quando a resposta não traz feições, e não pelo ``exceededTransferLimit``, que
alguns servidores omitem. O ArcGIS devolve erro de aplicação com HTTP 200 e um
objeto ``error``; esse caso vira :class:`ArcgisClientError`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from guaraci import __version__
from guaraci.core.http import (
    READ_ERRORS,
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)

__all__ = ["ArcgisClient", "ArcgisClientError", "ArcgisLayer", "epoch_ms_to_iso_date"]

DEFAULT_MAX_RECORD_COUNT = 1000
OID_FIELD_TYPE = "esriFieldTypeOID"
DATE_FIELD_TYPE = "esriFieldTypeDate"


class ArcgisClientError(ApiClientError):
    """Falha ao consultar um serviço ArcGIS REST."""


@dataclass
class ArcgisLayer:
    """Metadados da camada que importam para a leitura."""

    name: str
    max_record_count: int
    oid_field: Optional[str]
    #: Campos na ordem do serviço, como ``(nome, tipo)``.
    fields: List[tuple] = field(default_factory=list)

    @property
    def field_names(self) -> List[str]:
        return [name for name, _ in self.fields]

    def date_fields(self) -> List[str]:
        return [name for name, kind in self.fields if kind == DATE_FIELD_TYPE]


def epoch_ms_to_iso_date(value: object) -> str:
    """Data ISO (UTC) de um ``esriFieldTypeDate`` em milissegundos; vazio se nulo."""
    if value is None or value == "":
        return ""
    stamp = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    return stamp.date().isoformat()


class ArcgisClient:
    DEFAULT_TIMEOUT = 120
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(self, *, timeout_seconds: int = DEFAULT_TIMEOUT, max_attempts: int = 3) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def get_json(self, url: str, params: Dict[str, object]) -> Dict[str, object]:
        full = f"{url}?{urlencode({**params, 'f': 'json'})}"

        def send() -> Dict[str, object]:
            request = Request(full, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                category, retryable = classify_http_status(exc.code)
                raise ArcgisClientError(
                    f"ArcGIS request failed ({exc.code}) for '{url}'.",
                    category=category,
                    retryable=retryable,
                    hint="Confira a URL da camada (.../MapServer/<id>).",
                ) from exc
            except URLError as exc:
                category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
                raise ArcgisClientError(
                    f"Could not reach '{url}': {exc.reason}",
                    category=category,
                    retryable=True,
                    hint="Verifique acesso à internet, DNS e regras de proxy.",
                ) from exc
            except TimeoutError as exc:
                raise ArcgisClientError(
                    f"Timed out on '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                ) from exc
            except READ_ERRORS as exc:
                raise ArcgisClientError(
                    f"Connection dropped on '{url}': {exc}",
                    category="connectivity",
                    retryable=True,
                ) from exc
            except ValueError as exc:
                raise ArcgisClientError(
                    f"Invalid JSON from '{url}'.", category="api_error", retryable=True
                ) from exc
            error = payload.get("error") if isinstance(payload, dict) else None
            if error:
                code = error.get("code") if isinstance(error, dict) else None
                raise ArcgisClientError(
                    f"ArcGIS error {code} for '{url}': {error}",
                    category="api_error",
                    retryable=code in (500, 502, 503, 504),
                )
            return payload

        return request_with_retry(send, max_attempts=self.max_attempts)

    def layer(self, layer_url: str) -> ArcgisLayer:
        info = self.get_json(layer_url, {})
        fields = [(f["name"], f.get("type", "")) for f in info.get("fields", [])]
        oid = info.get("objectIdField") or next(
            (name for name, kind in fields if kind == OID_FIELD_TYPE), None
        )
        return ArcgisLayer(
            name=str(info.get("name", "")),
            max_record_count=int(info.get("maxRecordCount") or DEFAULT_MAX_RECORD_COUNT),
            oid_field=oid,
            fields=fields,
        )

    def count(self, layer_url: str, where: str = "1=1") -> int:
        payload = self.get_json(
            f"{layer_url}/query", {"where": where, "returnCountOnly": "true"}
        )
        return int(payload.get("count", 0))

    def iter_features(
        self,
        layer_url: str,
        layer: ArcgisLayer,
        *,
        where: str = "1=1",
        page_size: Optional[int] = None,
    ) -> Iterator[Dict[str, object]]:
        """Atributos de cada feição, em ordem estável do OID, até a página vazia."""
        size = max(1, min(page_size or layer.max_record_count, layer.max_record_count))
        offset = 0
        while True:
            params: Dict[str, object] = {
                "where": where,
                "outFields": "*",
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": size,
            }
            if layer.oid_field:
                params["orderByFields"] = layer.oid_field
            payload = self.get_json(f"{layer_url}/query", params)
            features = payload.get("features") or []
            if not features:
                return
            for feature in features:
                yield feature.get("attributes", {})
            offset += len(features)
