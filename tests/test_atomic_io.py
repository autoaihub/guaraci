"""Regressão: a troca atômica não pode desistir na primeira recusa do Windows.

``os.replace`` falha com ``PermissionError`` enquanto qualquer outro processo
mantém um handle sobre o destino, mesmo só de leitura. O sintoma foi a
persistência de jobs abortando de forma intermitente ao gravar ``jobs.json``,
com o trabalho registrado em memória e perdido em disco.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guaraci.utils import atomic_io


def _origem(tmp_path: Path, conteudo: str = "novo") -> Path:
    origem = tmp_path / "alvo.json.tmp"
    origem.write_text(conteudo, encoding="utf-8")
    return origem


def test_troca_direta_quando_nada_bloqueia(tmp_path: Path) -> None:
    destino = tmp_path / "alvo.json"
    destino.write_text("antigo", encoding="utf-8")

    atomic_io.replace_with_retry(_origem(tmp_path), destino)

    assert destino.read_text(encoding="utf-8") == "novo"


def test_recusa_transitoria_e_reagendada(tmp_path: Path, monkeypatch) -> None:
    destino = tmp_path / "alvo.json"
    destino.write_text("antigo", encoding="utf-8")
    real = atomic_io.os.replace
    tentativas = {"n": 0}

    def replace_instavel(src, dst):
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(atomic_io.os, "replace", replace_instavel)
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _: None)

    atomic_io.replace_with_retry(_origem(tmp_path), destino)

    assert tentativas["n"] == 3
    assert destino.read_text(encoding="utf-8") == "novo"


def test_bloqueio_persistente_ainda_falha(tmp_path: Path, monkeypatch) -> None:
    """Um handle que nunca solta precisa virar erro, não espera infinita."""
    destino = tmp_path / "alvo.json"
    destino.write_text("antigo", encoding="utf-8")
    chamadas = {"n": 0}

    def replace_travado(src, dst):
        chamadas["n"] += 1
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(atomic_io.os, "replace", replace_travado)
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _: None)

    with pytest.raises(PermissionError):
        atomic_io.replace_with_retry(_origem(tmp_path), destino)

    assert chamadas["n"] == atomic_io._ATTEMPTS
    assert destino.read_text(encoding="utf-8") == "antigo"


def test_jobs_persistem_apesar_de_recusa_transitoria(tmp_path: Path, monkeypatch) -> None:
    """O caminho real que motivou o helper: gravação de jobs.json."""
    from guaraci.services import jobs as jobs_module

    real = atomic_io.os.replace
    estado = {"falhou": False}

    def replace_instavel(src, dst):
        if not estado["falhou"] and str(dst).endswith("jobs.json"):
            estado["falhou"] = True
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(atomic_io.os, "replace", replace_instavel)
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _: None)

    servico = jobs_module.DownloadJobService.__new__(jobs_module.DownloadJobService)
    servico._storage_path = tmp_path / "jobs.json"
    servico._jobs = {}

    servico._persist_jobs_locked()

    assert estado["falhou"], "o teste não exercitou a recusa"
    assert servico._storage_path.read_text(encoding="utf-8") == "[]"
