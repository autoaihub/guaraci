"""Fontes CETESB (qualidade do ar de São Paulo) do registro padrão.

Duas fontes, pelo mesmo motivo que existem dois datasources: a série e o
cadastro respondem perguntas diferentes, e quem quer o mapa das estações não
quer baixar 48 horas de medida junto.

Nota de escopo, repetida aqui de propósito: estas fontes entregam o ÍNDICE de
qualidade do ar, não concentração em µg/m³. A descrição de cada parâmetro e o
título da fonte dizem isso, porque é o tipo de detalhe que se perde entre a
documentação e o uso. Ver :mod:`guaraci.cetesb.client` para a demonstração.
"""

from typing import List

from guaraci.cetesb.client import POLLUTANT_LAYERS
from guaraci.cetesb.codes import parameter_names, station_names
from guaraci.cetesb.horario import DEFAULT_PARAMETERS
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.services.normalizers import _normalize_cetesb_params

_MODE = "cetesb qualar api"


def _common_params(
    *,
    timeout_default: int = _downloads.CetesbQualarDataSource.DEFAULT_TIMEOUT,
    include_municipios: bool = True,
    base_url_description: str = "Optional CETESB ArcGIS MapServer base URL override.",
    raw_description: str = "Se true, salva o JSON bruto do ArcGIS além da exportação.",
) -> List[SourceParameterSpec]:
    """Parâmetros compartilhados pelas fontes CETESB.

    ``include_municipios`` existe porque o filtro por município só faz sentido
    onde a coleta varre a rede inteira. A fonte autenticada consulta estação a
    estação, então quem escolhe já escolheu o município ao escolher a estação,
    e expor o filtro ali seria oferecer um parâmetro que o datasource não
    aceita.
    """
    params = [
        SourceParameterSpec(
            name="output_dir",
            phase="tecnica",
            param_type="string",
            description="Output directory for downloaded files.",
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="output_format",
            phase="exportacao",
            param_type="string",
            description="Optional export format for the parsed table.",
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
    ]
    if include_municipios:
        params.append(
            SourceParameterSpec(
                name="municipios",
                phase="refinamento",
                param_type="string_list",
                description=(
                    "Filtro opcional por município, aplicado após a coleta. A "
                    "CETESB grafa o município em maiúsculas e sem acento (ex.: "
                    "'SAO PAULO'), mas a comparação ignora caixa."
                ),
                required=False,
                default=None,
            )
        )
    params.extend(
        [
            SourceParameterSpec(
                name="keep_raw",
                phase="tecnica",
                param_type="boolean",
                description=raw_description,
                required=False,
                default=False,
            ),
            SourceParameterSpec(
                name="timeout",
                phase="tecnica",
                param_type="integer",
                description="HTTP timeout in seconds.",
                required=False,
                default=timeout_default,
                minimum=1,
            ),
            SourceParameterSpec(
                name="api_base_url",
                phase="tecnica",
                param_type="string",
                description=base_url_description,
                required=False,
                default=None,
            ),
        ]
    )
    return params


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes CETESB na ordem canônica."""
    return [
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="cetesb_qualar",
                title="CETESB QUALAR (Índice de Qualidade do Ar, 48h)",
                mode=_MODE,
            ),
            datasource_cls=_downloads.CetesbQualarDataSource,
            params_schema=[
                SourceParameterSpec(
                    name="pollutants",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Poluentes a coletar (padrão: todos). Os valores são o "
                        "ÍNDICE de qualidade do ar da CETESB, não concentração "
                        "em µg/m³; concentração só pelo QUALAR com login."
                    ),
                    required=False,
                    default=None,
                    allowed_values=list(POLLUTANT_LAYERS),
                ),
                SourceParameterSpec(
                    name="stations",
                    phase="refinamento",
                    param_type="string_list",
                    description=(
                        "Filtro opcional por nome de estação, aplicado após a "
                        "coleta (ex.: 'Cerqueira César'). Ignora caixa. Use a "
                        "fonte 'cetesb_estacoes' para descobrir os nomes."
                    ),
                    required=False,
                    default=None,
                ),
                *_common_params(),
            ],
            normalize_params=_normalize_cetesb_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="cetesb_estacoes",
                title="CETESB (Cadastro das Estações de Monitoramento)",
                mode=_MODE,
            ),
            datasource_cls=_downloads.CetesbEstacoesDataSource,
            params_schema=_common_params(),
            normalize_params=_normalize_cetesb_params,
        ),
        ApiDownloadSource(
            descriptor=SourceDescriptor(
                source="cetesb_qualar_horario",
                title="CETESB QUALAR (Concentração Horária Medida)",
                mode="cetesb qualar auth",
            ),
            datasource_cls=_downloads.CetesbQualarHorarioDataSource,
            params_schema=[
                SourceParameterSpec(
                    name="stations",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Estações a consultar, por nome ou por código do "
                        "QUALAR. Obrigatório: o sistema responde uma estação "
                        "por vez, então não há padrão que faça sentido. "
                        "Atenção: o código do QUALAR NÃO é o 'ID' da fonte "
                        "cetesb_estacoes (Pinheiros é 99 aqui e 42 lá)."
                    ),
                    required=True,
                    default=None,
                    allowed_values=list(station_names()),
                ),
                SourceParameterSpec(
                    name="parameters",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Parâmetros medidos: 12 poluentes e 8 variáveis "
                        "meteorológicas (TEMP, UR, VV, DV, PRESS, RADG…). "
                        "Os valores são CONCENTRAÇÃO na unidade do parâmetro, "
                        "não índice."
                    ),
                    required=False,
                    default=list(DEFAULT_PARAMETERS),
                    allowed_values=list(parameter_names()),
                ),
                SourceParameterSpec(
                    name="start_date",
                    phase="coleta",
                    param_type="string",
                    description="Data inicial (`YYYY-MM-DD` ou `DD/MM/YYYY`).",
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="end_date",
                    phase="coleta",
                    param_type="string",
                    description="Data final (`YYYY-MM-DD` ou `DD/MM/YYYY`).",
                    required=True,
                    default=None,
                ),
                SourceParameterSpec(
                    name="only_validated",
                    phase="refinamento",
                    param_type="boolean",
                    description=(
                        "Se true (padrão), devolve só as leituras que a CETESB "
                        "marcou como validadas. Ponha false para incluir as "
                        "ainda não validadas, que são preliminares."
                    ),
                    required=False,
                    default=True,
                ),
                SourceParameterSpec(
                    name="pause_seconds",
                    phase="tecnica",
                    param_type="integer",
                    description=(
                        "Pausa entre requisições. O QUALAR responde um par "
                        "estação/parâmetro por vez, então uma varredura ampla "
                        "gera centenas de chamadas contra um sistema público "
                        "estadual. Não zere sem motivo."
                    ),
                    required=False,
                    default=int(_downloads.CetesbQualarHorarioDataSource.DEFAULT_PAUSE_SECONDS),
                    minimum=0,
                ),
                *_common_params(
                    timeout_default=_downloads.CetesbQualarHorarioDataSource.DEFAULT_TIMEOUT,
                    include_municipios=False,
                    base_url_description="Optional QUALAR base URL override.",
                    raw_description=(
                        "Se true, salva as leituras cruas em JSON além da exportação."
                    ),
                ),
            ],
            normalize_params=_normalize_cetesb_params,
        ),
    ]
