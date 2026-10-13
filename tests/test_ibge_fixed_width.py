"""Parser do INPUT SAS do IBGE e fatiador de largura fixa, sem rede.

Os leiautes abaixo imitam os três estilos publicados: posição com zeros à
esquerda e tabulação (PNS), vários blocos ``data`` num arquivo (POF) e
variáveis em sequência, sem ``@`` (PeNSE 2012). O erro que importa é o que
produz dado plausível e errado: coluna deslocada de uma posição, zero à
esquerda perdido, decimal reescalado.
"""

from __future__ import annotations

import io

import polars as pl
import pytest

from guaraci.ibge.fixed_width import parse_sas_input, scan_fixed_width, transcode_to_utf8

_PNS = (
    "/* PROGRAMA DE LEITURA EM SAS DO ARQUIVO DE MICRODADOS DA PNS */\r\n"
    "/* Obs.2: Ajuste o endereço do arquivo \\PNS.txt no comando INFILE */\r\n"
    "data PNS_2019;\r\n"
    "INFILE '...\\dados\\PNS_2019.txt' LRECL=14 missover; \r\n"
    "INPUT   \r\n"
    "@00001\tV0001\t$2.\t \t/*Unidade da Federação*/   \r\n"
    "@00003\tC008\t$3.\t\t\r\n"
    "@000006     V0028      \t\t 8.2   /*Peso*/\r\n"
    "@00014\tA001\t$ 1.\r\n"
    ";\r\n"
    "RUN;\r\n"
)

_POF = (
    "/* REGISTRO - DOMICILIO */\r\n"
    "data domicilio;\r\n"
    'INFILE ".....\\domicilio.txt";\r\n'
    "INPUT\r\n"
    "@01  UF                      2.\r\n"
    "@03  PESO                    5.2\r\n"
    ";\r\n"
    "run;\r\n"
    "data morador;\r\n"
    'INFILE "....\\MORADOR.txt";\r\n'
    "INPUT\r\n"
    "@01  UF   2.  @03 COD  $3.\r\n"
    ";\r\n"
    "run;\r\n"
)

_PENSE_2012 = (
    "DATA ESCOLAS;\r\n"
    "INFILE \t\t'PASTA ONDE ESTÁ O ARQUIVO\\pense2012Escolas.txt'\tlrecl=12;\r\n"
    "INPUT\t\r\n"
    "/*****VARIÁVEIS DE ESCOLA*****/\t\r\n"
    "ID_ESCOLA\t4.\t/*Identificação da escola*/\r\n"
    "CODMUN \t\t7. /* CÓDIGO DO MUNICÍPIO */\r\n"
    "DEPENDADM\t$1.\r\n"
    ";\r\n"
)


def test_pns_style_zero_padded_positions_labels_and_spaced_format():
    (block,) = parse_sas_input(_PNS)
    assert block.name == "PNS_2019"
    assert block.infile == "PNS_2019.txt"
    assert block.lrecl == 14
    names = [(c.name, c.start, c.width, c.is_char, c.decimals) for c in block.columns]
    assert names == [
        ("V0001", 1, 2, True, 0),
        ("C008", 3, 3, True, 0),
        ("V0028", 6, 8, False, 2),
        ("A001", 14, 1, True, 0),
    ]
    assert block.columns[0].label == "Unidade da Federação"
    assert block.columns[1].label is None  # o rótulo da linha seguinte não vaza
    assert block.columns[2].label == "Peso"
    assert block.layout_warning() is None


def test_pof_style_has_one_block_per_data_step():
    blocks = parse_sas_input(_POF)
    assert [(b.name, b.infile) for b in blocks] == [
        ("domicilio", "domicilio.txt"),
        ("morador", "MORADOR.txt"),
    ]
    assert [c.name for c in blocks[1].columns] == ["UF", "COD"]
    assert blocks[1].columns[1].start == 3


def test_pense_2012_style_without_pointer_is_sequential():
    (block,) = parse_sas_input(_PENSE_2012)
    assert block.infile == "pense2012Escolas.txt"
    assert [(c.name, c.start, c.width) for c in block.columns] == [
        ("ID_ESCOLA", 1, 4),
        ("CODMUN", 5, 7),
        ("DEPENDADM", 12, 1),
    ]
    assert block.columns[1].label == "CÓDIGO DO MUNICÍPIO"
    assert block.layout_warning() is None


def test_lrecl_that_does_not_match_the_layout_is_reported():
    (block,) = parse_sas_input(_PNS.replace("LRECL=14", "LRECL=20"))
    assert "20" in block.layout_warning()


def test_duplicated_variable_is_an_error():
    with pytest.raises(ValueError, match="duas vezes"):
        parse_sas_input("data x; input @1 A 1. @2 A 1.; run;")


def test_variable_without_format_is_an_error():
    with pytest.raises(ValueError, match="formato"):
        parse_sas_input("data x; input @1 A @2 B 1.; run;")


def test_slicing_keeps_text_blanks_decimals_and_accents(tmp_path):
    (block,) = parse_sas_input(_PNS)
    raw = (
        "3500700012.501\r\n"  # C008 "007" mantém zeros; peso com ponto explícito
        "11      85.5 \r\n"  # brancos viram vazio; último campo em branco
        "2É\r\n"  # linha curta: campos ausentes ficam vazios; acento cp1252
    ).encode("cp1252")
    target = tmp_path / "pns.utf8"
    transcode_to_utf8(io.BytesIO(raw), target)
    frame = scan_fixed_width(target, block.columns).collect()
    assert all(dtype == pl.String for dtype in frame.dtypes)
    assert frame.rows() == [
        ("35", "007", "00012.50", "1"),  # sem escala: 8.2 não divide por 100
        ("11", "", "85.5", ""),
        ("2É", "", "", ""),
    ]
