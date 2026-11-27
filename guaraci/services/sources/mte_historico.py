"""Fontes históricas do MTE: RAIS de 1985 a 2022 e CAGED antigo (2002 a 2019)."""

from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.mte.caged_antigo import CAGED_ANTIGO_FILES
from guaraci.mte.caged_antigo import datasource_for as caged_antigo_datasource_for
from guaraci.mte.rais import HIST_MAX_YEAR, HIST_MIN_YEAR, RAIS_HISTORICO_FILES, RAIS_REGIOES, RAIS_UFS
from guaraci.mte.rais import historico_datasource_for
from guaraci.services.downloads import ApiDownloadSource, DownloadSource, SourceDescriptor
from guaraci.services.sources.mte import _MODE, _common


def _rais_params(key: str) -> List[SourceParameterSpec]:
    years = [str(y) for y in range(HIST_MIN_YEAR, HIST_MAX_YEAR + 1)]
    params = [
        SourceParameterSpec(
            name="anos",
            phase="coleta",
            param_type="string_list",
            description=(
                f"Anos ({HIST_MIN_YEAR} a {HIST_MAX_YEAR}). Informe 'anos' ou "
                "start_year/end_year: os anos recentes passam de 2 GB comprimidos."
            ),
            required=False,
            default=None,
            allowed_values=years,
        ),
        SourceParameterSpec(
            name="start_year",
            phase="coleta",
            param_type="integer",
            description=f"Ano inicial (desde {HIST_MIN_YEAR}).",
            required=False,
            default=None,
            minimum=HIST_MIN_YEAR,
            maximum=HIST_MAX_YEAR,
        ),
        SourceParameterSpec(
            name="end_year",
            phase="coleta",
            param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False,
            default=None,
            minimum=HIST_MIN_YEAR,
            maximum=HIST_MAX_YEAR,
        ),
    ]
    if key == "mte_rais_vinculos_historico":
        params.extend(
            [
                SourceParameterSpec(
                    name="ufs",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "UFs dos vínculos até 2017 (um CSV por UF; 'IGNORADOS' reúne os sem "
                        "UF). Omita para todas."
                    ),
                    required=False,
                    default=None,
                    allowed_values=list(RAIS_UFS),
                ),
                SourceParameterSpec(
                    name="regioes",
                    phase="coleta",
                    param_type="string_list",
                    description="Regiões dos vínculos de 2018 em diante. Omita para todas.",
                    required=False,
                    default=None,
                    allowed_values=list(RAIS_REGIOES),
                ),
            ]
        )
    return [*params, *_common()]


def _caged_params() -> List[SourceParameterSpec]:
    return [
        SourceParameterSpec(
            name="anos",
            phase="coleta",
            param_type="string_list",
            description="Anos pedidos; cada mês tem de 20 a 33 MB comprimidos.",
            required=False,
            default=None,
            allowed_values=[str(y) for y in range(2002, 2020)],
        ),
        SourceParameterSpec(
            name="meses",
            phase="coleta",
            param_type="string_list",
            description="Meses (01 a 12) dentro dos anos. Omita para o ano inteiro.",
            required=False,
            default=None,
            allowed_values=[f"{m:02d}" for m in range(1, 13)],
        ),
        SourceParameterSpec(
            name="start_date",
            phase="coleta",
            param_type="string",
            description="Data inicial (`AAAA-MM-DD` ou `DD/MM/AAAA`); vale o mês dela.",
            required=False,
            default=None,
        ),
        SourceParameterSpec(
            name="end_date",
            phase="coleta",
            param_type="string",
            description="Data final; padrão: a data inicial.",
            required=False,
            default=None,
        ),
        *_common(),
    ]


def build_sources() -> List[DownloadSource]:
    sources: List[DownloadSource] = [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODE),
            datasource_cls=historico_datasource_for(spec.key),
            params_schema=_rais_params(spec.key),
        )
        for spec in RAIS_HISTORICO_FILES.values()
    ]
    sources.extend(
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODE),
            datasource_cls=caged_antigo_datasource_for(spec.key),
            params_schema=_caged_params(),
        )
        for spec in CAGED_ANTIGO_FILES.values()
    )
    return sources
