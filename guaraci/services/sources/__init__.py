"""Specs declarativas das fontes padrao do DownloadService, por familia.

Cada modulo importa os adapters/helpers de ``guaraci.services.downloads`` no
topo (mesmo padrao de ``opendatasus_registry``); por isso este pacote so deve
ser importado tardiamente, dentro de ``DownloadService._default_sources``.
"""

from typing import List

from guaraci.services.downloads import DownloadSource
from guaraci.services.sources import (
    datasus_ftp,
    datasus_pysus,
    govbr,
    ibge,
    nasa,
    opendatasus,
)

__all__ = ["build_default_sources"]


def build_default_sources() -> List[DownloadSource]:
    """Concatena as familias na MESMA ordem historica do literal original.

    A ordem importa: o dedup do registry gerado e a UI dependem dela.
    """
    return [
        *govbr.build_sources(),
        *opendatasus.build_sources(),
        *datasus_pysus.build_sources(),
        *datasus_ftp.build_sources(),
        *nasa.build_sources(),
        *ibge.build_sources(),
    ]
