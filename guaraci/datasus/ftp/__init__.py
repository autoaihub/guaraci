"""Direct DATASUS FTP integration layer (no PySUS dependency).

This package replaces ``pysus`` as the access path to ``ftp.datasus.gov.br``.
It is the implementation of phase 1 described in
``docs/PLANO_DATASUS_FTP_DIRETO.md``: a thin, testable wrapper over the
public anonymous FTP server, with file-name parsing and discovery helpers
that can be reused across SIH, SIM and SINAN.

Public surface:

- :class:`DatasusFtpClient` — async FTP wrapper (over ``ftplib`` via threads)
- :class:`FileRecord`        — immutable identity of a file on the FTP server
- :func:`discover_sih`       — list and filter SIH files in both windows
- :func:`dbc.read`           — DBC file → :class:`polars.DataFrame`
"""

from guaraci.datasus.ftp.catalog import (
    FileRecord,
    System,
    parse,
    parse_sih,
    parse_sim,
    parse_sinan,
)
from guaraci.datasus.ftp.client import DatasusFtpClient, FtpEntry
from guaraci.datasus.ftp.discovery import (
    SIH_CURRENT_PATH,
    SIH_LEGACY_PATH,
    discover_sih,
)

__all__ = [
    "DatasusFtpClient",
    "FileRecord",
    "FtpEntry",
    "SIH_CURRENT_PATH",
    "SIH_LEGACY_PATH",
    "System",
    "discover_sih",
    "parse",
    "parse_sih",
    "parse_sim",
    "parse_sinan",
]
