"""Leitores de formatos que o ``HttpFileDataSource`` não cobre (DBF e largura fixa com ``.dct``).

``HttpFileDataSource`` já baixa, compara por HEAD, grava em fluxo e exporta CSV, texto de
zip e xlsx. Os inquéritos de saúde antigos vêm em DBF (SB Brasil) e em largura fixa com
dicionário Stata (PNDS 2006). A fonte abaixo reaproveita todo o download e troca só a
exportação: cada leitor recebe o arquivo baixado e devolve pares ``(sufixo, frame)``, com todas
as colunas como texto, como o resto do bronze.
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

import polars as pl

from guaraci.arquivos.http_files import (
    HttpFile,
    HttpFileClient,
    HttpFileDataSource,
    HttpResource,
    _sink_atomic,
    _slug,
)
from guaraci.core.datasource import DataSource

__all__ = ["Leitor", "datasource_com_leitor", "ler_dbf", "ler_largura_fixa"]

# ``(arquivo baixado, avisos)`` para pares ``(sufixo, frame)``. Sufixo vazio = arquivo único.
Leitor = Callable[[Path, List[str]], Iterator[Tuple[str, pl.DataFrame]]]

_REPLACEMENT = chr(0xFFFD)


def _texto(valor: Optional[bytes], encoding: str, avisos: List[str], aviso: str) -> Optional[str]:
    if valor is None:
        return None
    text = valor.decode(encoding, errors="replace").strip()
    if _REPLACEMENT in text and aviso not in avisos:
        avisos.append(aviso)
    return text or None


def _dbf_para_frame(path: Path, encoding: str, avisos: List[str], rotulo: str) -> pl.DataFrame:
    try:
        from dbfread import DBF
    except ImportError as exc:  # pragma: no cover - depende do extra ``datasus``
        raise ValueError("Ler DBF exige o pacote dbfread (pip install guaraci[datasus]).") from exc
    # ``raw=True`` entrega os bytes de cada campo, sem converter número ou data: o bronze
    # guarda o texto que o órgão publicou (só o preenchimento com brancos sai).
    table = DBF(str(path), raw=True, recfactory=lambda items: [v for _, v in items])
    names = [n.strip() for n in table.field_names]
    aviso = f"{rotulo}: bytes inválidos em {encoding} foram trocados por U+FFFD."
    rows = [[_texto(v, encoding, avisos, aviso) for v in record] for record in table]
    return pl.DataFrame(rows, schema={n: pl.String for n in names}, orient="row")


def ler_dbf(encoding: str = "cp1252") -> Leitor:
    """DBF solto ou dentro de zip (uma tabela por membro ``.dbf``; o resto do zip é ignorado)."""

    def leitor(raw: Path, avisos: List[str]) -> Iterator[Tuple[str, pl.DataFrame]]:
        if not zipfile.is_zipfile(raw):
            yield "", _dbf_para_frame(raw, encoding, avisos, raw.name)
            return
        with zipfile.ZipFile(raw) as archive:
            membros = sorted(
                n for n in archive.namelist() if n.lower().endswith(".dbf") and not n.endswith("/")
            )
            if not membros:
                raise ValueError(f"{raw.name} não tem nenhum membro .dbf.")
            for membro in membros:
                # Cópia com nome fixo numa pasta temporária: o nome do membro nunca vira
                # caminho (zip é dado não confiável).
                with tempfile.TemporaryDirectory(dir=raw.parent) as tmp:
                    destino = Path(tmp) / "dados.dbf"
                    destino.write_bytes(archive.read(membro))
                    frame = _dbf_para_frame(destino, encoding, avisos, f"{raw.name}:{membro}")
                yield (_slug(Path(membro).stem) if len(membros) > 1 else ""), frame

    return leitor


_COLUNA_DCT = re.compile(r"^\s*(\w+)\s+(\S+)\s+(\d+):\s+(\d+)-(\d+)\s*$")


def _colunas_dct(texto: str, rotulo: str) -> List[Tuple[str, int, int]]:
    """``(nome, início, fim)`` com posições de 1 em 1, lidas do dicionário Stata (``infix``)."""
    colunas = []
    for linha in texto.splitlines():
        achou = _COLUNA_DCT.match(linha)
        if not achou:
            continue
        _tipo, nome, registro, inicio, fim = achou.groups()
        if registro != "1":
            raise ValueError(f"{rotulo}: registro de várias linhas ({registro}:) não é suportado.")
        colunas.append((nome, int(inicio), int(fim)))
    if not colunas:
        raise ValueError(f"{rotulo}: nenhuma coluna reconhecida no dicionário.")
    nomes = [c[0] for c in colunas]
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"{rotulo}: nomes de coluna repetidos no dicionário.")
    return colunas


def ler_largura_fixa(encoding: str = "cp1252") -> Leitor:
    """Zip com pares ``<nome>.dat`` e ``<nome>.dct``: uma tabela por par, com os nomes do ``.dct``."""

    def leitor(raw: Path, avisos: List[str]) -> Iterator[Tuple[str, pl.DataFrame]]:
        with zipfile.ZipFile(raw) as archive:
            nomes = [n for n in archive.namelist() if not n.endswith("/")]
            dados = sorted(n for n in nomes if n.lower().endswith(".dat"))
            if not dados:
                raise ValueError(f"{raw.name} não tem nenhum membro .dat.")
            por_stem = {n[:-4].lower(): n for n in nomes if n.lower().endswith(".dct")}
            for dat in dados:
                dct = por_stem.get(dat[:-4].lower())
                if dct is None:
                    raise ValueError(f"{raw.name}: {dat} não tem o .dct de mesmo nome.")
                colunas = _colunas_dct(
                    archive.read(dct).decode(encoding, errors="replace"), f"{raw.name}:{dct}"
                )
                # O cp1252 tem um byte por caractere, então as posições do ``.dct`` valem
                # sobre o texto já decodificado.
                texto = archive.read(dat).decode(encoding, errors="replace")
                linhas = [linha for linha in texto.splitlines() if linha.strip()]
                frame = pl.DataFrame({"_linha": linhas}, schema={"_linha": pl.String})
                frame = frame.select(
                    [
                        pl.col("_linha")
                        .str.slice(inicio - 1, fim - inicio + 1)
                        .str.strip_chars()
                        .alias(nome)
                        for nome, inicio, fim in colunas
                    ]
                ).with_columns(pl.all().replace("", None))
                yield _slug(Path(dat).stem), frame

    return leitor


class _ExportaPorLeitor(HttpFileDataSource):
    """``HttpFileDataSource`` com spec e leitor fixos; só a exportação muda."""

    SPEC: HttpFile
    LEITOR: Leitor
    # Prefixo tirado do sufixo de cada tabela (``pnds2006_br_mulheres`` -> ``mulheres``).
    PREFIXO: str = ""

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[HttpFileClient] = None,
    ) -> None:
        DataSource.__init__(self, name=self.SPEC.key, output_path=output_path)
        self.spec = self.SPEC
        self._client = client

    def _export_all(
        self,
        raw_path: Path,
        base_dir: Path,
        fmt: str,
        resource: HttpResource,
        multi: bool,
        warnings: Optional[List[str]] = None,
    ) -> List[Path]:
        base = f"{self.name}_{resource.code}" if multi else self.name
        suffix = {"csv": ".csv", "parquet": ".parquet"}.get(fmt, ".sqlite")
        avisos: List[str] = []
        saidas: List[Path] = []
        for sufixo, frame in type(self).LEITOR(raw_path, avisos):
            if self.PREFIXO:
                sufixo = re.sub(f"^{re.escape(self.PREFIXO)}", "", sufixo, flags=re.IGNORECASE)
            nome = f"{base}_{sufixo.lower()}" if sufixo else base
            saidas.append(
                _sink_atomic(frame.lazy(), base_dir / f"{nome}{suffix}", fmt, nome, raw_path.name)
            )
        if warnings is not None:
            warnings.extend(avisos)
        return saidas


def datasource_com_leitor(spec: HttpFile, leitor: Leitor, prefixo: str = "") -> type:
    """Classe de fonte para ``spec`` que exporta pelo ``leitor`` (ver ``_ExportaPorLeitor``)."""
    nome = "".join(parte.title() for parte in spec.key.split("_")) + "DataSource"
    return type(
        nome,
        (_ExportaPorLeitor,),
        {"DATASET": spec.key, "SPEC": spec, "LEITOR": staticmethod(leitor), "PREFIXO": prefixo},
    )
