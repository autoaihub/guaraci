"""Regressão: a ajuda da CLI não pode quebrar por codificação de console.

No Windows, `sys.stdout` assume cp1252 sempre que não está ligado a um
terminal UTF-8, o que inclui qualquer redirecionamento para arquivo ou cano.
Como a ajuda traz acentos e a bandeira na descrição do grupo,
`guaraci --help | more` terminava em UnicodeEncodeError antes de imprimir
qualquer coisa útil.
"""

from __future__ import annotations

import io
import subprocess
import sys

import pytest

from guaraci.cli.main import _force_utf8_stdio


class _Stream:
    """Stream mínimo que registra a reconfiguração pedida."""

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        self.reconfigured: dict[str, str] = {}

    def reconfigure(self, *, encoding: str, errors: str) -> None:
        self.reconfigured = {"encoding": encoding, "errors": errors}
        self.encoding = encoding


def _StreamCp1252() -> _Stream:
    return _Stream("cp1252")


def _StreamUtf8() -> _Stream:
    return _Stream("utf-8")


def test_cp1252_stdout_is_switched_to_utf8(monkeypatch) -> None:
    stream = _StreamCp1252()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", _StreamCp1252())

    _force_utf8_stdio()

    assert stream.reconfigured == {"encoding": "utf-8", "errors": "replace"}


def test_utf8_stdout_is_left_alone(monkeypatch) -> None:
    stream = _StreamUtf8()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", _StreamUtf8())

    _force_utf8_stdio()

    assert stream.reconfigured == {}


def test_stream_without_reconfigure_is_tolerated(monkeypatch) -> None:
    """Streams substituídos por captura de teste não têm `reconfigure`."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    _force_utf8_stdio()  # não deve levantar


@pytest.mark.parametrize("comando", [["--help"], ["fetch", "--help"], ["sinan", "--help"]])
def test_help_survives_a_non_utf8_console(comando) -> None:
    """Roda a CLI de verdade com o ambiente forçado na codificação legada."""
    import os

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"

    processo = subprocess.run(
        [sys.executable, "-m", "guaraci.cli.main", *comando],
        capture_output=True,
        env=env,
    )
    assert processo.returncode == 0, processo.stderr.decode("utf-8", "replace")
    assert b"Usage:" in processo.stdout
