"""Cliente HTTP para o ArcGIS REST público da CETESB (QUALAR).

A CETESB documenta o QUALAR como um sistema de consulta com cadastro. O que a
documentação não anuncia é que o mesmo banco está exposto, sem autenticação
nenhuma, num ArcGIS Server em ``servicos.cetesb.sp.gov.br/arcgis``. É esse o
caminho que este cliente usa: JSON sobre HTTP, sem chave, sem formulário.

O que o serviço entrega, verificado ao vivo em 2026-09-15
---------------------------------------------------------
``QUALAR/CETESB_QUALAR/MapServer`` tem oito camadas:

- camadas 0 a 5: uma por poluente (CO, MP10, MP2.5, NO2, O3, SO2), cada uma
  com uma linha por estação e 96 colunas de dados, ``M1..M48`` e ``TM1..TM48``;
- camada 6 (``PTO``): o cadastro das estações, com endereço, município e o
  índice corrente;
- camada 7: pior índice da Região Metropolitana de São Paulo.

Duas armadilhas neste formato, ambas confirmadas contra o serviço
--------------------------------------------------------------
1. **``M`` é ÍNDICE de qualidade do ar, não concentração.** A tentação é ler
   ``M1`` de MP10 como µg/m³, e o valor até parece plausível. Não é. Em
   2026-09-15 10:00 a estação Americana devolveu ``M1 = 10`` na camada de MP10
   e, na camada 6, ``Indice = 10`` com ``POLUENTE = MP10``. A conferência
   bateu em oito estações seguidas. Concentração em µg/m³ só pelo QUALAR
   clássico, com login. Quem usar este dado como se fosse concentração vai
   errar, porque o índice é uma transformação por faixas, não linear.
2. **``TM`` é hora LOCAL carimbada como se fosse UTC.** O valor vem em
   milissegundos de época; lido como UTC dá exatamente a hora local de São
   Paulo que a camada 6 publica no campo ``DATA``. Aplicar deslocamento de
   fuso desloca a série em três horas. Ver :func:`epoch_ms_to_local_naive`.

A janela é móvel: sempre as últimas 48 horas, sem histórico. Existe um serviço
``QA_Hist`` com uma tabela histórica, mas ela cobre apenas 02/03/2021 a
26/10/2021 e parou ali, então não serve como série e não é usada aqui.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from guaraci import __version__
from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    open_response,
    request_with_retry,
)

__all__ = [
    "CetesbClientError",
    "CetesbQualarClient",
    "POLLUTANT_LAYERS",
    "STATION_LAYER",
    "HOURS_PER_WINDOW",
    "epoch_ms_to_local_naive",
]

# Poluente -> id da camada. Os rótulos são os que a CETESB usa nos nomes das
# camadas, preservados como o publicador escreve (``MP2.5``, com ponto).
POLLUTANT_LAYERS: Mapping[str, int] = {
    "CO": 0,
    "MP10": 1,
    "MP2.5": 2,
    "NO2": 3,
    "O3": 4,
    "SO2": 5,
}

STATION_LAYER = 6
"""Camada do cadastro de estações (``QUALAR_DADOSHORARIOS_PTO``)."""

HOURS_PER_WINDOW = 48
"""Colunas ``M``/``TM`` por linha: a janela móvel é sempre de 48 horas."""


def epoch_ms_to_local_naive(value: object) -> Optional[datetime]:
    """Converte o carimbo ``TM``/``DataHora`` da CETESB em datetime ingênuo.

    O serviço entrega milissegundos de época, mas o instante codificado já é a
    hora local de São Paulo: ler como UTC devolve a hora que a própria CETESB
    publica no campo ``DATA`` da camada de estações. Por isso a conversão é
    feita em UTC e o fuso é descartado, em vez de convertido. Somar ou subtrair
    três horas aqui desalinharia a série inteira.
    """
    if value is None:
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    # ``utcfromtimestamp`` está depreciado; o caminho com fuso explícito e
    # ``replace(tzinfo=None)`` produz o mesmo datetime ingênuo sem o aviso.
    moment = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=millis)
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


class CetesbClientError(ApiClientError):
    """Levantado quando uma operação no ArcGIS da CETESB falha."""


class CetesbQualarClient:
    """Cliente mínimo para o MapServer QUALAR da CETESB."""

    DEFAULT_BASE_URL = (
        "https://servicos.cetesb.sp.gov.br/arcgis/rest/services/QUALAR/CETESB_QUALAR/MapServer"
    )
    DEFAULT_TIMEOUT = 120

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        selected = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected:
            raise ValueError("CETESB base URL cannot be empty.")
        self.base_url = selected
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def query_layer(
        self,
        layer: int,
        *,
        out_fields: str = "*",
        where: str = "1=1",
        return_geometry: bool = False,
    ) -> List[Dict[str, Any]]:
        """Consulta uma camada e devolve as feições cruas (``attributes``/``geometry``).

        Não pagina: as camadas do QUALAR têm uma linha por estação, 62 no
        total, bem abaixo de qualquer teto de ``maxRecordCount``. Se a CETESB
        truncar a resposta, ``exceededTransferLimit`` vira erro explícito em
        vez de série silenciosamente incompleta.
        """
        query = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "f": "json",
        }
        url = f"{self.base_url}/{int(layer)}/query?{urlencode(query)}"
        payload = self._request_json(url)

        if isinstance(payload, Mapping) and payload.get("error"):
            detail = payload.get("error")
            message = ""
            if isinstance(detail, Mapping):
                message = str(detail.get("message") or "")
            raise CetesbClientError(
                f"CETESB ArcGIS returned an error for layer {layer}: {message}".strip(),
                category="response_format",
                hint="Confirme o id da camada e os campos pedidos em outFields.",
            )
        if not isinstance(payload, Mapping):
            raise CetesbClientError(
                "Unexpected CETESB response (expected a JSON object).",
                category="response_format",
            )
        if payload.get("exceededTransferLimit"):
            raise CetesbClientError(
                f"CETESB truncated the response for layer {layer} "
                "(exceededTransferLimit). A série viria incompleta.",
                category="response_format",
                retryable=False,
                hint="Reduza o filtro 'where' ou os campos pedidos.",
            )
        features = payload.get("features")
        if not isinstance(features, list):
            return []
        return [item for item in features if isinstance(item, Mapping)]

    def service_info(self) -> Dict[str, Any]:
        """Metadados do MapServer, usados para confirmar as camadas esperadas."""
        payload = self._request_json(f"{self.base_url}?f=json")
        return dict(payload) if isinstance(payload, Mapping) else {}

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------
    def _request_json(self, url: str) -> Any:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"guaraci/{__version__}",
            },
        )

        def on_http_error(exc: HTTPError) -> CetesbClientError:
            _category, retryable = classify_http_status(exc.code)
            return CetesbClientError(
                f"CETESB request failed ({exc.code}).",
                category="http_error" if retryable else "configuration",
                retryable=retryable,
                hint="Confirme a URL do MapServer e o id da camada.",
            )

        def on_url_error(exc: URLError) -> CetesbClientError:
            return CetesbClientError(
                f"Could not connect to CETESB endpoint '{self.base_url}': {exc.reason}",
                category="connectivity",
                retryable=True,
                hint="Verifique acesso à internet, DNS e regras de proxy.",
            )

        def on_timeout(exc: Exception) -> CetesbClientError:
            return CetesbClientError(
                f"CETESB request timed out after {self.timeout_seconds} seconds.",
                category="timeout",
                retryable=True,
                hint="Tente de novo; o ArcGIS da CETESB oscila em horário de pico.",
            )

        def send() -> Any:
            raw_bytes, _headers = open_response(
                urlopen,
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            try:
                return json.loads(raw_bytes.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CetesbClientError(
                    "CETESB response was not valid JSON.",
                    category="response_format",
                    retryable=False,
                    hint="O ArcGIS pode ter devolvido uma página de erro HTML.",
                ) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)
