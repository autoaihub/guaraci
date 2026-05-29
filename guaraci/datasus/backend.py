"""DATASUS backend selection shared by SIH/SIM/SINAN data sources.

Phase 2 of ``docs/PLANO_DATASUS_FTP_DIRETO.md`` introduced a per-source
switch between the legacy PySUS path and the new direct-FTP layer, keyed
on the ``GUARACI_DATASUS_BACKEND`` env var. Phase 3 generalises the same
switch to SIM and SINAN, so the selector lives here in a dependency-free
leaf module that every source can import without risking an import cycle.

Phase 4 flipped :data:`DEFAULT_BACKEND` to ``ftp``; the legacy PySUS path
stays reachable for one release via ``GUARACI_DATASUS_BACKEND=pysus``.
"""

from __future__ import annotations

import os

from loguru import logger

BACKEND_FTP = "ftp"
BACKEND_PYSUS = "pysus"
VALID_BACKENDS = {BACKEND_FTP, BACKEND_PYSUS}

# Phase 4 (PLANO_DATASUS_FTP_DIRETO §6): the direct-FTP layer is the default.
# The legacy PySUS path stays reachable for one release via
# ``GUARACI_DATASUS_BACKEND=pysus`` (and the ``datasus-legacy`` extra).
DEFAULT_BACKEND = BACKEND_FTP

_ENV_VAR = "GUARACI_DATASUS_BACKEND"


def get_datasus_backend(default: str = DEFAULT_BACKEND) -> str:
    """Return the selected DATASUS backend (``"ftp"`` or ``"pysus"``).

    Reads :data:`_ENV_VAR`; an unset or unrecognised value falls back to
    ``default`` (which itself defaults to :data:`DEFAULT_BACKEND`).
    """
    raw = os.environ.get(_ENV_VAR, default).strip().lower()
    if raw not in VALID_BACKENDS:
        logger.warning(
            f"Unknown {_ENV_VAR}={raw!r}; falling back to {default!r}"
        )
        return default
    return raw
