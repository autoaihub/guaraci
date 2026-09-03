"""Resolução de coluna e comparação para os filtros de refinamento do DATASUS.

SIH, SIM e SINAN oferecem os mesmos filtros de recorte (UF, município, sexo,
ano) sobre microdados cujos nomes de coluna variam por sistema e por ano. Cada
datasource resolvia isso com uma cópia da mesma função local, e as duas cópias
carregavam os mesmos dois defeitos:

- a coluna era escolhida pela primeira que existisse no arquivo, mesmo quando
  vinha vazia. No SINAN, ``UF`` existe mas está em branco em 96% dos registros,
  enquanto ``SG_UF_NOT`` está completa: filtrar dengue por ``SP`` devolvia
  103 059 de 5 047 004 casos, sem erro nenhum;
- a comparação era feita direto contra o valor recebido da linha de comando,
  sempre string, enquanto colunas como ``NU_IDADE_N`` (Int64) e ``NU_ANO``
  (String, comparada com int) têm outro tipo. O filtro morria com
  ``ComputeError: cannot compare string with numeric type``.

Este módulo centraliza as duas decisões para que os três sistemas se comportem
igual e o conserto valha para todos.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Union

import polars as pl
from loguru import logger

Frame = Union[pl.DataFrame, pl.LazyFrame]

#: Valores que o DATASUS usa como "sem informação" em colunas de texto e que,
#: para efeito de escolha de coluna, não contam como dado presente.
_EMPTY_TOKENS = ("", "NAN", "NONE", "NULL")


def columns_of(frame: Frame) -> List[str]:
    """Nomes das colunas de um DataFrame ou LazyFrame."""
    if isinstance(frame, pl.LazyFrame):
        return frame.collect_schema().names()
    return list(frame.columns)


def dtype_of(frame: Frame, column: str) -> pl.DataType:
    """Tipo declarado de uma coluna, sem materializar o frame."""
    if isinstance(frame, pl.LazyFrame):
        return frame.collect_schema()[column]
    return frame.schema[column]


def _has_data(frame: Frame, column: str) -> bool:
    """Diz se a coluna tem algum valor útil (não nulo e não vazio).

    Custa uma passada com projeção de uma coluna só. Em parquet o plano
    aproveita as estatísticas por row group, o que medimos em 0,25 s sobre
    17 milhões de registros, barato diante da varredura que o filtro fará em
    seguida.
    """
    lazy = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    try:
        useful = (
            lazy.select(
                pl.col(column)
                .cast(pl.Utf8, strict=False)
                .str.strip_chars()
                .str.to_uppercase()
                .replace(list(_EMPTY_TOKENS), None)
                .count()
            )
            .collect()
            .item()
        )
    except Exception as exc:  # noqa: BLE001 - inspeção não pode derrubar o filtro
        logger.debug("Could not inspect column '{}' for data: {}", column, exc)
        return True
    return bool(useful)


def resolve_filter_column(frame: Frame, candidates: Sequence[str]) -> Optional[str]:
    """Escolhe a coluna a filtrar entre os nomes candidatos.

    Percorre ``candidates`` na ordem de preferência declarada pelo chamador e
    devolve o primeiro que exista **e tenha dados**. Quando todos os candidatos
    presentes estão vazios, devolve o primeiro existente: não há escolha melhor
    a fazer, e preservar o comportamento antigo é melhor que ignorar o filtro
    em silêncio.
    """
    available = columns_of(frame)
    present = [name for name in candidates if name in available]
    if not present:
        return None

    for name in present:
        if _has_data(frame, name):
            if name != present[0]:
                logger.info(
                    "Filter column '{}' is empty in this dataset; using '{}' instead.",
                    present[0],
                    name,
                )
            return name

    logger.warning(
        "None of the candidate columns {} carry data; filtering on '{}' anyway.",
        present,
        present[0],
    )
    return present[0]


def _as_number(value: Any) -> Optional[float]:
    """Converte o valor para número, ou devolve ``None`` se não for numérico."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def equality_expr(frame: Frame, column: str, value: Any) -> pl.Expr:
    """Expressão de igualdade que respeita o tipo da coluna.

    O valor chega da CLI ou da API como string ou int, sem relação com o tipo
    inferido do DBF. Comparar os dois diretamente derrubava o filtro com
    ``ComputeError``. Quando ambos os lados são numéricos a comparação é
    numérica, o que também resolve o zero à esquerda dos campos de mês
    (``MES_CMPT`` vale ``"01"`` e o usuário digita ``1``); caso contrário, é
    textual com espaços removidos e caixa alta.
    """
    numeric_value = _as_number(value)
    if numeric_value is not None:
        numeric_column = (
            pl.col(column)
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .cast(pl.Float64, strict=False)
        )
        return numeric_column == numeric_value

    normalized_value = str(value).strip().upper()
    column_expr = (
        pl.col(column).cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase()
    )
    return column_expr == normalized_value


