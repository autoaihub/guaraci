"""SICONFI: todos os anexos da DCA e do RREO, sem filtro de função.

Complementa ``siconfi_dca_despesa_funcao`` (DCA Anexo I-E, só Saúde) e
``siconfi_rreo_saude`` (RREO Anexo 02, só Saúde). Verificado ao vivo em 2026-11-14: sem
``no_anexo`` a API devolve todos os anexos do ente numa só consulta, então a chamada é feita
sem ele e o filtro por anexo, quando pedido, é local (SP, 2022: 3.478 linhas de DCA em sete
anexos, 4.365 de RREO no 6o bimestre em onze).

DCA: Anexos I-AB (balanço patrimonial), I-C, I-D, I-E, I-F, I-G e I-HI; município pequeno
não tem I-F e I-G. Os exercícios de 2013 chegam com o nome ``Anexo I-E`` (sem o prefixo
``DCA-``) e os de 2014 em diante com ``DCA-Anexo I-E``; o nome fica como a API publica.
2012 e antes voltam vazios. RREO: Anexos 01 a 04, 06, 07, 09, 10 (RPPS), 11, 13 e 14,
bimestral, desde 2015. Valores como a API publica; sem dado pessoal.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from guaraci.tesouro.rreo import SiconfiRreoSaudeDataSource
from guaraci.tesouro.siconfi import (
    SiconfiClient,
    SiconfiDcaDespesaFuncaoDataSource,
    _as_list,
)

__all__ = ["SiconfiDcaAnexosDataSource", "SiconfiRreoAnexosDataSource"]


def _norm(anexo: str) -> str:
    """Compara anexos sem o prefixo do tipo e de 'Anexo', sem caixa e sem espaços repetidos."""
    text = " ".join(str(anexo).split()).lower()
    for prefix in ("dca-", "rreo-"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text[len("anexo ") :] if text.startswith("anexo ") else text


class _AllAnexosClient:
    """Pede o ente sem ``no_anexo`` e deixa passar só os anexos pedidos (todos, se vazio)."""

    def __init__(self, inner: SiconfiClient, anexos: Sequence[str]) -> None:
        self._inner = inner
        self._wanted = {_norm(a) for a in anexos}

    @property
    def base_url(self) -> str:
        return self._inner.base_url

    def list_entes(self):
        return self._inner.list_entes()

    def _keep(self, items: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
        if not self._wanted:
            return list(items)
        return [i for i in items if _norm(str(i.get("anexo", ""))) in self._wanted]

    def dca_items(self, year: int, ente: object, anexo: str):
        return self._keep(
            self._inner.paginate("dca", {"an_exercicio": year, "id_ente": ente})
        )

    def paginate(self, path: str, params: Dict[str, object]):
        params = {k: v for k, v in params.items() if k != "no_anexo"}
        return iter(self._keep(self._inner.paginate(path, params)))


class SiconfiDcaAnexosDataSource(SiconfiDcaDespesaFuncaoDataSource):
    DATASET = "siconfi_dca_anexos"
    MIN_YEAR = 2013

    def download(  # type: ignore[override]
        self,
        *,
        anexos: Optional[Sequence[str]] = None,
        api_base_url: Optional[str] = None,
        timeout: int = SiconfiClient.DEFAULT_TIMEOUT,
        **kwargs,
    ):
        inner = self._client or SiconfiClient(base_url=api_base_url, timeout_seconds=timeout)
        self._client = _AllAnexosClient(inner, _as_list(anexos))
        try:
            return super().download(funcao="todas", timeout=timeout, **kwargs)
        finally:
            self._client = inner


class SiconfiRreoAnexosDataSource(SiconfiRreoSaudeDataSource):
    DATASET = "siconfi_rreo_anexos"

    def download(  # type: ignore[override]
        self,
        *,
        anexos: Optional[Sequence[str]] = None,
        api_base_url: Optional[str] = None,
        timeout: int = SiconfiClient.DEFAULT_TIMEOUT,
        **kwargs,
    ):
        inner = self._client or SiconfiClient(base_url=api_base_url, timeout_seconds=timeout)
        self._client = _AllAnexosClient(inner, _as_list(anexos))
        try:
            return super().download(conta="", timeout=timeout, **kwargs)
        finally:
            self._client = inner
