"""Contexto TLS para hosts cujo servidor envia a cadeia incompleta.

O servidor ``download.inep.gov.br`` manda só o certificado folha (``*.inep.gov.br``,
emitido pela RNP ICPEdu GR46 OV TLS CA 2025) e omite o intermediário. Navegadores
e o Windows completam a cadeia pela extensão AIA do certificado, mas o OpenSSL não
baixa nada sozinho, e por isso a verificação falha no Linux com
``unable to get local issuer certificate``.

A correção mantém a verificação ligada: o intermediário público vem embutido em
``guaraci/data/ca_intermediarios.crt`` e é somado às raízes (certifi, mais o store
do sistema) apenas para os hosts listados abaixo. Os demais hosts seguem com o
contexto padrão do ``urllib``. O intermediário vale até 2030-11-19; se o INEP
trocar de emissor, basta acrescentar o novo certificado ao arquivo.
"""

from __future__ import annotations

import ssl
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

__all__ = ["HOST_SUFFIXES", "INTERMEDIATES_CRT", "ssl_context_for"]

INTERMEDIATES_CRT = Path(__file__).resolve().parent.parent / "data" / "ca_intermediarios.crt"

# Sufixos de host que precisam do intermediário embutido.
HOST_SUFFIXES = (".inep.gov.br",)


def _needs_intermediates(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host.endswith(suffix) for suffix in HOST_SUFFIXES)


@lru_cache(maxsize=1)
def _context_with_intermediates() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi vem com o httpx
        pass
    context.load_verify_locations(cafile=str(INTERMEDIATES_CRT))
    return context


def ssl_context_for(url: str) -> Optional[ssl.SSLContext]:
    """Contexto com o intermediário embutido para o host da URL, ou ``None``.

    ``None`` deixa o ``urlopen`` usar o contexto padrão, com verificação completa.
    """
    if urlsplit(url).scheme != "https":
        return None
    if not _needs_intermediates(urlsplit(url).hostname or ""):
        return None
    return _context_with_intermediates()
