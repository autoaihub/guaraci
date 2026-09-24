"""Tabelas de código do QUALAR: estações e parâmetros.

O QUALAR identifica estação e parâmetro por código numérico, e esses códigos
não estão publicados em lugar nenhum fora do próprio sistema: as listas vivem
nos ``<select>`` do formulário, atrás do login. Sem elas, o conector
autenticado não tem como montar uma requisição.

Procedência: as tabelas vêm do pacote R `qualR` (rOpenSci, MIT), arquivos
``data-raw/cetesb_qualR.dat``, ``data-raw/cetesb_aqs.dat`` e
``data-raw/cetesb_variables.dat``, em https://github.com/ropensci/qualR .
São dados factuais produzidos pela CETESB, e o qualR é MIT como o Guaraci,
então não há conflito de licença; o crédito fica registrado aqui de todo modo.

ATENÇÃO ao numerar estações: o código do QUALAR NÃO é o campo ``ID`` da camada
de estações do ArcGIS. Pinheiros é 99 aqui e 42 lá. São numerações
independentes, e trocar uma pela outra devolve dados de outra estação sem erro
nenhum. A ligação entre os dois cadastros é feita pelo NOME da estação.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

__all__ = [
    "Station",
    "Parameter",
    "STATIONS",
    "PARAMETERS",
    "POLLUTANT_CODES",
    "METEOROLOGY_CODES",
    "resolve_station",
    "resolve_parameter",
    "station_names",
    "parameter_names",
]


@dataclass(frozen=True)
class Station:
    """Uma estação de monitoramento, como o QUALAR a numera."""

    code: int
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    region: Optional[str] = None


@dataclass(frozen=True)
class Parameter:
    """Um parâmetro medido: poluente ou variável meteorológica."""

    code: int
    abbreviation: str
    description: str
    meteorological: bool = False


_PARAMETER_LIST: Tuple[Parameter, ...] = (
    Parameter(61, 'BEN', 'Benzeno', False),
    Parameter(16, 'CO', 'Monoxido de Carbono', False),
    Parameter(23, 'DV', 'Direcao do Vento', True),
    Parameter(21, 'DVG', 'Direcao do Vento Global', True),
    Parameter(19, 'ERT', 'Enxofre Reduzido Total', False),
    Parameter(59, 'HCNM', 'Hidrocarbonetos Totais menos Metano', False),
    Parameter(12, 'MP10', 'Particulas Inalaveis', False),
    Parameter(57, 'MP2.5', 'Particulas Inalaveis Finas', False),
    Parameter(17, 'NO', 'Monoxido de Nitrogenio', False),
    Parameter(15, 'NO2', 'Dioxido de Nitrogenio', False),
    Parameter(18, 'NOx', 'Oxidos de Nitrogenio', False),
    Parameter(63, 'O3', 'Ozonio', False),
    Parameter(29, 'PRESS', 'Pressao Atmosferica', True),
    Parameter(26, 'RADG', 'Radiacao Solar Global', True),
    Parameter(56, 'RADUV', 'Radiacao Ultra-violeta', True),
    Parameter(13, 'SO2', 'Dioxido de Enxofre', False),
    Parameter(25, 'TEMP', 'Temperatura do Ar', True),
    Parameter(62, 'TOL', 'Tolueno', False),
    Parameter(28, 'UR', 'Umidade Relativa do Ar', True),
    Parameter(24, 'VV', 'Velocidade do Vento', True),
)

_STATION_LIST: Tuple[Station, ...] = (
    Station(290, 'Americana', -22.724253, -47.339549, 'Interior'),
    Station(105, 'Americana-Vila Sta Maria'),
    Station(106, 'Araraquara', -21.782522, -48.185832, 'Interior'),
    Station(107, 'Araçatuba', -21.186841, -50.439317, 'Interior'),
    Station(108, 'Bauru', -22.326608, -49.092759, 'Interior'),
    Station(90, 'Cambuci', -23.567708, -46.612273, 'NA'),
    Station(89, 'Campinas-Centro', -22.902525, -47.057211, 'Interior'),
    Station(276, 'Campinas-Taquaral', -22.874619, -47.058973, 'Interior'),
    Station(275, 'Campinas-V.União', -22.946728, -47.119281, 'Interior'),
    Station(269, 'Capão Redondo', -23.668356, -46.780043, 'São Paulo'),
    Station(263, 'Carapicuíba', -23.531395, -46.835780, 'MASP'),
    Station(248, 'Catanduva', -21.141943, -48.983075, 'Interior'),
    Station(94, 'Centro', -23.547806, -46.642414, 'NA'),
    Station(91, 'Cerqueira César', -23.553543, -46.672705, 'São Paulo'),
    Station(95, 'Cid.Universitária-USP-Ipen', -23.566342, -46.737414, 'São Paulo'),
    Station(73, 'Congonhas', -23.616320, -46.663466, 'São Paulo'),
    Station(87, 'Cubatão-Centro', -23.879027, -46.418483, 'Coast'),
    Station(66, 'Cubatão-V.Parisi', -23.849416, -46.388676, 'Coast'),
    Station(119, 'Cubatão-Vale do Mogi', -23.831589, -46.369569, 'Coast'),
    Station(92, 'Diadema', -23.685876, -46.611622, 'MASP'),
    Station(98, 'Grajaú-Parelheiros', -23.776266, -46.696961, 'São Paulo'),
    Station(289, 'Guaratinguetá', -22.801917, -45.191122, 'Interior'),
    Station(118, 'Guarulhos', -23.463209, -46.496214, 'MASP'),
    Station(264, 'Guarulhos-Paço Municipal', -23.455534, -46.518533, 'MASP'),
    Station(279, 'Guarulhos-Pimentas', -23.440117, -46.409949, 'MASP'),
    Station(83, 'Ibirapuera', -23.591842, -46.660688, 'São Paulo'),
    Station(262, 'Interlagos', -23.680508, -46.675043, 'São Paulo'),
    Station(266, 'Itaim Paulista', -23.501547, -46.420737, 'São Paulo'),
    Station(97, 'Itaquera', -23.580015, -46.466651, 'São Paulo'),
    Station(259, 'Jacareí', -23.294199, -45.968234, 'Interior'),
    Station(110, 'Jaú', -22.298620, -48.567457, 'Interior'),
    Station(109, 'Jundiaí', -23.192004, -46.897097, 'Interior'),
    Station(84, 'Lapa'),
    Station(281, 'Limeira', -22.563604, -47.414314, 'Interior'),
    Station(270, 'Marg.Tietê-Pte Remédios', -23.518706, -46.743320, 'São Paulo'),
    Station(111, 'Marília', -22.199809, -49.959970, 'Interior'),
    Station(65, 'Mauá', -23.668549, -46.466000, 'MASP'),
    Station(287, 'Mogi das Cruzes', -23.518172, -46.186861, 'NA'),
    Station(85, 'Mooca', -23.549734, -46.600417, 'São Paulo'),
    Station(96, 'N.Senhora do Ó', -23.480099, -46.692052, 'São Paulo'),
    Station(120, 'Osasco', -23.526721, -46.792078, 'MASP'),
    Station(72, 'Parque D.Pedro II', -23.544846, -46.627676, 'São Paulo'),
    Station(117, 'Paulínia', -22.772321, -47.154843, 'Interior'),
    Station(112, 'Paulínia Sul', -22.786806, -47.136559, 'Interior'),
    Station(291, 'Paulínia-Sta Terezinha'),
    Station(293, 'Perus'),
    Station(284, 'Pico do Jaraguá', -23.456269, -46.766098, 'São Paulo'),
    Station(99, 'Pinheiros', -23.561460, -46.702017, 'São Paulo'),
    Station(113, 'Piracicaba', -22.701222, -47.649653, 'Interior'),
    Station(268, 'Pirassununga-EM', -22.007713, -47.427564, 'NA'),
    Station(114, 'Presidente Prudente', -22.119937, -51.408777, 'NA'),
    Station(288, 'Ribeirão Preto', -21.153942, -47.828481, 'Interior'),
    Station(115, 'Ribeirão Preto-Ipiranga', -21.153940, -47.828480, 'Interior'),
    Station(292, 'Rio Claro-Jd.Guanabara'),
    Station(100, 'S.André Capuava', -23.639804, -46.491637, 'MASP'),
    Station(101, 'S.André-Centro', -23.645616, -46.536335, 'MASP'),
    Station(254, 'S.André-Paço Municipal', -23.656994, -46.530919, 'NA'),
    Station(272, 'S.Bernardo-Centro', -23.698671, -46.546232, 'MASP'),
    Station(102, 'S.Bernardo-Paulicéia', -23.671354, -46.584668, 'MASP'),
    Station(88, 'S.José Campos', -23.187887, -45.871198, 'Interior'),
    Station(277, 'S.José Campos-Jd.Satélite', -23.223645, -45.890800, 'Interior'),
    Station(278, 'S.José Campos-Vista Verde', -23.183697, -45.830897, 'Interior'),
    Station(236, 'S.Miguel Paulista', -23.498526, -46.444803, 'NA'),
    Station(273, 'Santa Gertrudes', -22.459955, -47.536298, 'Interior'),
    Station(63, 'Santana', -23.505993, -46.628960, 'São Paulo'),
    Station(64, 'Santo Amaro', -23.654977, -46.709998, 'São Paulo'),
    Station(258, 'Santos', -23.963057, -46.321170, 'Coast'),
    Station(260, 'Santos-Ponta da Praia', -23.981295, -46.300510, 'Coast'),
    Station(67, 'Sorocaba', -23.502427, -47.479030, 'Interior'),
    Station(86, 'São Caetano do Sul', -23.618443, -46.556354, 'MASP'),
    Station(116, 'São José Do Rio Preto', -20.784689, -49.398278, 'Interior'),
    Station(294, 'São Sebastião'),
    Station(103, 'Taboão da Serra', -23.609324, -46.758294, 'MASP'),
    Station(256, 'Tatuí', -23.360752, -47.870799, 'Interior'),
    Station(280, 'Taubaté', -23.032351, -45.575805, 'Interior'),
)


STATIONS: Mapping[int, Station] = {item.code: item for item in _STATION_LIST}
PARAMETERS: Mapping[int, Parameter] = {item.code: item for item in _PARAMETER_LIST}

POLLUTANT_CODES: Tuple[int, ...] = tuple(
    item.code for item in _PARAMETER_LIST if not item.meteorological
)
METEOROLOGY_CODES: Tuple[int, ...] = tuple(
    item.code for item in _PARAMETER_LIST if item.meteorological
)

# Índices de busca por nome. A chave é o nome dobrado para minúsculas e sem
# espaço nas pontas; acentos são PRESERVADOS, porque é assim que a CETESB
# escreve ("Cerqueira César") e normalizar acento aqui só criaria uma segunda
# grafia para manter em dia.
_STATIONS_BY_NAME: Mapping[str, Station] = {
    item.name.casefold(): item for item in _STATION_LIST
}
_PARAMETERS_BY_NAME: Mapping[str, Parameter] = {
    item.abbreviation.casefold(): item for item in _PARAMETER_LIST
}

# Grafias alternativas que aparecem em qualquer planilha do assunto.
_PARAMETER_ALIASES: Mapping[str, str] = {
    "mp25": "mp2.5",
    "mp2_5": "mp2.5",
    "pm2.5": "mp2.5",
    "pm25": "mp2.5",
    "pm10": "mp10",
    "nox": "nox",
    "o₃": "o3",
}


def resolve_station(value: object) -> Station:
    """Resolve uma estação por código ou por nome.

    Aceita as duas formas porque quem monta o pedido à mão pensa em nome
    ("Pinheiros") e quem automatiza já tem o código. Um nome desconhecido
    levanta erro com a lista, em vez de devolver dados de outra estação.
    """
    if isinstance(value, Station):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("Station cannot be empty.")
    if text.isdigit():
        station = STATIONS.get(int(text))
        if station is None:
            raise ValueError(
                f"Unknown QUALAR station code {text}. "
                "Use guaraci.cetesb.codes.STATIONS to list the valid codes."
            )
        return station
    station = _STATIONS_BY_NAME.get(text.casefold())
    if station is None:
        raise ValueError(
            f"Unknown QUALAR station {text!r}. Names follow the CETESB "
            "spelling, accents included (e.g. 'Cerqueira César')."
        )
    return station


def resolve_parameter(value: object) -> Parameter:
    """Resolve um parâmetro por código ou por abreviação, com aliases."""
    if isinstance(value, Parameter):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("Parameter cannot be empty.")
    if text.isdigit():
        parameter = PARAMETERS.get(int(text))
        if parameter is None:
            raise ValueError(
                f"Unknown QUALAR parameter code {text}. "
                "Use guaraci.cetesb.codes.PARAMETERS to list the valid codes."
            )
        return parameter
    key = text.casefold()
    key = _PARAMETER_ALIASES.get(key, key)
    parameter = _PARAMETERS_BY_NAME.get(key)
    if parameter is None:
        allowed = ", ".join(sorted(item.abbreviation for item in _PARAMETER_LIST))
        raise ValueError(f"Unknown QUALAR parameter {text!r}. Allowed: {allowed}")
    return parameter


def station_names() -> Tuple[str, ...]:
    """Nomes das estações, em ordem alfabética."""
    return tuple(item.name for item in _STATION_LIST)


def parameter_names() -> Tuple[str, ...]:
    """Abreviações dos parâmetros, em ordem alfabética."""
    return tuple(item.abbreviation for item in _PARAMETER_LIST)
