"""Censo Demografico 2022 (e 2010) no SIDRA: tabelas de recorte detalhado.

Sete fontes sobre o mesmo molde de :class:`~guaraci.ibge.sidra.SidraAggregateSource`.
Cada uma fixa tabela, variaveis e as classificacoes (cor ou raca, sexo, idade,
localizacao...), todas verificadas ao vivo em 2026-10-13 via
``GET /api/v3/agregados/<tabela>/metadados``. Todas publicam N1, N2, N3 e N6.

O parametro ``detalhe`` escolhe o recorte:

* ``completo`` (padrao): cada classificacao expandida em suas categorias, sem a
  linha "Total" da classificacao. Algumas classificacoes trazem subtotais entre
  as categorias (``Proprio de algum morador`` e seus filhos, em condicao de
  ocupacao; grupos de idade dentro de grupos maiores em algumas tabelas): as
  categorias seguem como o IBGE publica, entao somar tudo conta duas vezes.
* ``total``: so a categoria Total de cada classificacao, uma linha por
  localidade e variavel.

A API recusa consulta com mais de 50.000 valores. O nivel municipio com
``detalhe=completo`` passa disso em todas as tabelas; a base
(:meth:`SidraAggregateSource._requests`) pede por UF e fatia por categoria.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import IbgePopulacaoIdadeSexoDataSource, SidraAggregateSource

DETALHES = ("completo", "total")

_QUINQUENAL = tuple(IbgePopulacaoIdadeSexoDataSource._QUINQUENAL.split(","))
_SEXO = ("4", "5")
_COR_RACA = ("2776", "2777", "2778", "2779", "2780")
# C58 (grupo de idade) das tabelas 9608 e 10089: 0 a 4 ... 95 a 99, 100 ou mais.
_GRUPO_IDADE_21 = (
    "1140", "1141", "1142", "1143", "1144", "1145", "1146", "1147", "1148",
    "1149", "1150", "1151", "1152", "1153", "1154", "1155", "6802", "6803",
    "92963", "92964", "92965",
)
# C58 da tabela 10125 (2 anos ou mais): 2 a 4, 5 a 9, 10 a 14, 15 a 19 ...
# 55 a 59, 60 a 64 ... 95 a 99, 100 ou mais (sem os grupos agregados).
_GRUPO_IDADE_2_MAIS = (
    "77579", "1141", "1142", "1143", "1144", "1145", "1146", "1147", "1148",
    "1149", "1150", "1151", "1152", "1153", "1154", "1155", "6802", "6803",
    "92963", "92964", "92965",
)
# C287 da tabela 9542 (15 anos ou mais), faixas que nao se sobrepoem.
_IDADE_15_MAIS = ("93086", "93087", "2999", "9482", "9483", "9484", "3000")
_CONDICAO_OCUPACAO = (
    "73554", "73126", "4343", "1055", "73553", "73127", "73128", "73129", "1058",
)
_TIPO_DOMICILIO = ("6815", "121264", "3247", "71975", "71976", "71977")


@dataclass(frozen=True)
class Classif:
    """Uma classificacao do SIDRA: id, categoria Total e categorias detalhadas."""

    id: str
    total: str
    detalhe: Tuple[str, ...]
    # Falso: o recorte completo mantem so o Total desta classificacao.
    expande: bool = True


@dataclass(frozen=True)
class TabelaCenso:
    tabela: str
    variaveis: str
    classificacoes: Tuple[Classif, ...]
    periodos: Tuple[int, ...]


def _classificacao(tabela: TabelaCenso, detalhe: str) -> str:
    partes = []
    for classif in tabela.classificacoes:
        if detalhe == "completo" and classif.expande:
            categorias = ",".join(classif.detalhe)
        else:
            categorias = classif.total
        partes.append(f"{classif.id}[{categorias}]")
    return "|".join(partes)


class _CensoSidraSource(SidraAggregateSource):
    """Base das fontes do Censo: uma tabela, ``detalhe`` e ``level``."""

    DEFAULT_LEVEL = "uf"
    ESPEC: TabelaCenso
    SOURCE_NAME: str = ""

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name=self.SOURCE_NAME, output_path=output_path, client=client)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        espec = cls.__dict__.get("ESPEC")
        if espec is not None:
            cls.TABLE = espec.tabela
            cls.VARIABLE = espec.variaveis
            cls.PERIODS = espec.periodos

    @classmethod
    def periodos(cls) -> Tuple[int, ...]:
        return cls.ESPEC.periodos

    def _validar(self, start_year: object, end_year: object, detalhe: str) -> Tuple[int, int, str]:
        y0 = self._parse_year(start_year, "start_year")
        y1 = self._parse_year(end_year, "end_year")
        validos = self.ESPEC.periodos
        for ano in (y0, y1):
            if ano < min(validos) or ano > max(validos):
                raise ValueError(
                    f"SIDRA table {self.ESPEC.tabela} publishes only "
                    f"{', '.join(str(p) for p in validos)} (verified live). "
                    f"Got {ano}."
                )
        if y0 > y1:
            raise ValueError("Parameter 'start_year' cannot be after 'end_year'.")
        if not any(y0 <= p <= y1 for p in validos):
            raise ValueError(
                f"SIDRA table {self.ESPEC.tabela}: nenhum período publicado entre "
                f"{y0} e {y1}; publicados: {', '.join(str(p) for p in validos)}."
            )
        detalhe_norm = str(detalhe).strip().lower()
        if detalhe_norm not in DETALHES:
            raise ValueError(f"Unsupported detalhe '{detalhe}'. Allowed: {', '.join(DETALHES)}")
        return y0, y1, detalhe_norm

    def download(
        self,
        *,
        start_year: object = 2022,
        end_year: object = 2022,
        level: str = DEFAULT_LEVEL,
        detalhe: str = "completo",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0, y1, detalhe_norm = self._validar(start_year, end_year, detalhe)
        return self._coletar(
            self.ESPEC,
            start_year=y0,
            end_year=y1,
            level=level,
            detalhe=detalhe_norm,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )

    def _coletar(self, espec: TabelaCenso, *, detalhe: str, **kwargs) -> Dict[str, object]:
        self.TABLE = espec.tabela
        self.VARIABLE = espec.variaveis
        self.PERIODS = espec.periodos
        return self._collect(classificacao=_classificacao(espec, detalhe), **kwargs)


_COR = Classif("86", "95251", _COR_RACA)
_SEXO_C = Classif("2", "6794", _SEXO)


class IbgeCensoCorRacaIdadeSexoDataSource(_CensoSidraSource):
    """Populacao residente por cor ou raca, sexo e idade -- tabela 9606, var 93.

    Censo 2010 e 2022. Idade em grupos quinquenais (0 a 4 ... 95 a 99, 100 ou
    mais), os mesmos da tabela 9514. Recorte municipal por UF e categoria.
    """

    SOURCE_NAME = "ibge_censo_cor_raca_idade_sexo"
    ESPEC = TabelaCenso(
        "9606",
        "93",
        (_COR, _SEXO_C, Classif("287", "100362", _QUINQUENAL)),
        (2010, 2022),
    )


class IbgeCensoAlfabetizacaoDataSource(_CensoSidraSource):
    """Pessoas de 15 anos ou mais por alfabetizacao -- tabela 9542, var 950.

    Censo 2022. Alfabetizadas e nao alfabetizadas, por sexo, cor ou raca e
    faixa de idade (15 a 19, 20 a 24, 25 a 34, 35 a 44, 45 a 54, 55 a 64, 65 ou
    mais).
    """

    SOURCE_NAME = "ibge_censo_alfabetizacao"
    ESPEC = TabelaCenso(
        "9542",
        "950",
        (
            Classif("59", "93024", ("1023", "1024")),
            _SEXO_C,
            _COR,
            Classif("287", "100362", _IDADE_15_MAIS),
        ),
        (2022,),
    )


class IbgeCensoIndigenaDataSource(_CensoSidraSource):
    """Populacao total e indigena -- tabela 9845, vars 93 e 350.

    Censo 2010 e 2022. Por sexo, idade quinquenal, quesito de declaracao e
    localizacao do domicilio (dentro ou fora de terras indigenas). A forma de
    declaracao da idade fica sempre no Total, para nao multiplicar o recorte.
    """

    SOURCE_NAME = "ibge_censo_indigena"
    ESPEC = TabelaCenso(
        "9845",
        "93|350",
        (
            _SEXO_C,
            Classif("287", "100362", _QUINQUENAL),
            Classif("286", "113635", ("6555", "6556"), expande=False),
            Classif("1714", "60024", ("60025", "60026", "60029")),
            Classif("2661", "32776", ("12869", "12870")),
        ),
        (2010, 2022),
    )


class IbgeCensoQuilombolaDataSource(_CensoSidraSource):
    """Populacao total e quilombola -- tabela 10089, vars 93, 4709 e 4728.

    Censo 2022. Por sexo, grupo de idade, localizacao (dentro ou fora de
    territorios quilombolas) e situacao do domicilio. A variavel 4728 e um
    percentual (``unidade`` traz o ``%``); nao se soma com as contagens.
    """

    SOURCE_NAME = "ibge_censo_quilombola"
    ESPEC = TabelaCenso(
        "10089",
        "93|4709|4728",
        (
            _SEXO_C,
            Classif("58", "95253", _GRUPO_IDADE_21),
            Classif("2661", "32776", ("60027", "60028")),
            Classif("1", "6795", ("1", "2")),
        ),
        (2022,),
    )


class IbgeCensoAdensamentoDataSource(_CensoSidraSource):
    """Domicilios por moradores por dormitorio -- tabela 9933, var 381.

    Censo 2022. Cruzado com condicao de ocupacao e tipo do domicilio.
    """

    SOURCE_NAME = "ibge_censo_adensamento"
    ESPEC = TabelaCenso(
        "9933",
        "381",
        (
            Classif("1975", "73086", ("73087", "73088", "73089", "73090")),
            Classif("63", "95826", _CONDICAO_OCUPACAO),
            Classif("125", "2932", _TIPO_DOMICILIO),
        ),
        (2022,),
    )


class IbgeCensoParedesDataSource(_CensoSidraSource):
    """Domicilios por material das paredes externas -- tabela 9928, var 381.

    Censo 2022. Cruzado com condicao de ocupacao e tipo do domicilio.
    """

    SOURCE_NAME = "ibge_censo_paredes"
    ESPEC = TabelaCenso(
        "9928",
        "381",
        (
            Classif(
                "137",
                "13233",
                ("73073", "12194", "73074", "73075", "73076", "2876", "13226"),
            ),
            Classif("63", "95826", _CONDICAO_OCUPACAO),
            Classif("125", "2932", _TIPO_DOMICILIO),
        ),
        (2022,),
    )


class IbgeCensoDeficienciaDataSource(_CensoSidraSource):
    """Pessoas de 2 anos ou mais com deficiencia -- tabelas 10125 e 10132.

    Censo 2022. Dois recortes, gravados em arquivos separados na mesma
    execucao: ``..._sexo_idade`` (10125, vars 11852 e 12785, por sexo e grupo
    de idade) e ``..._cor_raca`` (10132, var 11852, por cor ou raca e existencia
    de deficiencia).
    """

    SOURCE_NAME = "ibge_censo_deficiencia"
    ESPEC = TabelaCenso(
        "10125",
        "11852|12785",
        (_SEXO_C, Classif("58", "95253", _GRUPO_IDADE_2_MAIS)),
        (2022,),
    )
    ESPEC_COR_RACA = TabelaCenso(
        "10132",
        "11852",
        (_COR, Classif("839", "46583", ("58765", "58766"))),
        (2022,),
    )

    def download(
        self,
        *,
        start_year: object = 2022,
        end_year: object = 2022,
        level: str = _CensoSidraSource.DEFAULT_LEVEL,
        detalhe: str = "completo",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0, y1, detalhe_norm = self._validar(start_year, end_year, detalhe)
        comum = dict(
            start_year=y0,
            end_year=y1,
            level=level,
            detalhe=detalhe_norm,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )
        self._STEM_TAG = "_sexo_idade"
        primeiro = self._coletar(self.ESPEC, **comum)
        registros = list(self._records)
        self._STEM_TAG = "_cor_raca"
        segundo = self._coletar(self.ESPEC_COR_RACA, **comum)
        self._records = registros + list(self._records)

        resultado = dict(primeiro)
        for chave in ("documents_found", "downloaded_count", "failed_count", "skipped_count"):
            resultado[chave] = int(primeiro.get(chave) or 0) + int(segundo.get(chave) or 0)
        resultado["exported_files"] = list(primeiro["exported_files"]) + list(
            segundo["exported_files"]
        )
        resultado["table"] = f"{self.ESPEC.tabela}+{self.ESPEC_COR_RACA.tabela}"
        avisos = " ".join(
            str(item)
            for item in (primeiro.get("export_warning"), segundo.get("export_warning"))
            if item
        )
        if avisos:
            resultado["export_warning"] = avisos
        self._completar_manifesto(resultado)
        return resultado

    def _completar_manifesto(self, resultado: Dict[str, object]) -> None:
        """O manifesto da segunda passada vira o das duas."""
        caminho = self.output_path / "manifest.json"
        try:
            manifesto = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        manifesto["exported_files"] = list(resultado["exported_files"])
        # O manifesto da segunda passada traz só as linhas dela; o total das
        # duas passadas entra tanto no campo legado quanto em ``stats``.
        manifesto["documents_found"] = resultado["documents_found"]
        estatisticas = manifesto.get("stats")
        if isinstance(estatisticas, dict):
            estatisticas["documents_found"] = resultado["documents_found"]
            estatisticas["failed_count"] = resultado["failed_count"]
        filtros = manifesto.setdefault("filters", {})
        filtros["table"] = resultado["table"]
        caminho.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")


CENSO_SOURCES: List[type] = [
    IbgeCensoCorRacaIdadeSexoDataSource,
    IbgeCensoAlfabetizacaoDataSource,
    IbgeCensoIndigenaDataSource,
    IbgeCensoQuilombolaDataSource,
    IbgeCensoAdensamentoDataSource,
    IbgeCensoParedesDataSource,
    IbgeCensoDeficienciaDataSource,
]
