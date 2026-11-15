"""Fontes de saúde do TabNet (SIAB e HIPERDIA) do registro padrão."""

from datetime import datetime
from typing import List

from guaraci.core.contracts import SourceParameterSpec
from guaraci.services.downloads import (
    EXPORT_FORMAT_VALUES,
    ApiDownloadSource,
    DownloadSource,
    SourceDescriptor,
)
from guaraci.tabnet.mensal import TabnetMensalDataSource
from guaraci.tabnet.saude import (
    HiperdiaCadastroDataSource,
    SiabCadastroFamiliarDataSource,
    SiabProducaoMarcadoresDataSource,
    SiabSaneamentoDataSource,
    SiabSituacaoSaudeDataSource,
)

_SIAB = (
    SiabSituacaoSaudeDataSource,
    SiabProducaoMarcadoresDataSource,
    SiabCadastroFamiliarDataSource,
    SiabSaneamentoDataSource,
)


def _normalize(params):
    normalized = dict(params)
    for key in ("start_year", "end_year"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            try:
                normalized[key] = int(value.strip())
            except ValueError:
                pass
    fmt = normalized.get("output_format")
    if isinstance(fmt, str):
        normalized["output_format"] = fmt.strip().lower() or None
    uf = normalized.get("uf")
    if isinstance(uf, str) and not uf.strip():
        normalized["uf"] = None
    return normalized


def _params(cls: type) -> List[SourceParameterSpec]:
    spec = cls.SPEC
    return [
        SourceParameterSpec(
            name="output_dir", phase="tecnica", param_type="string",
            description="Output directory for downloaded files.",
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="output_format", phase="exportacao", param_type="string",
            description="Export format (padrão csv), tudo como texto.",
            required=False, default=None, allowed_values=EXPORT_FORMAT_VALUES,
        ),
        SourceParameterSpec(
            name="start_year", phase="coleta", param_type="integer",
            description=(
                f"Ano inicial (de {spec.min_year} a {spec.max_year}, último ano publicado). "
                "Uma consulta por mês (ou por ano, nos cadastros anuais)"
                + (" e por UF." if spec.per_uf_def else ".")
            ),
            required=True, default=spec.max_year, minimum=spec.min_year,
            maximum=datetime.now().year,
        ),
        SourceParameterSpec(
            name="end_year", phase="coleta", param_type="integer",
            description="Ano final (padrão: igual a start_year).",
            required=False, default=None, minimum=spec.min_year,
            maximum=datetime.now().year,
        ),
        SourceParameterSpec(
            name="uf", phase="refinamento", param_type="string",
            description=(
                "Sigla da UF ou lista separada por vírgula (por exemplo PR ou PR,SC). "
                "Padrão: todas as UFs."
            ),
            required=False, default=None,
        ),
        SourceParameterSpec(
            name="keep_raw", phase="tecnica", param_type="boolean",
            description="Se true, guarda a página HTML de cada consulta como veio do TabNet.",
            required=False, default=False,
        ),
        SourceParameterSpec(
            name="timeout", phase="tecnica", param_type="integer",
            description="Timeout de socket, em segundos.",
            required=False, default=cls.DEFAULT_TIMEOUT, minimum=1,
        ),
        SourceParameterSpec(
            name="base_url", phase="tecnica", param_type="string",
            description="Optional tabcgi.exe URL override.",
            required=False, default=None,
        ),
    ]


def _source(cls: type, mode: str) -> DownloadSource:
    assert issubclass(cls, TabnetMensalDataSource)
    return ApiDownloadSource(
        descriptor=SourceDescriptor(source=cls.SPEC.dataset, title=cls.SPEC.title, mode=mode),
        datasource_cls=cls,
        params_schema=_params(cls),
        normalize_params=_normalize,
    )


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes SIAB e HIPERDIA na ordem canônica."""
    return [
        *(_source(cls, "siab tabnet") for cls in _SIAB),
        _source(HiperdiaCadastroDataSource, "hiperdia tabnet"),
    ]
