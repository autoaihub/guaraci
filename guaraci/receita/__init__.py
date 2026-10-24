"""CNPJ aberto da Receita Federal por WebDAV."""

from guaraci.receita.cnpj import CNPJ_FILES, CNPJ_TABELAS, CnpjDataSource, datasource_for
from guaraci.receita.webdav import (
    DEFAULT_TOKEN,
    DavEntry,
    ReceitaWebDavClient,
    ReceitaWebDavError,
)

__all__ = [
    "CNPJ_FILES",
    "CNPJ_TABELAS",
    "CnpjDataSource",
    "DEFAULT_TOKEN",
    "DavEntry",
    "ReceitaWebDavClient",
    "ReceitaWebDavError",
    "datasource_for",
]
