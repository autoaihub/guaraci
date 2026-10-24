"""Fontes de arquivos HTTP de URL fixa (Vigitel, IBAMA, Farmácia Popular, MGDI, PNI, SISVAN)."""

from typing import Dict, List, Optional, Sequence, Tuple

from guaraci.arquivos import (
    HTTP_FILES,
    HttpFile,
    HttpFileClient,
    datasource_for,
    datasource_for_spec,
    cgu,
    ibama,
    ibge_ftp,
    inep_ideb,
    mapbiomas,
    seguranca,
    transito_sp,
)
from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)

_MODES = {
    "vigitel": "svs files",
    "ibama_agrotoxicos_comercializacao": "ibama files",
    "farmacia_popular_indicadores": "demas s3 files",
    "mgdi_samu": "demas s3 files",
    "mgdi_upa": "demas s3 files",
    "mgdi_raps": "demas s3 files",
    "mgdi_emulti": "demas s3 files",
    "mgdi_academia_saude": "demas s3 files",
    "mgdi_telessaude": "demas s3 files",
    "mgdi_saude_bucal": "demas s3 files",
    "pni_doses_aplicadas_arquivos": "demas s3 files",
    "sisvan_estado_nutricional_arquivos": "demas s3 files",
    "ibama_rapp_emissoes_atmosfericas": "ibama files",
    "ibama_rapp_efluentes_liquidos": "ibama files",
    "inpe_area_queimada_biomas": "inpe files",
    "inpe_sisam": "inpe files",
    "pni_cobertura_vacinal_residencia": "datasus ftp file",
    "mgdi_cancer_colo_mama": "demas s3 files",
    "mgdi_cirurgias_especialistas": "demas s3 files",
    "mgdi_equidade": "demas s3 files",
    "mgdi_residencias_saude": "demas s3 files",
    "mgdi_rnds": "demas s3 files",
    "mgdi_saude_bucal_fluoretacao": "demas s3 files",
}


# Módulos de ``guaraci/arquivos/`` com spec própria (fora de ``HTTP_FILES``): cada um
# traz ``SPECS`` e ``MODES`` (chave para modo do descritor) e, se precisar, ``DATASOURCES``
# (chave para classe, quando a fonte descobre os arquivos em tempo de execução) e
# ``EXTRA_PARAMS`` (chave para parâmetros além dos que a spec já gera).
_EXTRA_MODULES = (ibama, seguranca, transito_sp, ibge_ftp, inep_ideb, mapbiomas, cgu)


def _extra_specs() -> List[Tuple[HttpFile, str, Optional[type], Sequence[SourceParameterSpec]]]:
    return [
        (
            spec,
            module.MODES[spec.key],
            getattr(module, "DATASOURCES", {}).get(spec.key),
            getattr(module, "EXTRA_PARAMS", {}).get(spec.key, ()),
        )
        for module in _EXTRA_MODULES
        for spec in module.SPECS
    ]


def _params(key: str) -> List[SourceParameterSpec]:
    return _params_for(HTTP_FILES[key])


def _params_for(spec: HttpFile) -> List[SourceParameterSpec]:
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
            description=(
                "Exporta em CSV UTF-8, Parquet ou SQLite, com todas as colunas "
                "como texto e nomes de coluna como publicados. Omita para guardar "
                "o arquivo como a fonte publica."
            ),
            required=False,
            default=None,
            allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="keep_raw",
            phase="tecnica",
            param_type="boolean",
            description="Se true, mantém o arquivo original além da exportação.",
            required=False,
            default=False,
        ),
        SourceParameterSpec(
            name="timeout",
            phase="tecnica",
            param_type="integer",
            description="HTTP timeout in seconds.",
            required=False,
            default=HttpFileClient.DEFAULT_TIMEOUT,
            minimum=1,
        ),
    ]
    if spec.selector == "indicadores":
        codes = [r.code for r in spec.resources]
        params.insert(
            0,
            SourceParameterSpec(
                name="indicadores",
                phase="coleta",
                param_type="string_list",
                description=(
                    "Códigos dos indicadores (um CSV por indicador). Omita para "
                    f"baixar todos os {len(codes)}."
                ),
                required=False,
                default=None,
                allowed_values=codes,
            ),
        )
    if spec.selector == "periodo":
        years = sorted({r.code.split("_")[0] for r in spec.resources})
        if spec.anos_label:
            anos_text = spec.anos_label
        elif spec.period_required:
            anos_text = (
                "Anos a baixar (obrigatório). Cada arquivo tem de 0,4 a 4,4 GB "
                "comprimidos, então peça poucos anos por vez."
            )
        else:
            anos_text = "Anos a baixar. Omita para baixar todos os anos publicados."
        params.insert(
            0,
            SourceParameterSpec(
                name="anos",
                phase="coleta",
                param_type="string_list",
                description=anos_text,
                required=spec.period_required,
                default=[years[-1]] if spec.period_required else None,
                allowed_values=years,
            ),
        )
        subperiods = sorted(
            {r.code.partition("_")[2] for r in spec.resources if "_" in r.code}
        )
        if subperiods:
            numeric = all(s.isdigit() for s in subperiods)
            params.insert(
                1,
                SourceParameterSpec(
                    name="meses",
                    phase="coleta",
                    param_type="string_list",
                    description=(
                        "Meses (01 a 12) dentro dos anos pedidos. Omita para o ano inteiro."
                        if numeric
                        else spec.subperiod_label
                        or "Semestres (S1, S2) ou trimestres (T3) dentro dos anos pedidos. "
                        "Omita para todos."
                    ),
                    required=False,
                    default=None,
                    allowed_values=[f"{m:02d}" for m in range(1, 13)] if numeric else subperiods,
                ),
            )
        if spec.year_window:
            for name, text in (
                ("start_year", "Primeiro ano da janela (recorte do orquestrador)."),
                ("end_year", "Último ano da janela; sem ele vale só o ano inicial."),
            ):
                params.append(
                    SourceParameterSpec(
                        name=name,
                        phase="coleta",
                        param_type="integer",
                        description=text,
                        required=False,
                        default=None,
                        minimum=int(years[0]),
                    )
                )
    return params


def http_file_source(
    spec: HttpFile,
    mode: str,
    datasource_cls: Optional[type] = None,
    extra_params: Sequence[SourceParameterSpec] = (),
) -> ApiDownloadSource:
    """Registra spec que não está em ``HTTP_FILES`` (módulos novos de ``guaraci/arquivos/``)."""
    return ApiDownloadSource(
        descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=mode),
        datasource_cls=datasource_cls or datasource_for_spec(spec),
        params_schema=[*_params_for(spec), *extra_params],
    )


def build_sources() -> List[DownloadSource]:
    """Fontes de arquivo HTTP: as de ``HTTP_FILES`` e, depois, as dos módulos próprios."""
    sources: List[DownloadSource] = [
        ApiDownloadSource(
            descriptor=SourceDescriptor(source=spec.key, title=spec.title, mode=_MODES[spec.key]),
            datasource_cls=datasource_for(spec.key),
            params_schema=_params(spec.key),
        )
        for spec in HTTP_FILES.values()
    ]
    sources.extend(
        http_file_source(spec, mode, cls, extra) for spec, mode, cls, extra in _extra_specs()
    )
    return sources
