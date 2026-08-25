"""IBGE Registro Civil: nascidos vivos, óbitos, casamentos e divórcios
(SIDRA tabelas 2680 / 2681 / 4406 / 5937).

The two registration tables (2680/2681) publish one aggregate per year (periods 2003-2024, confirmed live
2026-08-17 via ``GET /api/v3/agregados/<tabela>/metadados``), each pre-split by
five classifications (month of event, sex, and three others). Because the
period axis is already annual, choosing the *mensal* table (2680/2681) over
its *anual* sibling (2679/2684) costs nothing extra in request count — the
month breakdown just rides along as an opt-in classification, not a heavier
sweep.

That classification breadth does bite at the municipal level, though.
Confirmed live 2026-08-17 against table 2680 (var 218), year 2023:

* ``N6[all]`` (5570 municipalities) x ``mes=all`` (13 categories, all other
  classifications defaulted to Total) -> **HTTP 500** (SIDRA aggregate limit).
* ``N6[all]`` x ``mes=Total`` (default) -> 200 OK, ~680 KB.
* ``N3[all]`` (27 UFs) x ``mes=all`` -> 200 OK, ~50 KB.
* ``N6[all]`` x ``sexo=ambos`` (2 categories) with ``mes=Total`` -> 200 OK,
  ~1.3 MB.

So both sources default every classification to "Total" (matching the *anual*
tables' output) and expose ``mes``/``sexo`` as opt-in params; requesting
``mes != "total"`` together with ``level="municipio"`` is rejected up front
with a clear message instead of letting SIDRA 500. The other three
classifications (local, número de nascidos por parto / natureza do óbito,
idade) stay fixed at Total — not exposed yet, to keep the combinatorics honest
(``docs/PLANO_NOVAS_FONTES.md`` Fase C).

Registro civil (cartorial) is a counterpoint to DATASUS SINASC/SIM, which
capture the health-system side (declaração de nascido vivo / óbito): the two
can diverge (late/underregistration) and comparing them is itself a signal.

Casamentos (table 4406) and divórcios (table 5937), verified live
2026-08-25, close the registro civil series (births, deaths, nuptiality).
See :class:`IbgeCasamentosDataSource` and :class:`IbgeDivorciosDataSource`
docstrings for their combinatorics limits.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import SidraAggregateSource


class _CivilRegistrySource(SidraAggregateSource):
    """Shared ``mes``/``sexo`` classification handling for RC sources."""

    MES_CLASSIFICACAO_ID: str = ""
    SEXO_CLASSIFICACAO_ID = "2"

    MES: Dict[str, str] = {"total": "0", "all": "all", "todos": "all"}
    SEXO: Dict[str, str] = {"total": "0", "ambos": "4,5", "homens": "4", "mulheres": "5"}

    def _build_classificacao(self, *, mes: str, sexo: str, level_key: str) -> str:
        mes_norm = str(mes).strip().lower()
        sexo_norm = str(sexo).strip().lower()
        mes_token = self.MES.get(mes_norm)
        if mes_token is None:
            raise ValueError(f"Unsupported mes '{mes}'. Allowed: {', '.join(sorted(set(self.MES)))}")
        sexo_token = self.SEXO.get(sexo_norm)
        if sexo_token is None:
            raise ValueError(f"Unsupported sexo '{sexo}'. Allowed: {', '.join(self.SEXO)}")
        if mes_token != "0" and level_key in ("municipio", "n6"):
            raise ValueError(
                "Parameter 'mes' != 'total' is not supported together with "
                "level='municipio' (SIDRA rejects the combinatorial request "
                "— confirmed live). Use level='uf'/'regiao'/'brasil' for the "
                "monthly breakdown, or keep mes='total' for the municipal one."
            )
        return f"{self.MES_CLASSIFICACAO_ID}[{mes_token}]|{self.SEXO_CLASSIFICACAO_ID}[{sexo_token}]"

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = SidraAggregateSource.DEFAULT_LEVEL,
        mes: str = "total",
        sexo: str = "total",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        level_key = str(level).strip().lower()
        classificacao = self._build_classificacao(mes=mes, sexo=sexo, level_key=level_key)
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            classificacao=classificacao,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgeNascidosVivosRcDataSource(_CivilRegistrySource):
    """Live births by month/sex of registration — SIDRA table 2680, var 218.

    "Nascidos vivos, ocorridos no ano, por mês do nascimento[...] e lugar do
    registro." Annual periods 2003-2024; captures cartorial registration.
    Reference total (Brasil, 2023, mes/sexo=Total, verified live 2026-08-17):
    2 523 267 live births.
    """

    TABLE = "2680"
    VARIABLE = "218"
    DEFAULT_LEVEL = "municipio"
    MES_CLASSIFICACAO_ID = "235"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_nascidos_vivos_rc", output_path=output_path, client=client)


class IbgeObitosRcDataSource(_CivilRegistrySource):
    """Deaths by month/sex of occurrence — SIDRA table 2681, var 343.

    "Óbitos, ocorridos no ano, por mês de ocorrência[...] e lugar do
    registro." Annual periods 2003-2024. Reference total (Brasil, 2023,
    mes/sexo=Total, verified live 2026-08-17): 1 429 575 deaths.
    """

    TABLE = "2681"
    VARIABLE = "343"
    DEFAULT_LEVEL = "municipio"
    MES_CLASSIFICACAO_ID = "244"

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_obitos_rc", output_path=output_path, client=client)


class IbgeCasamentosDataSource(SidraAggregateSource):
    """Marriages by month of registration (SIDRA table 4406, var 4993).

    "Casamentos, por mês do registro, estado civil dos cônjuges, grupos de
    idade dos cônjuges e lugar do registro." Annual periods 2013-2024
    (confirmed live 2026-08-25 via ``GET /api/v3/agregados/4406/metadados``).
    Closes the registro civil trio alongside ``ibge_nascidos_vivos_rc`` and
    ``ibge_obitos_rc``.

    Only the month-of-registration classification (236) is exposed as
    ``mes``, mirroring the nascidos vivos / óbitos guard: the other four
    classifications (estado civil and grupo de idade of each spouse, up to
    39 age categories each) stay fixed at "Total": exposing them would
    multiply the combinatorics well past what SIDRA tolerates at municipal
    level, and there is no health-analysis use case yet that needs them.

    Confirmed live 2026-08-25 against ``N6[all]`` (5570 municipalities),
    year 2023:

    * ``mes=Total`` (default) -> 200 OK, ~677 KB.
    * ``mes=all`` (13 categories) -> **HTTP 500** (SIDRA aggregate limit).
    * ``N3[all]`` (27 UFs) x ``mes=all`` -> 200 OK.

    So ``mes != "total"`` together with ``level="municipio"`` is rejected up
    front, exactly like the nascidos vivos / óbitos sources.

    Reference total (Brasil, 2023, mes=Total, verified live 2026-08-25):
    940 799 marriages.
    """

    TABLE = "4406"
    VARIABLE = "4993"
    DEFAULT_LEVEL = "municipio"
    MES_CLASSIFICACAO_ID = "236"
    # Estado civil (664/665) and grupo de idade (666/667) of each spouse,
    # fixed at Total, not exposed yet (see class docstring).
    OUTRAS_CLASSIFICACOES = "664[0]|665[0]|666[0]|667[0]"
    MES: Dict[str, str] = {"total": "0", "all": "all", "todos": "all"}

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_casamentos", output_path=output_path, client=client)

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        mes: str = "total",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        level_key = str(level).strip().lower()
        mes_norm = str(mes).strip().lower()
        mes_token = self.MES.get(mes_norm)
        if mes_token is None:
            raise ValueError(f"Unsupported mes '{mes}'. Allowed: {', '.join(sorted(set(self.MES)))}")
        if mes_token != "0" and level_key in ("municipio", "n6"):
            raise ValueError(
                "Parameter 'mes' != 'total' is not supported together with "
                "level='municipio' (SIDRA rejects the combinatorial request, "
                "confirmed live). Use level='uf'/'regiao'/'brasil' for the "
                "monthly breakdown, or keep mes='total' for the municipal one."
            )
        classificacao = f"{self.MES_CLASSIFICACAO_ID}[{mes_token}]|{self.OUTRAS_CLASSIFICACOES}"
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            classificacao=classificacao,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgeDivorciosDataSource(SidraAggregateSource):
    """Divorces granted in 1st instance (SIDRA table 5937, var 231).

    "Divórcios concedidos em 1ª instância, por grupos de idade do marido e
    da mulher na data da sentença, tempo transcorrido entre as datas do
    casamento e da sentença e lugar da ação do processo." Annual periods
    2014-2024 (confirmed live 2026-08-25). Closes the registro civil trio
    together with ``ibge_casamentos``: divórcios are a judicial process (not
    a cartório registration), so this table's shape has three age/time
    classifications instead of a month-of-registration one: there is no
    "mes" axis here at all.

    Confirmed live 2026-08-25 against ``N6[all]`` (5570 municipalities),
    year 2023:

    * All three classifications at Total (default) -> 200 OK, ~679 KB.
    * Any one classification set to ``all`` (idade do marido: 15 cats,
      idade da mulher: 15 cats, or tempo transcorrido: 32 cats) -> **HTTP
      500** (SIDRA aggregate limit).
    * ``N3[all]`` (27 UFs) x tempo transcorrido=all -> 200 OK.

    So ``idade_marido``/``idade_mulher``/``tempo_decorrido`` != "total"
    together with ``level="municipio"`` is rejected up front, mirroring the
    guard used for the other registro civil sources.

    Reference total (Brasil, 2023, all classifications=Total, verified live
    2026-08-25): 360 787 divorces.
    """

    TABLE = "5937"
    VARIABLE = "231"
    DEFAULT_LEVEL = "municipio"
    IDADE_MARIDO_ID = "274"
    IDADE_MULHER_ID = "275"
    TEMPO_ID = "276"
    DETALHE: Dict[str, str] = {"total": "0", "all": "all", "todos": "all"}

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name="ibge_divorcios", output_path=output_path, client=client)

    def _token(self, param_name: str, value: str) -> tuple[str, str]:
        normalized = str(value).strip().lower()
        token = self.DETALHE.get(normalized)
        if token is None:
            raise ValueError(
                f"Unsupported {param_name} '{value}'. Allowed: {', '.join(sorted(set(self.DETALHE)))}"
            )
        return token, normalized

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        idade_marido: str = "total",
        idade_mulher: str = "total",
        tempo_decorrido: str = "total",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        level_key = str(level).strip().lower()
        marido_token, marido_norm = self._token("idade_marido", idade_marido)
        mulher_token, mulher_norm = self._token("idade_mulher", idade_mulher)
        tempo_token, tempo_norm = self._token("tempo_decorrido", tempo_decorrido)
        if "all" in (marido_norm, mulher_norm, tempo_norm) and level_key in ("municipio", "n6"):
            raise ValueError(
                "Parameters 'idade_marido'/'idade_mulher'/'tempo_decorrido' != "
                "'total' are not supported together with level='municipio' "
                "(SIDRA rejects the combinatorial request, confirmed live). "
                "Use level='uf'/'regiao'/'brasil' for the detailed breakdown, "
                "or keep all three at 'total' for the municipal one."
            )
        classificacao = (
            f"{self.IDADE_MARIDO_ID}[{marido_token}]|"
            f"{self.IDADE_MULHER_ID}[{mulher_token}]|"
            f"{self.TEMPO_ID}[{tempo_token}]"
        )
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            classificacao=classificacao,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )
