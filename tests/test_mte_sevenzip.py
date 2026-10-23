"""Extrator 7z do MTE, sem rede.

Cobre o comando do binário, a escolha do backend, o erro de instalação, o membro
único e (quando há binário ou py7zr) a extração real de um 7z montado no teste.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from guaraci.mte import sevenzip
from guaraci.mte.sevenzip import (
    SevenZipError,
    SevenZipExtractor,
    SevenZipUnavailable,
    check_available,
    find_binary,
)

CSV = "a;b\r\n1;ç\r\n".encode("utf-8")


def test_comando_do_binario_extrai_para_stdout_sem_progresso() -> None:
    cmd = SevenZipExtractor.stream_command("/x/7z", Path("a.7z"))
    assert cmd == ["/x/7z", "x", "-so", "-bd", "-y", "a.7z"]
    assert SevenZipExtractor.list_command("/x/7z", Path("a.7z"))[:3] == ["/x/7z", "l", "-slt"]


def test_find_binary_procura_7z_7za_7zz_no_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    def fake_which(name: str):
        seen.append(name)
        return "/usr/bin/7zz" if name == "7zz" else None

    monkeypatch.setattr(sevenzip.shutil, "which", fake_which)
    assert find_binary() == "/usr/bin/7zz"
    assert seen == ["7z", "7za", "7zz"]


def test_find_binary_cai_no_caminho_padrao_do_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sevenzip.shutil, "which", lambda name: None)
    monkeypatch.setattr(sevenzip.sys, "platform", "win32")
    monkeypatch.setattr(sevenzip.os.path, "isfile", lambda p: p.endswith(r"7-Zip\7z.exe"))
    assert find_binary() == r"C:\Program Files\7-Zip\7z.exe"


def test_sem_binario_nem_py7zr_o_erro_diz_como_instalar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sevenzip, "find_binary", lambda: None)
    monkeypatch.setattr(sevenzip, "_import_py7zr", lambda: None)
    with pytest.raises(SevenZipUnavailable) as err:
        check_available(SevenZipExtractor())
    message = str(err.value)
    assert "7-Zip" in message and "py7zr" in message and "guaraci[trabalho]" in message


def test_backend_prefere_o_binario_e_cai_no_py7zr() -> None:
    assert SevenZipExtractor(binary="/x/7z").backend() == "binary"
    assert SevenZipExtractor(binary="", py7zr_module=object()).backend() == "py7zr"


class _FakeProcess:
    def __init__(self, data: bytes, code: int = 0) -> None:
        import io

        self.stdout = io.BytesIO(data)
        self.code = code
        self.killed = False

    def wait(self) -> int:
        return self.code

    def kill(self) -> None:
        self.killed = True


def _extractor_with(process: _FakeProcess, monkeypatch: pytest.MonkeyPatch, names=("f.txt",)):
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        return process

    extractor = SevenZipExtractor(binary="/x/7z", runner=runner)
    monkeypatch.setattr(extractor, "member_names", lambda archive: list(names))
    return extractor, calls


def test_open_le_o_stdout_do_binario(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    extractor, calls = _extractor_with(_FakeProcess(CSV), monkeypatch)
    with extractor.open(tmp_path / "x.7z") as stream:
        assert stream.read(1 << 20) == CSV
        assert stream.read(1 << 20) == b""
    assert calls[0][:3] == ["/x/7z", "x", "-so"]


def test_codigo_de_saida_diferente_de_zero_apos_ler_tudo_e_erro(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    extractor, _ = _extractor_with(_FakeProcess(CSV, code=2), monkeypatch)
    with pytest.raises(SevenZipError, match="código 2"):
        with extractor.open(tmp_path / "x.7z") as stream:
            while stream.read(1 << 20):
                pass


def test_mais_de_um_membro_e_erro(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    extractor, _ = _extractor_with(_FakeProcess(CSV), monkeypatch, names=("a.txt", "b.txt"))
    with pytest.raises(SevenZipError, match="2 membros"):
        with extractor.open(tmp_path / "x.7z"):
            pass


def test_saida_antecipada_mata_o_processo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = _FakeProcess(CSV)
    extractor, _ = _extractor_with(process, monkeypatch)
    with pytest.raises(RuntimeError):
        with extractor.open(tmp_path / "x.7z"):
            raise RuntimeError("consumidor desistiu")
    assert process.killed


def _make_7z(tmp_path: Path) -> Path:
    binary = find_binary()
    if binary is None:
        pytest.skip("sem binário 7z")
    src = tmp_path / "dado.txt"
    src.write_bytes(CSV)
    archive = tmp_path / "dado.7z"
    subprocess.run([binary, "a", "-bd", str(archive), str(src)], check=True, capture_output=True)
    return archive


def test_extracao_real_com_o_binario_quando_existe(tmp_path: Path) -> None:
    archive = _make_7z(tmp_path)
    extractor = SevenZipExtractor()
    assert extractor.backend() == "binary"
    assert extractor.member_names(archive) == ["dado.txt"]
    with extractor.open(archive) as stream:
        assert stream.read() == CSV


def test_extracao_real_com_py7zr_quando_instalado(tmp_path: Path) -> None:
    py7zr = pytest.importorskip("py7zr")
    archive = tmp_path / "p.7z"
    src = tmp_path / "dado.txt"
    src.write_bytes(CSV)
    with py7zr.SevenZipFile(archive, "w") as handle:
        handle.write(src, "dado.txt")
    extractor = SevenZipExtractor(binary="")
    assert extractor.backend() == "py7zr"
    with extractor.open(archive) as stream:
        assert stream.read() == CSV
