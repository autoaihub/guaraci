"""Fontes de saúde por arquivo HTTP da leva 7: IARC (CI5-XII), inquéritos nacionais (SB Brasil,
PNDS 2006, Covitel) e Cetic.br (TIC Saúde e TIC Domicílios).

Cada pacote traz ``SPECS`` e ``MODES`` (e ``DATASOURCES`` quando a exportação usa leitor próprio);
o descritor sai do mesmo ``http_file_source`` das demais fontes de arquivo.
"""

from typing import List

from guaraci.cetic import tic
from guaraci.iarc import ci5, monografias
from guaraci.inqueritos import covitel, pnds, sb_brasil
from guaraci.services.downloads import DownloadSource
from guaraci.services.sources.arquivos import http_file_source

_MODULES = (ci5, monografias, sb_brasil, pnds, covitel, tic)


def build_sources() -> List[DownloadSource]:
    return [
        http_file_source(
            spec, module.MODES[spec.key], getattr(module, "DATASOURCES", {}).get(spec.key)
        )
        for module in _MODULES
        for spec in module.SPECS
    ]
