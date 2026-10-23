"""Produção agropecuária municipal do IBGE no SIDRA e Censo Agropecuário 2017.

Seis fontes anuais (PAM, PPM, PEVS) sobre o molde de
:class:`~guaraci.ibge.sidra.SidraAggregateSource`, mais três tabelas do Censo
Agropecuário 2017. Tabelas, variáveis e categorias foram conferidas ao vivo em
2026-10-23 em ``GET /api/v3/agregados/<tabela>/metadados`` (todas publicam N1,
N2, N3 e N6):

* 5457 (PAM, lavouras temporárias e permanentes), 1974-2025, 85 produtos;
* 3939 (PPM, efetivo dos rebanhos), 1974-2025, 10 tipos de rebanho;
* 3940 (PPM, aquicultura), 2013-2025, 25 categorias;
* 74 (PPM, produção de origem animal), 1974-2025, 6 produtos;
* 289 (PEVS, extração vegetal), 1986-2025, 63 produtos;
* 291 (PEVS, silvicultura), 1986-2025, 37 produtos.

O parâmetro ``detalhe`` segue o do Censo: ``completo`` (padrão) expande o
produto em suas categorias, sem a linha Total; ``total`` pede só o Total. A
3939 não tem categoria Total e devolve sempre os tipos de rebanho. Os produtos
de PEVS e as espécies da aquicultura vêm com subtotais entre as categorias
(``1 - Alimentícios`` e seus filhos), como o IBGE publica; somar tudo conta
duas vezes. O valor da produção vem em moeda da época (Cruzeiro até 1993, Real
desde 1994), como diz a coluna ``unidade``.

O nível município pede por UF e fatia por produto até caber nos 50.000 valores
da API (:meth:`SidraAggregateSource._requests`): a PAM de um ano são cerca de
80 requisições. O nível padrão da PAM e da PPM é município; o do Censo
Agropecuário é UF.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from guaraci.ibge.censo import (
    DETALHES,
    Classif,
    TabelaCenso,
    _CensoSidraSource,
)
from guaraci.ibge.client import IbgeSidraClient
from guaraci.ibge.sidra import SidraAggregateSource

# Categorias (sem a linha Total) de cada classificação, conferidas nos metadados.
_PAM_PRODUTOS = (
    "40129", "40092", "83388", "45982", "83399", "40329", "83389", "40130", "40099",
    "40100", "40101", "40102", "40103", "40131", "40136", "40104", "40105", "40137",
    "40468", "40138", "40139", "40140", "40141", "40330", "40106", "40331", "83390",
    "40142", "40143", "40107", "83391", "40108", "40109", "40144", "83392", "40145",
    "83400", "40146", "40147", "40110", "40111", "40112", "40148", "40113", "83395",
    "40114", "40149", "83401", "40150", "83393", "40115", "40151", "40152", "40116",
    "40260", "40117", "40261", "40118", "40119", "40262", "40263", "40264", "40120",
    "40121", "40122", "83394", "83396", "40265", "40266", "40267", "40268", "40269",
    "83397", "40123", "83398", "40270", "40124", "40125", "40271", "40126", "40127",
    "40128", "40272", "40273", "40274",
)

_PPM_REBANHOS = (
    "2670", "2675", "2672", "32794", "32795", "2681", "2677", "32796", "32793",
    "2680",
)

_PPM_ORIGEM_ANIMAL = (
    "2682", "2685", "2686", "2687", "2683", "2684",
)

_PPM_AQUICULTURA = (
    "79366", "32861", "32865", "32866", "32867", "32868", "32869", "32870", "32871",
    "32872", "32873", "32874", "32875", "32876", "32877", "32878", "32879", "32880",
    "32881", "32886", "32887", "32888", "32889", "32890", "32891",
)

_PEVS_EXTRATIVO = (
    "3402", "3403", "83410", "83411", "83412", "3404", "3405", "83413", "3406",
    "83414", "83415", "3407", "3408", "39409", "3409", "83416", "83417", "3410",
    "11296", "3411", "3412", "3413", "3414", "3415", "3416", "3417", "3418", "3419",
    "40524", "3420", "3421", "3422", "110011", "3423", "3424", "3425", "3426",
    "3427", "3428", "3429", "3430", "3431", "3433", "3434", "3435", "3438", "83418",
    "3439", "3440", "3441", "3442", "83419", "3443", "3444", "3445", "3446", "3448",
    "3449", "3450", "3451", "3452", "3453", "3454",
)

_PEVS_SILVICULTURA = (
    "3455", "83420", "83421", "33247", "83422", "33248", "83423", "33249", "3456",
    "83424", "83425", "33250", "83426", "33251", "83427", "33252", "3457", "3458",
    "83428", "83429", "33253", "83430", "33254", "83431", "33255", "3459", "83432",
    "83433", "33256", "83434", "33257", "83435", "33258", "3460", "3461", "3462",
    "3463",
)

# C829 (tipologia), C12564 (sexo do produtor), C218, C800 e C12598 do Censo
# Agropecuário 2017, sem a linha Total de cada uma.
_TIPOLOGIA = (
    "46303", "46304", "46305", "46306", "46307", "46422", "46423",
)
_SEXO_PRODUTOR = ("112634", "112635", "41146")
_SEXO_PRODUTOR_DIRIGENTE = ("112634", "112635")
_CONDICAO_PRODUTOR = (
    "46503", "46504", "46505", "46506", "46507", "4783", "111518",
)
_CONDICAO_LEGAL_TERRAS = ("111134", "111135", "111136", "111137", "41157", "111138")
_USO_AGROTOXICO = ("111611", "111612", "46557", "46558")
_ESCOLARIDADE_6851 = (
    "46510", "46511", "40708", "40709", "40710", "40711", "40712", "40713",
    "40714", "40715", "40726", "40727", "40728", "40729", "40730", "41159",
)
_ESCOLARIDADE_6755 = (
    "46510", "46511", "40708", "40709", "40710", "40711", "40712", "40713",
    "40714", "40715", "40726", "40727", "40728", "40729", "40730",
)
_ASSOCIACAO = ("114543", "113455", "41142", "41143", "41144", "113457")
_COR_RACA_PRODUTOR = ("46424", "46425", "46426", "46428", "46429")
_CLASSE_IDADE_PRODUTOR = (
    "118190", "118191", "118192", "118193", "118194", "46437", "46501",
)
_CONCLUSAO_CURSO = ("46587", "46588")


@dataclass(frozen=True)
class TabelaAnual:
    """Tabela anual do SIDRA com uma classificação de produto."""

    tabela: str
    variaveis: str
    classificacao: Classif
    primeiro_ano: int


def _pedido(espec: TabelaAnual, detalhe: str) -> str:
    classif = espec.classificacao
    if detalhe == "completo" or not classif.total:
        categorias = ",".join(classif.detalhe)
    else:
        categorias = classif.total
    return f"{classif.id}[{categorias}]"


class _AgroAnualSource(SidraAggregateSource):
    """Base das séries anuais: uma tabela, ``detalhe`` e ``level``."""

    DEFAULT_LEVEL = "municipio"
    ESPEC: TabelaAnual
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

    @classmethod
    def primeiro_ano(cls) -> int:
        return cls.ESPEC.primeiro_ano

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        detalhe: str = "completo",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0 = self._parse_year(start_year, "start_year")
        y1 = self._parse_year(end_year, "end_year")
        if y0 < self.ESPEC.primeiro_ano:
            raise ValueError(
                f"SIDRA table {self.ESPEC.tabela} starts in {self.ESPEC.primeiro_ano}. "
                f"Got {y0}."
            )
        detalhe_norm = str(detalhe).strip().lower()
        if detalhe_norm not in DETALHES:
            raise ValueError(f"Unsupported detalhe '{detalhe}'. Allowed: {', '.join(DETALHES)}")
        return self._collect(
            start_year=y0,
            end_year=y1,
            level=level,
            classificacao=_pedido(self.ESPEC, detalhe_norm),
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgePamLavourasDataSource(_AgroAnualSource):
    """Lavouras temporárias e permanentes por município -- tabela 5457.

    PAM, 1974-2025. Variáveis: área plantada ou destinada à colheita (8331),
    área colhida (216), quantidade produzida (214), rendimento médio (112, não
    se soma) e valor da produção (215). Produto em 85 categorias. As variáveis
    de percentual do total geral ficam de fora.
    """

    SOURCE_NAME = "ibge_pam_lavouras"
    ESPEC = TabelaAnual(
        "5457",
        "8331|216|214|112|215",
        Classif("782", "0", _PAM_PRODUTOS),
        1974,
    )


class IbgePpmRebanhosDataSource(_AgroAnualSource):
    """Efetivo dos rebanhos por município -- tabela 3939, variável 105 (cabeças).

    PPM, 1974-2025. Bovino, bubalino, equino, suíno (total e matrizes), caprino,
    ovino, galináceos (total e galinhas) e codornas. Sem categoria Total.
    """

    SOURCE_NAME = "ibge_ppm_rebanhos"
    ESPEC = TabelaAnual("3939", "105", Classif("79", "", _PPM_REBANHOS), 1974)


class IbgePpmAquiculturaDataSource(_AgroAnualSource):
    """Produção da aquicultura por município -- tabela 3940, variáveis 4146 e 215.

    PPM, 2013-2025. A variável 4146 muda de unidade conforme o produto (quilos,
    mil unidades); a coluna ``unidade`` traz a de cada linha.
    """

    SOURCE_NAME = "ibge_ppm_aquicultura"
    ESPEC = TabelaAnual("3940", "4146|215", Classif("654", "0", _PPM_AQUICULTURA), 2013)


class IbgePpmProducaoAnimalDataSource(_AgroAnualSource):
    """Produção de origem animal por município -- tabela 74, variáveis 106 e 215.

    PPM, 1974-2025. Leite, ovos de galinha, ovos de codorna, mel de abelha,
    casulos do bicho-da-seda e lã.
    """

    SOURCE_NAME = "ibge_ppm_producao_animal"
    ESPEC = TabelaAnual("74", "106|215", Classif("80", "0", _PPM_ORIGEM_ANIMAL), 1974)


class IbgePevsExtracaoVegetalDataSource(_AgroAnualSource):
    """Extração vegetal por município -- tabela 289, variáveis 144 e 145.

    PEVS, 1986-2025. Quantidade produzida e valor da produção por produto
    extrativo (alimentícios, borrachas, ceras, madeiras e outros), com
    subtotais por grupo.
    """

    SOURCE_NAME = "ibge_pevs_extracao_vegetal"
    ESPEC = TabelaAnual("289", "144|145", Classif("193", "0", _PEVS_EXTRATIVO), 1986)


class IbgePevsSilviculturaDataSource(_AgroAnualSource):
    """Silvicultura por município -- tabela 291, variáveis 142 e 143.

    PEVS, 1986-2025. Quantidade produzida e valor da produção por produto da
    silvicultura (carvão vegetal, lenha, madeira em tora, resina), com
    subtotais por espécie. A tabela 5930, de área florestal, não entra.
    """

    SOURCE_NAME = "ibge_pevs_silvicultura"
    ESPEC = TabelaAnual("291", "142|143", Classif("194", "0", _PEVS_SILVICULTURA), 1986)


AGRO_ANUAL_SOURCES = [
    IbgePamLavourasDataSource,
    IbgePpmRebanhosDataSource,
    IbgePpmAquiculturaDataSource,
    IbgePpmProducaoAnimalDataSource,
    IbgePevsExtracaoVegetalDataSource,
    IbgePevsSilviculturaDataSource,
]


# -- Censo Agropecuário 2017 ------------------------------------------------------

_TIPOLOGIA_C = Classif("829", "46302", _TIPOLOGIA, expande=False)


class IbgeCensoAgro2017AgrotoxicosDataSource(_CensoSidraSource):
    """Estabelecimentos por uso de agrotóxicos -- tabela 6851, variável 183.

    Censo Agropecuário 2017. Número de estabelecimentos por uso de agrotóxicos
    (utilizou, não utilizou, e os dois motivos do não uso), sexo do produtor e
    escolaridade. Tipologia (agricultura familiar), condição do produtor e
    associação a cooperativa ficam no Total no recorte completo, para não
    multiplicar o cruzamento. As categorias de escolaridade trazem a pergunta
    "sabe ler e escrever" ao lado dos níveis de curso, como o IBGE publica.
    """

    SOURCE_NAME = "ibge_censo_agro_2017_agrotoxicos"
    ESPEC = TabelaCenso(
        "6851",
        "183",
        (
            _TIPOLOGIA_C,
            Classif("12521", "46556", _USO_AGROTOXICO),
            Classif("12564", "41145", _SEXO_PRODUTOR),
            Classif("218", "46502", _CONDICAO_PRODUTOR, expande=False),
            Classif("800", "41147", _ESCOLARIDADE_6851),
            Classif("12598", "41141", _ASSOCIACAO, expande=False),
        ),
        (2017,),
    )


class IbgeCensoAgro2017EstabelecimentosDataSource(_CensoSidraSource):
    """Estabelecimentos e área por condição das terras -- tabela 6753, vars 183 e 184.

    Censo Agropecuário 2017. Número de estabelecimentos e área (hectares) por
    tipologia (agricultura familiar e Pronaf), condição legal das terras,
    condição do produtor em relação às terras e sexo do produtor.
    """

    SOURCE_NAME = "ibge_censo_agro_2017_estabelecimentos"
    ESPEC = TabelaCenso(
        "6753",
        "183|184",
        (
            Classif("829", "46302", _TIPOLOGIA),
            Classif("221", "111195", _CONDICAO_LEGAL_TERRAS),
            Classif("218", "46502", _CONDICAO_PRODUTOR),
            Classif("12564", "41145", _SEXO_PRODUTOR),
        ),
        (2017,),
    )


class IbgeCensoAgro2017ProdutorDataSource(_CensoSidraSource):
    """Estabelecimentos dirigidos pelo produtor -- tabela 6755, variável 9998.

    Censo Agropecuário 2017. Perfil do produtor: sexo, escolaridade, conclusão
    do curso, cor ou raça e classe de idade. A tipologia fica no Total no
    recorte completo.
    """

    SOURCE_NAME = "ibge_censo_agro_2017_produtor"
    ESPEC = TabelaCenso(
        "6755",
        "9998",
        (
            _TIPOLOGIA_C,
            Classif("12564", "41145", _SEXO_PRODUTOR_DIRIGENTE),
            Classif("800", "41147", _ESCOLARIDADE_6755),
            Classif("840", "46586", _CONCLUSAO_CURSO),
            Classif("830", "46427", _COR_RACA_PRODUTOR),
            Classif("12771", "45951", _CLASSE_IDADE_PRODUTOR),
        ),
        (2017,),
    )


CENSO_AGRO_SOURCES = [
    IbgeCensoAgro2017AgrotoxicosDataSource,
    IbgeCensoAgro2017EstabelecimentosDataSource,
    IbgeCensoAgro2017ProdutorDataSource,
]
