"""Fontes de saúde do TabNet do DATASUS com série municipal mensal: SIAB e HIPERDIA.

Verificado ao vivo em 2026-11-14 em ``tabnet.datasus.gov.br`` (HTTP, formulário
no ``deftohtm.exe`` e consulta no ``tabcgi.exe``):

* SIAB situação de saúde (``SIABSbr.def``, 52 medidas) e produção e marcadores
  (``SIABPbr.def``, 54 medidas): um ``.dbf`` por mês, jan/1998 a dez/2015.
* SIAB cadastramento familiar (``SIABFbr.def``, 47 medidas) e situação de
  saneamento (``SIABCbr.def``, 23 medidas): um ``.dbf`` de dezembro por ano (1998-2014) e mensais de jun a dez/2015.
* HIPERDIA (``hd<uf>.def``, um por UF, 4 medidas: hipertensão, diabetes tipo 1,
  diabetes tipo 2 e hipertensão com diabetes): jan/2002 a abr/2013.
"""

from guaraci.tabnet.mensal import TabnetMensalDataSource, TabnetMensalSpec

__all__ = [
    "HiperdiaCadastroDataSource",
    "SiabCadastroFamiliarDataSource",
    "SiabProducaoMarcadoresDataSource",
    "SiabSaneamentoDataSource",
    "SiabSituacaoSaudeDataSource",
]


class SiabSituacaoSaudeDataSource(TabnetMensalDataSource):
    SPEC = TabnetMensalSpec(
        dataset="siab_situacao_saude",
        title="SIAB - Situação de Saúde por município (1998-2015)",
        def_path="siab/cnv/SIABSbr.def",
        min_year=1998,
        max_year=2015,
    )


class SiabProducaoMarcadoresDataSource(TabnetMensalDataSource):
    SPEC = TabnetMensalSpec(
        dataset="siab_producao_marcadores",
        title="SIAB - Produção e Marcadores por município (1998-2015)",
        def_path="siab/cnv/SIABPbr.def",
        min_year=1998,
        max_year=2015,
    )


class SiabCadastroFamiliarDataSource(TabnetMensalDataSource):
    SPEC = TabnetMensalSpec(
        dataset="siab_cadastro_familiar",
        title="SIAB - Cadastramento Familiar por município (1998-2015)",
        def_path="siab/cnv/SIABFbr.def",
        min_year=1998,
        max_year=2015,
    )


class SiabSaneamentoDataSource(TabnetMensalDataSource):
    SPEC = TabnetMensalSpec(
        dataset="siab_saneamento",
        title="SIAB - Situação de Saneamento por município (1998-2015)",
        def_path="siab/cnv/SIABCbr.def",
        min_year=1998,
        max_year=2015,
    )


class HiperdiaCadastroDataSource(TabnetMensalDataSource):
    SPEC = TabnetMensalSpec(
        dataset="hiperdia_cadastro",
        title="HIPERDIA - Cadastro de hipertensos e diabéticos por município (2002-2013)",
        def_path="hiperdia/cnv/hd{uf}.def",
        min_year=2002,
        max_year=2013,
        per_uf_def=True,
    )
