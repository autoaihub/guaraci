"""Leitura de microdados de largura fixa do IBGE a partir do INPUT SAS publicado.

O IBGE descreve o leiaute dos microdados (PNS, POF, PeNSE 2012) num programa
SAS de leitura, e não num dicionário tabular estável. O parser aqui entende o
subconjunto que esses programas usam:

- ``data NOME;`` abre um bloco (a POF tem 16 num arquivo só);
- ``INFILE '...\\arquivo.txt' LRECL=n;`` dá o arquivo e o tamanho do registro;
- ``INPUT`` lista as variáveis, cada uma como ``@<pos> <VAR> [$]<w>.[d]``
  (PNS e POF, posição com ou sem zeros à esquerda) ou só ``<VAR> [$]<w>.[d]``,
  em sequência a partir da posição 1 (PeNSE 2012);
- ``/* rótulo */`` na mesma linha da variável vira o rótulo dela.

As posições são de BYTE. O fatiador decodifica o arquivo em cp1252, que mapeia
um byte para um caractere, e corta por caractere: a posição fica certa mesmo
que o arquivo traga acento. Formatos ``w.d`` não são reescalados: nos arquivos
do IBGE o ponto decimal vem escrito no próprio dado, e o campo sai como texto,
só sem os brancos das pontas.
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, List, Optional, Sequence, Tuple

import polars as pl

__all__ = [
    "SasColumn",
    "SasBlock",
    "parse_sas_input",
    "load_frozen_layout",
    "transcode_to_utf8",
    "scan_fixed_width",
]


@dataclass(frozen=True)
class SasColumn:
    name: str
    start: int  # posição inicial, base 1, em bytes
    width: int
    is_char: bool = False
    decimals: int = 0
    label: Optional[str] = None

    @property
    def end(self) -> int:
        """Última posição ocupada (base 1, inclusiva)."""
        return self.start + self.width - 1


@dataclass
class SasBlock:
    name: str
    infile: Optional[str] = None  # só o nome do arquivo, sem a pasta
    lrecl: Optional[int] = None
    columns: List[SasColumn] = field(default_factory=list)

    @property
    def record_length(self) -> int:
        """Maior posição coberta pelas variáveis declaradas."""
        return max((c.end for c in self.columns), default=0)

    def layout_warning(self) -> Optional[str]:
        """Aviso quando as variáveis passam do LRECL declarado.

        LRECL maior que o fim da última variável é folga normal nos programas
        do IBGE (a PNAD Contínua declara 4000 e usa cerca de 3700) e não avisa.
        """
        if self.lrecl is not None and self.record_length > self.lrecl:
            return (
                f"{self.name}: LRECL declarado {self.lrecl}, variáveis cobrem "
                f"{self.record_length} posições."
            )
        return None


_TOKEN = re.compile(
    r"/\*.*?\*/"  # comentário
    r"|'[^']*'|\"[^\"]*\""  # texto entre aspas
    r"|;"
    r"|[^\s;]+?(?=;|/\*|\s|$)",
    re.S,
)
_FORMAT = re.compile(r"^(\$)?(\d+)\.(\d*)$")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LRECL = re.compile(r"^lrecl=(\d+)$", re.I)


def _tokens(text: str) -> List[Tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def _statements(tokens):
    """Agrupa os tokens em comandos terminados por ``;``."""
    current = []
    for token in tokens:
        if token[0] == ";":
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path.strip().strip("'\""))[-1].strip()


def _parse_input(tokens, text: str, block: SasBlock, context: str) -> None:
    items = [t for t in tokens if not t[0].startswith("/*")]
    comments = [t for t in tokens if t[0].startswith("/*")]
    cursor = 1
    i = 0
    last_end_offset = None
    while i < len(items):
        tok = items[i][0]
        start = None
        if tok.startswith("@"):
            digits = tok[1:]
            if not digits:
                i += 1
                digits = items[i][0] if i < len(items) else ""
            if not digits.isdigit():
                raise ValueError(f"{context}: posição inválida '{tok}{digits}'.")
            start = int(digits)
            i += 1
            if i >= len(items):
                raise ValueError(f"{context}: '@{digits}' sem variável.")
            tok = items[i][0]
        if not _NAME.match(tok):
            raise ValueError(f"{context}: token inesperado '{tok}' no INPUT.")
        name = tok
        i += 1
        fmt = items[i][0] if i < len(items) else ""
        if fmt == "$" and i + 1 < len(items):
            i += 1
            fmt = "$" + items[i][0]
        match = _FORMAT.match(fmt)
        if not match:
            raise ValueError(f"{context}: variável {name} sem formato w. reconhecível ('{fmt}').")
        last_end_offset = items[i][2]
        i += 1
        width = int(match.group(2))
        if width <= 0:
            raise ValueError(f"{context}: variável {name} com largura zero.")
        begin = start if start is not None else cursor
        label = None
        for comment, c_start, _ in comments:
            if c_start >= last_end_offset:
                if "\n" not in text[last_end_offset:c_start]:
                    label = comment[2:-2].strip() or None
                break
        block.columns.append(
            SasColumn(
                name=name,
                start=begin,
                width=width,
                is_char=bool(match.group(1)),
                decimals=int(match.group(3) or 0),
                label=label,
            )
        )
        cursor = begin + width


def parse_sas_input(text: str) -> List[SasBlock]:
    """Lê um programa SAS de leitura e devolve um bloco por ``data``.

    Variáveis declaradas fora de um ``data`` (arquivo só com INPUT) caem num
    bloco sem nome. Nomes repetidos no mesmo bloco são erro: a saída teria
    duas colunas iguais.
    """
    blocks: List[SasBlock] = []
    current: Optional[SasBlock] = None
    for statement in _statements(_tokens(text)):
        words = [t for t in statement if not t[0].startswith("/*")]
        if not words:
            continue
        keyword = words[0][0].lower()
        if keyword == "data":
            current = SasBlock(name=words[1][0] if len(words) > 1 else f"bloco{len(blocks) + 1}")
            blocks.append(current)
        elif keyword == "infile":
            if current is None:
                current = SasBlock(name=f"bloco{len(blocks) + 1}")
                blocks.append(current)
            for word, _, _ in words[1:]:
                if word[:1] in "'\"":
                    current.infile = _basename(word)
                lrecl = _LRECL.match(word)
                if lrecl:
                    current.lrecl = int(lrecl.group(1))
        elif keyword == "input":
            if current is None:
                current = SasBlock(name=f"bloco{len(blocks) + 1}")
                blocks.append(current)
            first = statement.index(words[0])
            _parse_input(statement[first + 1 :], text, current, context=current.name)
    for block in blocks:
        seen = set()
        for column in block.columns:
            if column.name in seen:
                raise ValueError(f"{block.name}: variável {column.name} declarada duas vezes.")
            seen.add(column.name)
    return [b for b in blocks if b.columns]


def load_frozen_layout(path: Path, *, name: str = "congelado") -> SasBlock:
    """Lê um leiaute congelado em CSV (``nome,inicio,largura,texto,decimais``).

    Serve às edições cujo leiaute o IBGE só publicou em planilha (PeNSE 2009).
    Linhas que começam por ``#`` são comentário de origem.
    """
    block = SasBlock(name=name)
    lines = [
        line
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    header = lines[0].split(",")
    if header != ["nome", "inicio", "largura", "texto", "decimais"]:
        raise ValueError(f"{path}: cabeçalho inesperado {header}.")
    seen = set()
    for line in lines[1:]:
        nome, inicio, largura, texto, decimais = line.split(",")
        if nome in seen:
            raise ValueError(f"{path}: variável {nome} declarada duas vezes.")
        seen.add(nome)
        block.columns.append(
            SasColumn(nome, int(inicio), int(largura), texto == "1", int(decimais))
        )
    return block


def transcode_to_utf8(source: BinaryIO, target: Path, encoding: str = "cp1252") -> None:
    """Copia um fluxo de bytes para ``target`` em UTF-8, em blocos de 1 MB.

    Byte sem caractere na codificação vira o caractere de substituição, que
    também ocupa uma posição: o alinhamento das colunas se mantém.
    """
    decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
    with open(target, "w", encoding="utf-8", newline="") as sink:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            sink.write(decoder.decode(chunk))
        sink.write(decoder.decode(b"", final=True))


_LINE = "_linha"


def scan_fixed_width(path: Path, columns: Sequence[SasColumn]) -> pl.LazyFrame:
    """Frame preguiçoso com uma coluna de texto por variável, a partir de um arquivo UTF-8.

    Cada linha entra inteira como uma coluna só (separador que não ocorre no
    dado, sem aspas) e é cortada pelo polars, sem laço Python por registro.
    Linha mais curta que o leiaute (brancos finais cortados) dá campo vazio.
    """
    frame = pl.scan_csv(
        path,
        has_header=False,
        separator="\x1f",
        quote_char=None,
        infer_schema=False,
        new_columns=[_LINE],
    )
    line = pl.col(_LINE)
    return frame.select(
        [
            line.str.slice(c.start - 1, c.width).str.strip_chars(" \t\r\n").alias(c.name)
            for c in columns
        ]
    )
