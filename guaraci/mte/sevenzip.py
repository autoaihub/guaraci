"""Extração de arquivos 7z em fluxo (microdados do MTE: Novo CAGED e RAIS).

O MTE publica tudo em 7z, e a biblioteca padrão do Python não lê esse formato.
O extrator tenta, nesta ordem:

1. o binário ``7z``, ``7za`` ou ``7zz`` no ``PATH`` (no Windows, também
   ``C:\\Program Files\\7-Zip\\7z.exe``), com ``x -so``: o conteúdo sai em fluxo,
   sem escrever o CSV descompactado em disco;
2. o pacote ``py7zr`` (extra opcional ``trabalho``), que só extrai para disco: o
   conteúdo vai a um diretório temporário, apagado ao fim.

Sem nenhum dos dois, o erro diz como instalar. Todo arquivo do MTE traz um único
membro; mais de um é erro, para não concatenar tabelas diferentes sem aviso.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, List, Optional

__all__ = [
    "BINARY_NAMES",
    "INSTALL_HINT",
    "SevenZipError",
    "SevenZipExtractor",
    "SevenZipUnavailable",
    "check_available",
    "default_extractor",
    "find_binary",
]

BINARY_NAMES = ("7z", "7za", "7zz")
_WINDOWS_PATHS = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
)
INSTALL_HINT = (
    "Instale o 7-Zip (https://www.7-zip.org/; no Linux, o pacote p7zip-full ou 7zip) "
    "ou o pacote Python py7zr (pip install 'guaraci[trabalho]')."
)


class SevenZipError(RuntimeError):
    """O 7z falhou ao ler o arquivo (corrompido, truncado ou com membros demais)."""


class SevenZipUnavailable(SevenZipError):
    """Nem o binário 7z nem o py7zr estão disponíveis."""


def find_binary() -> Optional[str]:
    """Caminho do binário do 7-Zip, ou ``None`` se não houver."""
    for name in BINARY_NAMES:
        found = shutil.which(name)
        if found:
            return found
    if sys.platform.startswith("win"):
        for candidate in _WINDOWS_PATHS:
            if os.path.isfile(candidate):
                return candidate
    return None


def _import_py7zr():
    try:
        import py7zr  # type: ignore
    except ImportError:
        return None
    return py7zr


class _Stream:
    """Leitor do ``stdout`` do 7z que anota se chegou ao fim do fluxo."""

    def __init__(self, process: "subprocess.Popen[bytes]") -> None:
        self._process = process
        self.eof = False

    def read(self, size: int = -1) -> bytes:
        data = self._process.stdout.read(size)  # type: ignore[union-attr]
        if not data:
            self.eof = True
        return data


class SevenZipExtractor:
    """Abre o único membro de um 7z como fluxo de bytes.

    ``binary`` e ``py7zr_module`` são injetáveis para teste. ``binary=""`` desliga a
    busca do binário (força o ``py7zr``); ``None`` deixa :func:`find_binary` decidir.
    """

    def __init__(
        self,
        *,
        binary: Optional[str] = None,
        py7zr_module: object = None,
        runner: Callable[..., "subprocess.Popen[bytes]"] = subprocess.Popen,
    ) -> None:
        self._binary = binary
        self._py7zr = py7zr_module
        self._runner = runner

    def _resolve_binary(self) -> Optional[str]:
        if self._binary is not None:
            return self._binary or None
        return find_binary()

    def _resolve_py7zr(self):
        return self._py7zr if self._py7zr is not None else _import_py7zr()

    @staticmethod
    def stream_command(binary: str, archive: Path) -> List[str]:
        """Comando que escreve o conteúdo do 7z no ``stdout`` (``-bd``: sem barra de progresso)."""
        return [binary, "x", "-so", "-bd", "-y", str(archive)]

    @staticmethod
    def list_command(binary: str, archive: Path) -> List[str]:
        return [binary, "l", "-slt", "-ba", "-bd", str(archive)]

    def backend(self) -> str:
        """``"binary"`` ou ``"py7zr"``; levanta :class:`SevenZipUnavailable` sem nenhum."""
        if self._resolve_binary():
            return "binary"
        if self._resolve_py7zr() is not None:
            return "py7zr"
        raise SevenZipUnavailable(
            "Nenhum extrator 7z disponível (binário 7z/7za/7zz no PATH ou pacote py7zr). "
            + INSTALL_HINT
        )

    def member_names(self, archive: Path) -> List[str]:
        """Nomes dos arquivos dentro do 7z."""
        if self.backend() == "binary":
            binary = self._resolve_binary()
            done = subprocess.run(
                self.list_command(str(binary), archive), capture_output=True, check=False
            )
            if done.returncode != 0:
                raise SevenZipError(
                    f"7z não leu '{archive.name}' (código {done.returncode}): "
                    f"{done.stderr.decode('utf-8', 'replace').strip()[:300]}"
                )
            names: List[str] = []
            current: dict = {}
            for raw in done.stdout.decode("utf-8", "replace").splitlines() + [""]:
                line = raw.rstrip()
                if not line:
                    if current.get("Path") and current.get("Folder") != "+":
                        names.append(current["Path"])
                    current = {}
                    continue
                key, sep, value = line.partition(" = ")
                if sep:
                    current[key] = value
            return names
        py7zr = self._resolve_py7zr()
        with py7zr.SevenZipFile(archive, "r") as handle:  # type: ignore[union-attr]
            return [name for name in handle.getnames() if not name.endswith("/")]

    @contextlib.contextmanager
    def open(self, archive: Path) -> Iterator[BinaryIO]:
        """Abre o conteúdo do único membro do 7z. Fecha e limpa ao sair do bloco."""
        archive = Path(archive)
        names = self.member_names(archive)
        if len(names) != 1:
            raise SevenZipError(
                f"'{archive.name}' tem {len(names)} membros {names}; esperado exatamente um."
            )
        if self.backend() == "binary":
            with self._open_binary(archive) as stream:
                yield stream  # type: ignore[misc]
        else:
            with self._open_py7zr(archive, names[0]) as stream:
                yield stream

    @contextlib.contextmanager
    def _open_binary(self, archive: Path) -> Iterator[_Stream]:
        binary = str(self._resolve_binary())
        with tempfile.TemporaryFile() as errors:
            process = self._runner(
                self.stream_command(binary, archive),
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            stream = _Stream(process)
            try:
                yield stream
            except BaseException:
                process.kill()
                process.wait()
                raise
            finally:
                if process.stdout is not None:
                    process.stdout.close()
            code = process.wait()
            if code != 0 and stream.eof:
                errors.seek(0)
                detail = errors.read().decode("utf-8", "replace").strip()[:300]
                raise SevenZipError(
                    f"7z falhou ao extrair '{archive.name}' (código {code}): {detail}"
                )

    @contextlib.contextmanager
    def _open_py7zr(self, archive: Path, member: str) -> Iterator[BinaryIO]:
        py7zr = self._resolve_py7zr()
        workdir = Path(tempfile.mkdtemp(prefix="guaraci_7z_"))
        try:
            with py7zr.SevenZipFile(archive, "r") as handle:  # type: ignore[union-attr]
                handle.extract(path=workdir, targets=[member])
            with open(workdir / member, "rb") as stream:
                yield stream
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def default_extractor() -> SevenZipExtractor:
    return SevenZipExtractor()


def check_available(extractor: Optional[SevenZipExtractor] = None) -> str:
    """Falha cedo (antes de baixar GB) se não há extrator. Devolve o backend escolhido."""
    return (extractor or default_extractor()).backend()
