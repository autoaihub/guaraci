"""SIGTAP: Tabela Unificada de Procedimentos, Medicamentos e OPM do SUS (DATASUS).

``ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/`` guarda um zip por
competência, ``TabelaUnificada_AAAAMM_vAAMMDDHHMM.zip`` (227 versões em
2026-11-14, cerca de 2 MB cada). Cada zip traz as tabelas em texto de largura
fixa (``tb_*.txt`` e ``rl_*.txt``) e, ao lado de cada uma, ``<tabela>_layout.txt``
com ``Coluna,Tamanho,Inicio,Fim,Tipo``. As colunas saem com os nomes do layout
(``CO_PROCEDIMENTO``, ``NO_PROCEDIMENTO``...), o preenchimento com espaços à
direita é removido e todo valor fica como texto. Uma competência por execução.
"""

from __future__ import annotations

import csv
import ftplib
import io
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from guaraci.arquivos.http_files import HttpFileClient
from guaraci.core.http import request_with_retry
from guaraci.gestao_publica.rest import RowSpool, as_list, finalize_export, normalize_format
from guaraci.referencias.base import ProgressCallback, ReferenciaDataSource

FTP_HOST = "ftp2.datasus.gov.br"
FTP_DIR = "/pub/sistemas/tup/downloads"
ZIP_RE = re.compile(r"^TabelaUnificada_(\d{6})_v(\d+)\.zip$", re.IGNORECASE)
COMPETENCIA_RE = re.compile(r"^\d{6}$")
ENCODING = "cp1252"


def listar_competencias(*, host: str = FTP_HOST, directory: str = FTP_DIR, timeout: int = 60) -> Dict[str, str]:
    """Competência (AAAAMM) -> nome do zip mais recente dela (maior sufixo de versão)."""

    def send() -> List[str]:
        with ftplib.FTP(host, timeout=timeout) as ftp:
            ftp.login()
            return ftp.nlst(directory)

    found: Dict[str, Tuple[int, str]] = {}
    for entry in request_with_retry(send, max_attempts=3):
        name = entry.rsplit("/", 1)[-1]
        match = ZIP_RE.match(name)
        if not match:
            continue
        competencia, versao = match.group(1), int(match.group(2))
        if competencia not in found or versao > found[competencia][0]:
            found[competencia] = (versao, name)
    return {comp: name for comp, (_, name) in sorted(found.items())}


def ler_layout(text: str) -> List[Tuple[str, int, int]]:
    """Linhas ``Coluna,Tamanho,Inicio,Fim,Tipo`` -> (nome, início 0-based, fim exclusivo)."""
    campos: List[Tuple[str, int, int]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4 or not row[2].strip().isdigit():
            continue
        campos.append((row[0].strip(), int(row[2]) - 1, int(row[3])))
    return campos


class SigtapDataSource(ReferenciaDataSource):
    DATASET = "sigtap_tabela_unificada"
    DEFAULT_TIMEOUT = 300

    def download(
        self,
        *,
        competencia: Optional[str] = None,
        tabelas: Optional[Sequence[object]] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        ftp_host: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = self.base_dir(output_dir)
        host = ftp_host or FTP_HOST
        disponiveis = listar_competencias(host=host, timeout=min(int(timeout), 60))
        if not disponiveis:
            raise ValueError("Nenhum zip TabelaUnificada_*.zip encontrado no FTP do DATASUS.")
        escolhida = str(competencia).strip() if competencia else max(disponiveis)
        if not COMPETENCIA_RE.match(escolhida):
            raise ValueError("competencia deve ter o formato AAAAMM (por exemplo 202611).")
        if escolhida not in disponiveis:
            raise ValueError(
                f"Competência {escolhida} não está no FTP; vai de {min(disponiveis)} a {max(disponiveis)}."
            )
        pedidas = {t.lower().removesuffix(".txt") for t in as_list(tabelas)}
        url = f"ftp://{host}{FTP_DIR}/{disponiveis[escolhida]}"
        client = HttpFileClient(timeout_seconds=timeout)
        exported: List[str] = []
        warnings: List[str] = []
        rows_total = 0
        files = 0
        with tempfile.TemporaryDirectory(prefix=f"{self.name}.", dir=str(base_dir)) as tmp:
            raw = Path(tmp) / "origem.zip"
            client.download(url, raw)
            with zipfile.ZipFile(raw) as archive:
                nomes = {n.lower(): n for n in archive.namelist()}
                todas = sorted(
                    n[: -len("_layout.txt")]
                    for n in nomes
                    if n.endswith("_layout.txt") and f"{n[: -len('_layout.txt')]}.txt" in nomes
                )
                desconhecidas = sorted(pedidas - set(todas))
                if desconhecidas:
                    raise ValueError(
                        f"Tabelas inexistentes na competência {escolhida}: {', '.join(desconhecidas)}. "
                        f"Disponíveis: {', '.join(todas)}."
                    )
                alvo = [t for t in todas if not pedidas or t in pedidas]
                if progress_callback is not None:
                    progress_callback({
                        "event": "download_start", "source": self.name, "documents_total": len(alvo),
                    })
                for index, tabela in enumerate(alvo, start=1):
                    rows = self._tabela(
                        archive, nomes, tabela, escolhida, base_dir, fmt, exported, warnings
                    )
                    rows_total += rows
                    files += 1 if rows else 0
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name,
                            "documents_total": len(alvo), "files_completed": index,
                            "file_path": tabela,
                        })
        return self.result(
            base_dir=base_dir, source_url=url, fmt=fmt, exported=exported,
            rows=rows_total, files=files, warnings=warnings,
        )

    def _tabela(
        self, archive: zipfile.ZipFile, nomes: Dict[str, str], tabela: str, competencia: str,
        base_dir: Path, fmt: str, exported: List[str], warnings: List[str],
    ) -> int:
        layout = ler_layout(archive.read(nomes[f"{tabela}_layout.txt"]).decode(ENCODING, errors="replace"))
        if not layout:
            warnings.append(f"{tabela}: layout sem colunas legíveis.")
            return 0
        stem = f"{self.name}_{competencia}_{tabela}"
        colunas = [nome for nome, _, _ in layout]
        spool = RowSpool(base_dir, stem)
        try:
            with io.TextIOWrapper(
                archive.open(nomes[f"{tabela}.txt"]), encoding=ENCODING, errors="replace", newline=""
            ) as texto:
                for line in texto:
                    line = line.rstrip("\r\n")
                    if not line.strip():
                        continue
                    spool.add({nome: line[ini:fim].rstrip() for nome, ini, fim in layout})
        except BaseException:
            spool.discard()
            raise
        rows = spool.rows
        path = spool.write_csv(base_dir / f"{stem}.csv", columns=colunas)
        if path is None:
            warnings.append(f"{tabela}: sem linhas.")
            return 0
        exported.extend(finalize_export(path, fmt, stem))
        return rows
