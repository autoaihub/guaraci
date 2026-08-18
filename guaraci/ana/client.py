"""HTTP client for the ANA / SNIRH HidroWebService (new REST API).

Facts locked by live inspection on 2026-08-18 of the public OpenAPI document
at ``https://www.ana.gov.br/hidrowebservice/api-docs`` (the Swagger UI at
``/swagger-ui/index.html`` is a client-rendered SPA; the JSON spec it loads is
served at ``/hidrowebservice/api-docs``, not the more common ``/v3/api-docs``):

- The legacy webservice ``telemetriaws1.ana.gov.br`` is discontinued
  (2026-06-30) and is NOT used here.
- Auth: ``GET /EstacoesTelemetricas/OAUth/v1`` with the credentials in the
  ``Identificador``/``Senha`` headers (not query params, not body).
- The spec declares a single GLOBAL security scheme
  (``components.securitySchemes.Authorization`` = HTTP bearer, JWT format)
  applied to every operation. In practice the ``OAUth/v1`` call itself does
  not require a bearer token (it is how one is obtained); every other
  operation is called with ``Authorization: Bearer <tokenautenticacao>``.
- The telemetric series endpoints (``HidroinfoanaSerieTelemetricaAdotada/v1``
  and ``.../Detalhada/v1``) take query parameters with literal Portuguese,
  accented names: ``Código da Estação`` (int), ``Tipo Filtro Data`` (enum
  ``DATA_LEITURA``/``DATA_ULTIMA_ATUALIZACAO``), ``Data de Busca
  (yyyy-MM-dd)`` (reference date), and ``Range Intervalo de busca`` (enum of
  minute/hour/day buckets, largest being ``DIAS_30``). There is no
  ``start_date``/``end_date`` pair on these endpoints — the API looks back
  (or around) a fixed bucket from the reference date, which is why the
  datasource layer (``guaraci/ana/hidro.py``) slices any requested window
  into <=30-day chunks anchored at each chunk's end date and filters the
  combined response client-side to the caller's actual window.

Response field names beyond the OAuth token are NOT locked: the OpenAPI
document types ``Devolucao.items`` as an opaque ``object`` (no properties are
published), and no ANA credentials were available while writing this client
(the operator's e-mail registration with ANA is still pending) to inspect a
real payload. This client therefore decodes ``items`` generically (list of
dict, or a single dict) and passes it through unchanged; field-name mapping,
if any is needed, lives in the datasource and is documented there as
EXPERIMENTAL / live-data-unvalidated (mirroring ``guaraci/nasa/gpm.py``,
which faced the same "contract confirmed, live payload unvalidated" gap).
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from guaraci.core.http import (
    DEFAULT_MAX_ATTEMPTS,
    ApiClientError,
    classify_http_status,
    decode_json_mapping,
    is_timeout_reason,
    open_response,
    read_http_error_body,
    request_with_retry,
)

# Token lifetime per the ANA manual: 60 minutes. A safety margin forces a
# proactive re-authentication a bit before the real expiry so a long-running
# multi-chunk download never straddles the boundary.
_TOKEN_TTL_SECONDS = 60 * 60
_TOKEN_SAFETY_MARGIN_SECONDS = 90

_StrOrInt = Union[str, int]


class AnaHidroClientError(ApiClientError):
    """Raised when ANA HidroWebService operations fail."""


class AnaHidroClient:
    """Minimal client for the ANA HidroWebService REST API.

    Handles OAuth token acquisition/caching/renewal and the two telemetric
    series endpoints used by :class:`guaraci.ana.hidro.AnaHidroDataSource`.
    Credentials are provided by the caller (the datasource resolves them from
    ``GUARACI_ANA_ID``/``GUARACI_ANA_SENHA``); this client never reads
    environment variables or files itself, matching the NASA/IBGE clients.
    """

    DEFAULT_BASE_URL = "https://www.ana.gov.br/hidrowebservice"

    VALID_TIPO_FILTRO_DATA = ("DATA_LEITURA", "DATA_ULTIMA_ATUALIZACAO")
    VALID_DETAIL = ("adotada", "detalhada")
    # Full published enum for "Range Intervalo de busca"; the datasource only
    # ever requests the maximum daily bucket (DIAS_30) per 30-day chunk.
    VALID_RANGE = (
        "MINUTO_5", "MINUTO_10", "MINUTO_15", "MINUTO_30",
        "HORA_1", "HORA_2", "HORA_3", "HORA_4", "HORA_5", "HORA_6",
        "HORA_7", "HORA_8", "HORA_9", "HORA_10", "HORA_11", "HORA_12",
        "HORA_13", "HORA_14", "HORA_15", "HORA_16", "HORA_17", "HORA_18",
        "HORA_19", "HORA_20", "HORA_21", "HORA_22", "HORA_23", "HORA_24",
        "DIAS_2", "DIAS_7", "DIAS_14", "DIAS_21", "DIAS_30",
    )
    RANGE_MAX_DAYS = "DIAS_30"

    def __init__(
        self,
        *,
        identificador: str,
        senha: str,
        base_url: Optional[str] = None,
        timeout_seconds: int = 120,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        id_clean = str(identificador).strip()
        senha_clean = str(senha).strip()
        if not id_clean or not senha_clean:
            raise ValueError(
                "ANA HidroWebService requires both 'identificador' and 'senha'."
            )
        self._identificador = id_clean
        self._senha = senha_clean
        selected = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected:
            raise ValueError("ANA HidroWebService base URL cannot be empty.")
        self.base_url = selected
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self._clock = clock
        self._token: Optional[str] = None
        self._token_issued_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _token_is_fresh(self) -> bool:
        if self._token is None or self._token_issued_at is None:
            return False
        age = self._clock() - self._token_issued_at
        return age < (_TOKEN_TTL_SECONDS - _TOKEN_SAFETY_MARGIN_SECONDS)

    def _ensure_token(self) -> str:
        if self._token_is_fresh():
            assert self._token is not None
            return self._token
        return self.authenticate()

    def authenticate(self) -> str:
        """Call ``OAUth/v1`` and cache the returned token. Returns the token."""
        url = f"{self.base_url}/EstacoesTelemetricas/OAUth/v1"
        request = Request(
            url,
            headers={
                "Identificador": self._identificador,
                "Senha": self._senha,
                "Accept": "application/json",
                "User-Agent": "guaraci/0.6.0",
            },
        )
        payload = self._send_json(
            request,
            secret=self._senha,
            connection_label="autenticação (OAUth/v1)",
        )
        token = self._extract_token(payload)
        self._token = token
        self._token_issued_at = self._clock()
        return token

    @staticmethod
    def _extract_token(payload: Mapping[str, object]) -> str:
        items = payload.get("items")
        candidate: Optional[object] = None
        if isinstance(items, Mapping):
            candidate = items.get("tokenautenticacao")
        elif isinstance(items, list) and items and isinstance(items[0], Mapping):
            candidate = items[0].get("tokenautenticacao")
        if not candidate:
            candidate = payload.get("tokenautenticacao")
        if not candidate or not str(candidate).strip():
            raise AnaHidroClientError(
                "ANA HidroWebService authentication call succeeded but no "
                "'tokenautenticacao' field was found in the response.",
                category="response_format",
                hint=(
                    "The OAUth/v1 response shape may have changed; inspect "
                    "the raw payload before retrying."
                ),
            )
        return str(candidate).strip()

    # ------------------------------------------------------------------
    # Telemetric series (adotada / detalhada)
    # ------------------------------------------------------------------
    def serie_telemetrica(
        self,
        *,
        station_id: _StrOrInt,
        detail: str,
        data_busca: str,
        tipo_filtro_data: str = "DATA_LEITURA",
        range_intervalo: str = RANGE_MAX_DAYS,
    ) -> List[Dict[str, object]]:
        """Fetch one 30-day-max telemetric bucket for one station.

        ``detail`` selects ``adotada`` (adopted chuva/nível/vazão readings)
        or ``detalhada`` (adopted + raw sensor readings). ``data_busca`` is
        the reference date (``YYYY-MM-DD``) the API's ``Range`` bucket is
        anchored to.
        """
        detail_clean = str(detail).strip().lower()
        if detail_clean not in self.VALID_DETAIL:
            raise AnaHidroClientError(
                f"Unsupported ANA HidroWebService detail '{detail}'.",
                category="configuration",
                hint=f"Allowed: {', '.join(self.VALID_DETAIL)}.",
            )
        if tipo_filtro_data not in self.VALID_TIPO_FILTRO_DATA:
            raise AnaHidroClientError(
                f"Unsupported 'tipo_filtro_data' value '{tipo_filtro_data}'.",
                category="configuration",
                hint=f"Allowed: {', '.join(self.VALID_TIPO_FILTRO_DATA)}.",
            )
        if range_intervalo not in self.VALID_RANGE:
            raise AnaHidroClientError(
                f"Unsupported 'range_intervalo' value '{range_intervalo}'.",
                category="configuration",
                hint=f"Allowed: {', '.join(self.VALID_RANGE)}.",
            )

        endpoint = (
            "HidroinfoanaSerieTelemetricaAdotada"
            if detail_clean == "adotada"
            else "HidroinfoanaSerieTelemetricaDetalhada"
        )
        query = urlencode(
            {
                "Código da Estação": str(station_id),
                "Tipo Filtro Data": tipo_filtro_data,
                "Data de Busca (yyyy-MM-dd)": data_busca,
                "Range Intervalo de busca": range_intervalo,
            }
        )
        url = f"{self.base_url}/EstacoesTelemetricas/{endpoint}/v1?{query}"
        payload = self._authorized_get(url, label=f"{endpoint}/v1")
        return self._extract_items(payload)

    @staticmethod
    def _extract_items(payload: Mapping[str, object]) -> List[Dict[str, object]]:
        items = payload.get("items")
        if items is None:
            return []
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, Mapping)]
        if isinstance(items, Mapping):
            return [dict(items)]
        return []

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------
    def _authorized_get(self, url: str, *, label: str, _retried: bool = False) -> Dict[str, object]:
        token = self._ensure_token()
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "guaraci/0.6.0",
            },
        )
        try:
            return self._send_json(request, secret=self._senha, connection_label=label)
        except AnaHidroClientError as exc:
            # A stale-but-not-yet-expired token can still be rejected by the
            # server; re-authenticate once and retry before giving up.
            if exc.category == "configuration" and "401" in exc.message and not _retried:
                self._token = None
                self._token_issued_at = None
                return self._authorized_get(url, label=label, _retried=True)
            raise

    def _send_json(
        self, request: Request, *, secret: str, connection_label: str
    ) -> Dict[str, object]:
        def on_http_error(exc: HTTPError) -> AnaHidroClientError:
            message = self._redact(self._extract_http_error_message(exc), secret)
            category, retryable, hint = self._classify_http_error(exc.code)
            return AnaHidroClientError(
                f"ANA HidroWebService {connection_label} failed ({exc.code}): {message}",
                category=category,
                retryable=retryable,
                hint=hint,
            )

        def on_url_error(exc: URLError) -> AnaHidroClientError:
            category, hint = self._classify_url_error_reason(exc.reason)
            return AnaHidroClientError(
                f"Could not connect to ANA HidroWebService ({connection_label}): "
                f"{self._redact(str(exc.reason), secret)}",
                category=category,
                retryable=True,
                hint=hint,
            )

        def on_timeout(exc: Exception) -> AnaHidroClientError:
            return AnaHidroClientError(
                f"ANA HidroWebService {connection_label} timed out after "
                f"{self.timeout_seconds} seconds",
                category="timeout",
                retryable=True,
                hint="Retry with a narrower date window if the service is slow.",
            )

        def send() -> Dict[str, object]:
            raw_bytes, headers = open_response(
                lambda req, timeout: urlopen(req, timeout=timeout),
                request,
                timeout=self.timeout_seconds,
                on_http_error=on_http_error,
                on_url_error=on_url_error,
                on_timeout=on_timeout,
            )
            content_type = ""
            if headers is not None:
                content_type = str(headers.get("Content-Type", "")).lower()
            return decode_json_mapping(
                raw_bytes,
                content_type=content_type,
                error_cls=AnaHidroClientError,
                service_label="ANA HidroWebService",
                non_json_hint=(
                    "Check the base URL and endpoint path; valid base is "
                    "https://www.ana.gov.br/hidrowebservice."
                ),
            )

        return request_with_retry(send, max_attempts=self.max_attempts)

    @staticmethod
    def _redact(text: str, secret: str) -> str:
        if secret and secret in text:
            return text.replace(secret, "***")
        return text

    @staticmethod
    def _classify_http_error(code: int) -> tuple[str, bool, str]:
        category, retryable = classify_http_status(
            code, configuration_codes=frozenset({400, 401, 404, 406, 417})
        )
        if code == 401:
            hint = (
                "Check GUARACI_ANA_ID/GUARACI_ANA_SENHA and that the token "
                "was not revoked; the client already retries once after "
                "re-authenticating."
            )
        elif code in {400, 406, 417}:
            hint = "Check the station code, date filters, and range parameters."
        elif code == 404:
            hint = "Check the base URL and endpoint path."
        elif retryable:
            hint = "Retry later; the ANA HidroWebService may be busy."
        else:
            hint = "Check request parameters and endpoint compatibility before retrying."
        return category, retryable, hint

    @staticmethod
    def _classify_url_error_reason(reason: object) -> tuple[str, str]:
        if is_timeout_reason(reason):
            return (
                "timeout",
                "Retry with a narrower date window if the service remains slow.",
            )
        return (
            "connectivity",
            "Check internet access, DNS resolution, and firewall/proxy rules.",
        )

    @staticmethod
    def _extract_http_error_message(exc: HTTPError) -> str:
        return read_http_error_body(exc)
