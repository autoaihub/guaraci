"""Regressão: o módulo do SINAN precisa importar sem a dependência opcional.

`pysus` é opcional, e a suíte do Python CI roda sem ela instalada. O bloco de
import definia apenas `PYSUS_AVAILABLE = False` no `except`, deixando o nome
`PySUS` indefinido: quem apenas tocasse o símbolo recebia `AttributeError` em
vez do `ImportError` explicativo que o código levanta de propósito. Era o que
mantinha o Python CI vermelho, no mesmo teste, desde 2026-08-25.
"""

from __future__ import annotations

import importlib
import sys

import pytest


class _PysusAusente:
    """Finder que responde como se o pacote não estivesse instalado."""

    def find_spec(self, name, path=None, target=None):  # noqa: ANN001, ANN201
        if name == "pysus" or name.startswith("pysus."):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return None


@pytest.fixture
def sinan_sem_pysus(monkeypatch):
    """Recarrega `guaraci.datasus.sinan` com o pysus fora de alcance."""
    bloqueio = _PysusAusente()
    monkeypatch.setattr(sys, "meta_path", [bloqueio, *sys.meta_path])
    for nome in [n for n in sys.modules if n == "pysus" or n.startswith("pysus.")]:
        monkeypatch.delitem(sys.modules, nome, raising=False)

    modulo = importlib.import_module("guaraci.datasus.sinan")
    recarregado = importlib.reload(modulo)
    yield recarregado
    # Devolve o módulo ao estado real para não contaminar os demais testes.
    monkeypatch.undo()
    importlib.reload(recarregado)


def test_modulo_importa_sem_a_dependencia(sinan_sem_pysus) -> None:
    assert sinan_sem_pysus.PYSUS_AVAILABLE is False


def test_simbolo_existe_mesmo_sem_a_dependencia(sinan_sem_pysus) -> None:
    """Sem isto, `sinan.PySUS` levantava AttributeError em vez de valer None."""
    assert hasattr(sinan_sem_pysus, "PySUS")
    assert sinan_sem_pysus.PySUS is None
    assert hasattr(sinan_sem_pysus, "pysus")
    assert sinan_sem_pysus.pysus is None


def test_coleta_pelo_backend_pysus_falha_com_erro_explicativo(
    sinan_sem_pysus, tmp_path, monkeypatch
) -> None:
    """O erro precisa dizer o que instalar, e não estourar num atributo.

    O backend padrão é o FTP direto, que não depende do pysus; o caminho que
    exige a biblioteca só é escolhido por variável de ambiente.
    """
    monkeypatch.setenv("GUARACI_DATASUS_BACKEND", "pysus")
    fonte = sinan_sem_pysus.SinanDataSource(output_path=str(tmp_path))

    with pytest.raises(ImportError, match="PySUS is required"):
        fonte.download(start_year=2023, end_year=2023, diseases=["RAIV"])
