"""Índices de preços ao consumidor do IBGE (SNIPC) pela SIDRA: IPCA, INPC e IPCA-15.

Conferido ao vivo em 2026-11-14 (``/api/v3/agregados/<tabela>/metadados`` e consultas).

Cada índice tem duas tabelas de naturezas diferentes:

* **Série histórica** do índice geral, só Brasil (N1): número-índice (base dezembro de
  1993 = 100), variação mensal e variações acumuladas em 3 meses, em 6 meses, no ano e em
  12 meses. IPCA na 1737 (desde dezembro de 1979), INPC na 1736 (desde março de 1979) e
  IPCA-15 na 3065 (desde maio de 2000). É o deflator das séries de gasto.
* **Grupos, subgrupos, itens e subitens** (classificação 315), com variação mensal, no ano,
  em 12 meses e peso mensal, para Brasil (N1), capitais e municípios da pesquisa (N6) e
  regiões metropolitanas (N7); N6 são as seis capitais fora das regiões metropolitanas e N7 as dez regiões metropolitanas. O IBGE parte a série em tabelas por período, escolhidas aqui
  pelo ano: IPCA 2938 (2006-2011), 1419 (2012-2019) e 7060 (2020 em diante); INPC 1100
  (2012-2019) e 7063 (2020 em diante); IPCA-15 1705 (2012-2019) e 7062 (2020 em diante). As
  categorias (7169 índice geral, 7660 saúde e cuidados pessoais etc.) têm o mesmo código em
  todas as tabelas.

A SIDRA responde mensal por faixa de períodos (``202401-202412``). O ano pedido vira uma
faixa de 12 meses; mês ainda não publicado simplesmente não volta. Mês sem valor ("...")
fica nulo. A saída é uma linha por (localidade, mês, categoria, variável): ``nivel,
localidade_id, localidade_nome, periodo, ano, mes, [categoria], variavel_id, variavel,
unidade, valor``.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import SidraAggregateSource

# Categorias da classificação 315 (iguais em todas as tabelas acima).
_GRUPOS = "7169,7170,7445,7486,7558,7625,7660,7712,7766,7786"
# Índice geral, o grupo Saúde e cuidados pessoais e os subgrupos dele.
_SAUDE = "7169,7660,7661,7683,7697"

DETALHES = ("grupos", "saude", "todos")
NIVEIS_GRUPOS = ("brasil", "municipio", "regiao_metropolitana")
_LEVELS_GRUPOS = {
    "brasil": "N1",
    "pais": "N1",
    "n1": "N1",
    "municipio": "N6",
    "n6": "N6",
    "regiao_metropolitana": "N7",
    "n7": "N7",
}


class _PrecosMensal(SidraAggregateSource):
    """Base mensal: o ano vira uma faixa ``AAAA01-AAAA12`` e a saída traz ``periodo/ano/mes``."""

    PRIMEIRO_ANO = 1979
    DEFAULT_LEVEL = "brasil"

    def _period_tokens(self, year: int) -> List[str]:
        return [f"{year}01-{year}12"]

    def _parse(self, payload: List[object], nivel: str) -> List[Dict[str, object]]:
        nomes = {
            str(v.get("id")): v.get("variavel") for v in payload if isinstance(v, dict)
        }
        rows: List[Dict[str, object]] = []
        for base in super()._parse(payload, nivel):
            periodo = base.pop("ano")
            row: Dict[str, object] = {}
            for chave, valor in base.items():
                row[chave] = valor
                if chave == "localidade_nome":
                    row["periodo"] = periodo
                    row["ano"] = periodo // 100 if periodo is not None else None
                    row["mes"] = periodo % 100 if periodo is not None else None
                elif chave == "variavel_id":
                    row["variavel"] = nomes.get(str(valor))
            rows.append(row)
        return rows


class _SerieHistorica(_PrecosMensal):
    """Série nacional do índice geral (sem classificação)."""

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0 = self._parse_year(start_year, "start_year")
        if y0 < self.PRIMEIRO_ANO:
            raise ValueError(
                f"A tabela {self.TABLE} começa em {self.PRIMEIRO_ANO}; start_year={y0} é anterior."
            )
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level="brasil",
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgeIpcaSerieDataSource(_SerieHistorica):
    """IPCA, série histórica: número-índice e variações (tabela 1737, desde 1979)."""

    TABLE = "1737"
    VARIABLE = "2266|63|2263|2264|69|2265"
    PRIMEIRO_ANO = 1979

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None):
        super().__init__(name="ibge_ipca_serie", output_path=output_path, client=client)


class IbgeInpcSerieDataSource(_SerieHistorica):
    """INPC, série histórica: número-índice e variações (tabela 1736, desde 1979)."""

    TABLE = "1736"
    VARIABLE = "2289|44|2290|2291|68|2292"
    PRIMEIRO_ANO = 1979

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None):
        super().__init__(name="ibge_inpc_serie", output_path=output_path, client=client)


class IbgeIpca15SerieDataSource(_SerieHistorica):
    """IPCA-15, série histórica: número-índice e variações (tabela 3065, desde 2000)."""

    TABLE = "3065"
    VARIABLE = "1117|355|1118|1119|356|1120"
    PRIMEIRO_ANO = 2000

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None):
        super().__init__(name="ibge_ipca15_serie", output_path=output_path, client=client)


class _PrecosGrupos(_PrecosMensal):
    """Grupos, subgrupos, itens e subitens (classificação 315), com troca de tabela por ano."""

    # (primeiro ano, tabela); vale a última entrada cujo ano não passa do pedido.
    TABELAS: Tuple[Tuple[int, str], ...] = ()
    CLASSIFICACAO_ID = "315"
    LEVELS = _LEVELS_GRUPOS
    # ``todos`` fora do Brasil estoura o teto de 50.000 valores por ano; pede mês a mês.
    _por_mes = False

    @property
    def primeiro_ano(self) -> int:
        return self.TABELAS[0][0]

    @property
    def TABLE(self) -> str:  # type: ignore[override]
        return self.TABELAS[-1][1]

    def _table_for(self, year: int) -> str:
        escolhida = self.TABELAS[0][1]
        for inicio, tabela in self.TABELAS:
            if year >= inicio:
                escolhida = tabela
        return escolhida

    def _period_tokens(self, year: int) -> List[str]:
        if self._por_mes:
            return [f"{year}{mes:02d}" for mes in range(1, 13)]
        return super()._period_tokens(year)

    @classmethod
    def _localities(cls, nivel, classificacao, n_variaveis=0):
        # A fatia por UF da base é para município de verdade; aqui N6 são só as capitais.
        return [f"{nivel}[all]"]

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = "brasil",
        detalhe: str = "grupos",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0 = self._parse_year(start_year, "start_year")
        if y0 < self.primeiro_ano:
            raise ValueError(
                f"{self.name} começa em {self.primeiro_ano}; start_year={y0} é anterior."
            )
        detalhe_norm = str(detalhe).strip().lower()
        if detalhe_norm not in DETALHES:
            raise ValueError(f"Unsupported detalhe '{detalhe}'. Allowed: {', '.join(DETALHES)}")
        token = {"grupos": _GRUPOS, "saude": _SAUDE, "todos": "all"}[detalhe_norm]
        nivel = self._resolve_level(level)
        self._por_mes = detalhe_norm == "todos" and nivel != "N1"
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            classificacao=f"{self.CLASSIFICACAO_ID}[{token}]",
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgeIpcaGruposDataSource(_PrecosGrupos):
    """IPCA por grupos, subgrupos, itens e subitens (tabelas 2938, 1419 e 7060, desde 2006)."""

    VARIABLE = "63|69|2265|66"
    TABELAS = ((2006, "2938"), (2012, "1419"), (2020, "7060"))

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None):
        super().__init__(name="ibge_ipca_grupos", output_path=output_path, client=client)


class IbgeInpcGruposDataSource(_PrecosGrupos):
    """INPC por grupos, subgrupos, itens e subitens (tabelas 1100 e 7063, desde 2012)."""

    VARIABLE = "44|68|2292|45"
    TABELAS = ((2012, "1100"), (2020, "7063"))

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None):
        super().__init__(name="ibge_inpc_grupos", output_path=output_path, client=client)


class IbgeIpca15GruposDataSource(_PrecosGrupos):
    """IPCA-15 por grupos, subgrupos, itens e subitens (tabelas 1705 e 7062, desde 2012)."""

    VARIABLE = "355|356|1120|357"
    TABELAS = ((2012, "1705"), (2020, "7062"))

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None):
        super().__init__(name="ibge_ipca15_grupos", output_path=output_path, client=client)


PRECOS_SERIE_SOURCES = (
    IbgeIpcaSerieDataSource,
    IbgeInpcSerieDataSource,
    IbgeIpca15SerieDataSource,
)
PRECOS_GRUPOS_SOURCES = (
    IbgeIpcaGruposDataSource,
    IbgeInpcGruposDataSource,
    IbgeIpca15GruposDataSource,
)