def uf_expr(frame: Frame, column: str, value: Any) -> pl.Expr:
    """Igualdade de UF tolerante à forma como cada sistema guarda o estado.

    O mesmo filtro ``--uf SP`` precisa acertar três representações: a sigla
    (``SG_UF_NOT`` do SINAN), o código IBGE de dois dígitos e o código de seis
    dígitos de município ou de gestor, cujos dois primeiros dígitos são a UF
    (``UF_ZI`` vale ``120000`` para o Acre, ``CODMUNRES`` vale ``120040``).
    Sem isso, ``--uf SP`` no SIH e no SIM nunca casava com nada.

    Aceita da pessoa usuária tanto a sigla quanto o código numérico.
    """
    from guaraci.utils.mapping import UF_DICT

    siglas = {sigla.upper(): sigla for sigla in UF_DICT.values()}
    codigo_para_sigla = {str(code): sigla for code, sigla in UF_DICT.items()}

    pedido = str(value).strip().upper()
    alvo = siglas.get(pedido) or codigo_para_sigla.get(pedido.lstrip("0"))
    if alvo is None:
        # Valor que não corresponde a nenhuma UF: não casa nada, sem estourar.
        return pl.lit(False)

    texto = pl.col(column).cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase()
    # Os dois primeiros dígitos de um código numérico são a UF; para a sigla,
    # o próprio valor. As duas leituras são testadas em OU.
    prefixo = texto.str.replace(r"\.0+$", "").str.slice(0, 2)
    return (texto == alvo) | (
        prefixo.replace_strict(codigo_para_sigla, default=None) == alvo
    )


def uf_normalization_expr(frame: Frame, column: str, sample_rows: int = 10_000) -> pl.Expr:
    """Normaliza uma coluna de UF para a sigla, preservando o que não for UF.

    A seleção das colunas a normalizar é feita por nome (qualquer coluna com
    ``UF``), o que varre junto campos que não são unidade federativa: ``UF_ZI``
    no SIH é o código do gestor (``120000``). Como esse valor não corresponde a
    nenhuma UF, o mapeamento antigo o substituía por nulo e a coluna inteira se
    perdia no arquivo exportado.

    Aqui a coluna só é reescrita quando uma amostra mostra que ela de fato
    carrega UFs. Caso contrário é devolvida intacta.
    """
    from guaraci.utils.mapping import UF_DICT

    lookup = {
        **{str(code): sigla for code, sigla in UF_DICT.items()},
        **{sigla: sigla for sigla in UF_DICT.values()},
    }

    normalized = (
        pl.col(column)
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.to_uppercase()
        .str.replace(r"\.0+$", "")
    )

    lazy = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    try:
        reconhecidos = (
            lazy.select(normalized.alias(column))
            .head(sample_rows)
            .select(pl.col(column).replace_strict(lookup, default=None).count())
            .collect()
            .item()
        )
    except Exception as exc:  # noqa: BLE001 - inspeção não pode derrubar a carga
        logger.debug("Could not sample column '{}' for UF mapping: {}", column, exc)
        reconhecidos = 1

    if not reconhecidos:
        logger.debug(
            "Column '{}' holds no recognisable UF value; leaving it untouched.", column
        )
        return pl.col(column)

    return normalized.replace_strict(lookup, default=None).cast(pl.Utf8).alias(column)


def uf_column_names(columns: Sequence[str]) -> List[str]:
    """Colunas candidatas a conter UF, pelo nome."""
    return [name for name in columns if "UF" in name.upper()]


def coded_equality_expr(
    frame: Frame, column: str, value: Any, mapping: dict[str, str]
) -> pl.Expr:
    """Igualdade para campos que a interface expõe por rótulo e o dado guarda por código.

    ``--sexo M`` precisa virar ``1`` no SIM e no SIH e continuar ``M`` no
    SINAN, porque cada sistema codifica o campo à sua maneira. ``mapping``
    traduz o rótulo aceito na interface para o código do sistema; valores que
    já venham no código do sistema passam direto.
    """
    pedido = str(value).strip().upper()
    return equality_expr(frame, column, mapping.get(pedido, pedido))


def contains_expr(frame: Frame, column: str, value: Any) -> pl.Expr:
    """Expressão de substring, usada pelos filtros de município."""
    return (
        pl.col(column)
        .cast(pl.Utf8, strict=False)
        .str.contains(str(value), literal=True, strict=False)
    )


def combine(conditions: Sequence[pl.Expr]) -> Optional[pl.Expr]:
    """Junta as condições com E lógico, ou devolve ``None`` se não houver."""
    if not conditions:
        return None
    combined = conditions[0]
    for condition in conditions[1:]:
        combined = combined & condition
    return combined
