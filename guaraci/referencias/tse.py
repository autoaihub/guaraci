"""Equivalência de códigos de município entre o TSE e o IBGE.

CKAN ``dadosabertos.tse.jus.br``, conjunto ``codigos-oficiais-de-uf-e-municipios-
segundo-o-tse-e-o-ibge``; o recurso é o zip ``municipio_tse_ibge.zip`` (HTTP 200
em 2026-11-14, 139 KB) com ``municipio_tse_ibge.csv`` (ISO-8859-1, ``;``) e um
``leiame.pdf`` que não entra.
"""

from __future__ import annotations

from guaraci.referencias.zip_csv import ZipCsvDataSource


class TseMunicipiosDataSource(ZipCsvDataSource):
    DATASET = "tse_municipios_ibge"
    URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip"
    ENCODING = "iso-8859-1"

    def stem_for(self, member: str) -> str:
        return self.name
