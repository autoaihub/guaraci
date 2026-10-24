"""Fontes CKAN estaduais e municipais (Recife, Porto Alegre e Minas Gerais).

Usa ``ckan_api_source`` do módulo federal. O registro deste módulo em
``sources/__init__.py`` é do orquestrador.
"""

from typing import List

from guaraci.ckan.estaduais import CKAN_ESTADUAIS
from guaraci.services.downloads import DownloadSource
from guaraci.services.sources.ckan_federal import ckan_api_source


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes CKAN estaduais na ordem de ``CKAN_ESTADUAIS``."""
    return [ckan_api_source(spec) for spec in CKAN_ESTADUAIS.values()]
