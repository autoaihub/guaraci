"""Conectores da CETESB (qualidade do ar do estado de São Paulo).

Dois caminhos, deliberadamente separados, porque entregam medidas diferentes:

- o ArcGIS público (:mod:`guaraci.cetesb.client`), sem credencial, que entrega
  o ÍNDICE de qualidade do ar das últimas 48 horas;
- o QUALAR clássico (:mod:`guaraci.cetesb.qualar_client`), com login, que
  entrega CONCENTRAÇÃO medida em série histórica.

Confundir os dois é o erro mais fácil de cometer aqui, e o mais caro: índice é
transformação por faixas e não serve para dose-resposta.
"""

from guaraci.cetesb.client import (
    HOURS_PER_WINDOW,
    POLLUTANT_LAYERS,
    STATION_LAYER,
    CetesbClientError,
    CetesbQualarClient,
    epoch_ms_to_local_naive,
)
from guaraci.cetesb.horario import CetesbQualarHorarioDataSource
from guaraci.cetesb.qualar import CetesbEstacoesDataSource, CetesbQualarDataSource
from guaraci.cetesb.qualar_client import CetesbAuthError, QualarClient

__all__ = [
    "CetesbQualarClient",
    "CetesbClientError",
    "CetesbAuthError",
    "QualarClient",
    "CetesbQualarDataSource",
    "CetesbEstacoesDataSource",
    "CetesbQualarHorarioDataSource",
    "POLLUTANT_LAYERS",
    "STATION_LAYER",
    "HOURS_PER_WINDOW",
    "epoch_ms_to_local_naive",
]
