"""Funcoes de normalizacao de parametros das fontes de download.

Movidas de ``guaraci/services/downloads.py``. Este modulo nao importa nada
do pacote ``guaraci``, entao pode ser importado cedo sem risco de ciclo;
``downloads.py`` reexporta estes nomes para compatibilidade (o registry
gerado importa ``_normalize_opendatasus_params`` de la).
"""

from __future__ import annotations

from typing import Dict


def _normalize_sinan_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)
    diseases = normalized.get("diseases")
    if isinstance(diseases, list):
        normalized["diseases"] = [str(item).strip().upper() for item in diseases if str(item).strip()]
    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None
    sexo = normalized.get("sexo")
    if isinstance(sexo, str):
        normalized["sexo"] = sexo.strip().upper()
    uf = normalized.get("uf")
    if isinstance(uf, str):
        normalized["uf"] = uf.strip().upper()
    return normalized


def _normalize_ftp_params(params: Dict[str, object]) -> Dict[str, object]:
    """Normalise params for the phase-5 generic FTP DATASUS sources."""
    normalized = dict(params)
    for key in ("groups", "states"):
        value = normalized.get(key)
        if isinstance(value, list):
            normalized[key] = [
                str(item).strip().upper() for item in value if str(item).strip()
            ]
    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None
    return normalized


def _normalize_sim_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)
    groups = normalized.get("groups")
    states = normalized.get("states")
    if isinstance(groups, list):
        normalized["groups"] = [str(item).strip().upper() for item in groups if str(item).strip()]
    if isinstance(states, list):
        normalized["states"] = [str(item).strip().upper() for item in states if str(item).strip()]
    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None
    sexo = normalized.get("sexo")
    if isinstance(sexo, str):
        normalized["sexo"] = sexo.strip().upper()
    uf = normalized.get("uf")
    if isinstance(uf, str):
        normalized["uf"] = uf.strip().upper()
    return normalized


def _normalize_sih_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = _normalize_sim_params(params)
    months = normalized.get("months")
    if isinstance(months, list):
        parsed = []
        for item in months:
            raw = str(item).strip()
            if raw:
                parsed.append(int(raw))
        normalized["months"] = parsed
    mes = normalized.get("mes")
    if mes is not None:
        normalized["mes"] = int(mes)
    return normalized


def _normalize_opendatasus_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)
    dataset = normalized.get("dataset")
    if isinstance(dataset, str):
        normalized["dataset"] = dataset.strip().lower()

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    uf = normalized.get("uf")
    if isinstance(uf, str):
        cleaned_uf = uf.strip().upper()
        normalized["uf"] = cleaned_uf if cleaned_uf else None

    uf_like_keys = {
        "sg_uf",
        "sg_uf_not",
        "uf_notificacao",
        "uf_residencia",
        "uf_paciente",
        "uf_estabelecimento",
        "sigla_unidade_federacao",
    }
    for key, value in list(normalized.items()):
        if key in {
            "dataset",
            "output_format",
            "uf",
            "start_date",
            "end_date",
            "resource_id",
            "api_base_url",
        }:
            continue
        if isinstance(value, str):
            cleaned_value = value.strip()
            if not cleaned_value:
                normalized[key] = None
            elif key in uf_like_keys:
                normalized[key] = cleaned_value.upper()
            else:
                normalized[key] = cleaned_value

    for key in ("start_date", "end_date", "resource_id", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned_value = value.strip()
            normalized[key] = cleaned_value if cleaned_value else None

    for key in ("start_year", "end_year", "batch_size", "max_pages"):
        value = normalized.get(key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                normalized[key] = None
                continue
            normalized[key] = int(stripped)
            continue
        normalized[key] = int(value)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_ibge_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    for key in ("level", "sexo", "faixa_etaria"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                normalized[key] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    api_base_url = normalized.get("api_base_url")
    if isinstance(api_base_url, str):
        normalized["api_base_url"] = api_base_url.strip() or None

    for key in ("start_year", "end_year"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            try:
                normalized[key] = int(value.strip())
            except ValueError:
                pass

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            try:
                normalized["timeout"] = int(stripped)
            except ValueError:
                normalized.pop("timeout", None)
        else:
            normalized.pop("timeout", None)

    return normalized


def _normalize_nasa_power_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    parameters = normalized.get("parameters")
    if isinstance(parameters, list):
        normalized["parameters"] = [
            str(item).strip().upper() for item in parameters if str(item).strip()
        ]

    temporal = normalized.get("temporal")
    if isinstance(temporal, str):
        cleaned = temporal.strip().lower()
        if cleaned:
            normalized["temporal"] = cleaned

    community = normalized.get("community")
    if isinstance(community, str):
        cleaned = community.strip().upper()
        if cleaned:
            normalized["community"] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    for key in ("latitude", "longitude", "start_date", "end_date", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            normalized[key] = cleaned if cleaned else None

    # Empty/invalid timeout is dropped so the datasource default applies; a
    # None timeout would break the int() coercion in the client resolver.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            normalized["timeout"] = int(stripped)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_nasa_firms_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    product = normalized.get("product")
    if isinstance(product, str):
        cleaned = product.strip().upper()
        if cleaned:
            normalized["product"] = cleaned

    country = normalized.get("country")
    if isinstance(country, str):
        cleaned = country.strip().upper()
        if cleaned:
            normalized["country"] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    for key in ("area", "start_date", "end_date", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            normalized[key] = cleaned if cleaned else None

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            normalized["timeout"] = int(stripped)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_inmet_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    for key in ("ufs", "variables"):
        value = normalized.get(key)
        if isinstance(value, list):
            transform = str.upper if key == "ufs" else str.lower
            normalized[key] = [
                transform(str(item).strip()) for item in value if str(item).strip()
            ]

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    api_base_url = normalized.get("api_base_url")
    if isinstance(api_base_url, str):
        normalized["api_base_url"] = api_base_url.strip() or None

    for key in ("start_year", "end_year"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            try:
                normalized[key] = int(value.strip())
            except ValueError:
                pass

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            try:
                normalized["timeout"] = int(stripped)
            except ValueError:
                normalized.pop("timeout", None)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized


def _normalize_nasa_gpm_params(params: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(params)

    product = normalized.get("product")
    if isinstance(product, str):
        cleaned = product.strip().lower()
        if cleaned:
            normalized["product"] = cleaned

    variable = normalized.get("variable")
    if isinstance(variable, str):
        cleaned = variable.strip()
        if cleaned:
            normalized["variable"] = cleaned

    output_format = normalized.get("output_format")
    if isinstance(output_format, str):
        cleaned = output_format.strip().lower()
        normalized["output_format"] = cleaned if cleaned else None

    for key in ("latitude", "longitude", "start_date", "end_date", "api_base_url"):
        value = normalized.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            normalized[key] = cleaned if cleaned else None

    # Empty/invalid timeout is dropped so the datasource default applies.
    timeout = normalized.get("timeout")
    if isinstance(timeout, str):
        stripped = timeout.strip()
        if stripped:
            normalized["timeout"] = int(stripped)
        else:
            normalized.pop("timeout", None)
    elif isinstance(timeout, bool):
        normalized.pop("timeout", None)
    elif isinstance(timeout, (int, float)):
        normalized["timeout"] = int(timeout)

    keep_raw = normalized.get("keep_raw")
    if isinstance(keep_raw, str):
        lowered = keep_raw.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            normalized["keep_raw"] = True
        elif lowered in {"0", "false", "no", "n", "off", ""}:
            normalized["keep_raw"] = False
    elif keep_raw is not None:
        normalized["keep_raw"] = bool(keep_raw)

    return normalized
