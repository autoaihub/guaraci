"""Transporte genérico para tabuladores TabNet clássicos (``tabcgi.exe`` + ``.def``)."""

from guaraci.tabnet.client import (
    RawHttpResponse,
    TabnetClient,
    TabnetClientError,
    parse_raw_response,
)
from guaraci.tabnet.form import ALL_CATEGORIES, TabnetForm, TabnetOption, parse_form
from guaraci.tabnet.saida import PrnTable, TabnetNoTableError, clean_header, parse_prn

__all__ = [
    "ALL_CATEGORIES",
    "PrnTable",
    "RawHttpResponse",
    "TabnetClient",
    "TabnetClientError",
    "TabnetForm",
    "TabnetNoTableError",
    "TabnetOption",
    "clean_header",
    "parse_form",
    "parse_prn",
    "parse_raw_response",
]
