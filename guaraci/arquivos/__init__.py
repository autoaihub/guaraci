"""Arquivos de dados abertos servidos por HTTP em URL fixa (Vigitel, IBAMA, Farmácia Popular)."""

from guaraci.arquivos.http_files import (
    FARMACIA_INDICADORES,
    HTTP_FILES,
    HttpFile,
    HttpFileClient,
    HttpFileClientError,
    HttpFileDataSource,
    HttpResource,
    RemoteFile,
    datasource_for,
)

__all__ = [
    "FARMACIA_INDICADORES",
    "HTTP_FILES",
    "HttpFile",
    "HttpFileClient",
    "HttpFileClientError",
    "HttpFileDataSource",
    "HttpResource",
    "RemoteFile",
    "datasource_for",
]
