"""CID-10 do DATASUS: capítulos, grupos, categorias e subcategorias (e a morfologia CID-O).

``http://www2.datasus.gov.br/cid10/V2008/downloads/CID10CSV.zip`` (HTTP 200 em
2026-11-14, 297 KB, última modificação 2014-10-13) traz seis CSVs em ISO-8859-1
com separador ``;``. Os arquivos ``.DBF`` da mesma página não entram.
"""

from __future__ import annotations

from guaraci.referencias.zip_csv import ZipCsvDataSource


class Cid10DataSource(ZipCsvDataSource):
    DATASET = "cid10_datasus"
    URL = "http://www2.datasus.gov.br/cid10/V2008/downloads/CID10CSV.zip"
    ENCODING = "iso-8859-1"
