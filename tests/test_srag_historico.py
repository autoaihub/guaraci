"""Bancos históricos de SRAG (2009-2012 e 2013-2018), sem rede.

Três defeitos apareceram na primeira coleta real (24/09/2026), e cada um
produzia falha de conversão ou recurso sumido sem motivo visível:

- o CSV desses bancos não passa pelo bucket S3, e sim pela CDN do Ministério;
- todo CSV de SRAG usa ``;``, e o conversor lia com vírgula;
- o banco de 2016 vem em latin-1, e o polars só lê UTF-8.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from guaraci.opendatasus.portal_files import (
    PortalFileDataSource,
    _csv_separator,
    _utf8_csv,
    parse_resource_s3_url,
)
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.ledger import STATUS_OK, Ledger, LedgerRow
from guaraci.orchestrator.planner import plan_backfill, plan_update

SLUG = "srag-2009-2012"
CDN = "https://d26692udehoye.cloudfront.net/SRAG/2009-2012"
S3 = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG"


def _id(digit: str) -> str:
    """ID no formato UUID que o parser exige, como os do portal."""
    return "-".join(digit * n for n in (8, 4, 4, 4, 12))


# Nomes como o portal publica: cada ano três vezes, sem formato no nome, mais
# o agregado "2009 a 2012" e os anexos não tabulares.
_RESOURCES = {
    _id("0"): ("Dicionário de Dados", None),
    _id("1"): ("Gripe influenza 2009 a 2012", f"{CDN}/INFLUD09-12.csv"),
    _id("2"): ("Gripe influenza 2009", f"{CDN}/INFLUD09.csv"),
    _id("3"): ("Gripe influenza 2009", f"{S3}/xml/INFLUD09.xml.zip"),
    _id("4"): ("Gripe influenza 2009", f"{S3}/json/INFLUD09.json.zip"),
    _id("5"): ("Gripe influenza 2010", f"{CDN}/INFLUD10.csv"),
    _id("6"): ("Gripe influenza 2010", f"{S3}/json/INFLUD10.json.zip"),
}


def _card(resource_id: str, name: str) -> str:
    # Mesma marcação dos cartões reais (ver test_portal_files_datasource.py):
    # o nome mora num div irmão, antes do link "Explorar".
    return f"""
    <div class="br-card rounder-md"><div class="card-content d-flex">
      <div class="p-2 m-0 ml-md-2">
        <div class="text-weight-bold" style="margin-bottom:10px">{name}</div>
      </div>
      <div class="d-none d-md-block">
        <a class="br-button primary" href="/dataset/{SLUG}/resource/{resource_id}">Explorar</a>
      </div>
    </div></div>
    """


class _Client:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.downloads: list[str] = []

    def get_dataset_page(self, slug: str) -> str:
        assert slug == SLUG
        return "<html><body>" + "".join(_card(k, n) for k, (n, _) in _RESOURCES.items()) + "</body></html>"

    def get_resource_page(self, slug: str, resource_id: str) -> str:
        url = _RESOURCES[resource_id][1]
        # A página real também carrega assets de CDN que não são o arquivo.
        asset = '<link href="https://d1abc.cloudfront.net/fonts/rawline.css">'
        link = f'<a href="{url}" class="resource-url-analytics">Baixar</a>' if url else ""
        return f"<html><head>{asset}</head><body>{link}</body></html>"

    def head_content_length(self, url: str) -> int:
        return 1024

    def download_file(self, url: str, destination, **_kwargs) -> int:  # noqa: ANN001
        self.downloads.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)
        return len(self.payload)


# --- URL do recurso ---------------------------------------------------------


def test_cdn_data_url_is_found_when_the_page_has_no_s3_link():
    html = (
        '<link href="https://d1abc.cloudfront.net/fonts/rawline.css">'
        f'<a href="{CDN}/INFLUD09.csv">Baixar</a>'
    )
    assert parse_resource_s3_url(html) == f"{CDN}/INFLUD09.csv"


def test_s3_link_still_wins_over_the_cdn():
    html = f'<a href="{CDN}/INFLUD09.csv">x</a><a href="{S3}/json/INFLUD09.json.zip">y</a>'
    assert parse_resource_s3_url(html) == f"{S3}/json/INFLUD09.json.zip"


def test_cdn_asset_that_is_not_data_is_ignored():
    assert parse_resource_s3_url('<link href="https://d1abc.cloudfront.net/fonts/rawline.css">') is None


# --- descoberta -------------------------------------------------------------


def test_discovery_keeps_one_csv_per_year_and_drops_the_aggregate(tmp_path):
    source = PortalFileDataSource(output_path=str(tmp_path), client=_Client())
    found = source.discover(dataset="srag_arquivos_2009_2012")
    years = sorted({item["year"] for item in found["resources"]})
    assert years == [2009, 2010]
    assert all("INFLUD09-12" not in item["url"] for item in found["resources"])
    best = PortalFileDataSource._select_best_per_year(
        source._discover_resources(_Client(), source._resolve_spec("srag_arquivos_2009_2012")),
        source._resolve_spec("srag_arquivos_2009_2012"),
    )
    assert [(item.year, item.format) for item in best] == [(2009, "csv"), (2010, "csv")]


# --- conversão --------------------------------------------------------------

_HEADER = b"DT_NOTIFIC;SG_UF_NOT;OUTRO_DES\r\n"


def test_semicolon_separator_is_detected(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes(_HEADER + b"10/08/2009;31;TOSSE, FEBRE\r\n")
    assert _csv_separator(path) == ";"
    comma = tmp_path / "b.csv"
    comma.write_bytes(b"a,b;c\n1,2\n")
    assert _csv_separator(comma) == ","


def test_utf8_file_is_used_as_is(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes(_HEADER + "10/08/2009;31;VÔMITOS\r\n".encode("utf-8"))
    assert _utf8_csv(path) == path


def test_latin1_file_is_transcoded_byte_faithfully(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes(_HEADER + "10/08/2016;35;VÔMITOS\r\n".encode("latin-1"))
    converted = _utf8_csv(path)
    assert converted != path
    assert "VÔMITOS" in converted.read_text(encoding="utf-8")
    assert path.read_bytes().endswith("VÔMITOS\r\n".encode("latin-1"))  # original intacto


def test_latin1_semicolon_csv_converts_to_parquet(tmp_path):
    payload = _HEADER + "10/08/2016;35;VÔMITOS\r\n14/08/2016;50;TOSSE, FEBRE\r\n".encode("latin-1")
    client = _Client(payload)
    source = PortalFileDataSource(output_path=str(tmp_path), client=client)
    result = source.download(
        dataset="srag_arquivos_2009_2012",
        start_year=2009,
        end_year=2009,
        output_format="parquet",
        output_dir=str(tmp_path),
    )
    assert client.downloads == [f"{CDN}/INFLUD09.csv"]
    [exported] = result["exported_files"]
    frame = pl.read_parquet(exported)
    assert frame.columns == ["DT_NOTIFIC", "SG_UF_NOT", "OUTRO_DES"]
    assert frame["OUTRO_DES"].to_list() == ["VÔMITOS", "TOSSE, FEBRE"]
    assert not list(Path(tmp_path).rglob("*.utf8.tmp.csv"))  # cópia temporária removida


# --- orquestrador -----------------------------------------------------------


def _ok(source: str, year: int) -> LedgerRow:
    return LedgerRow(
        run_id="r", ts_utc="t", source=source, kind="api_window", granularity="annual",
        status=STATUS_OK, partition_key=f"{source}||||||{year}", year=year,
    )


@pytest.mark.parametrize(
    "source,years",
    [("srag_arquivos_2009_2012", [2009, 2010, 2011, 2012]),
     ("srag_arquivos_2013_2018", [2013, 2014, 2015, 2016, 2017, 2018])],
)
def test_frozen_bank_backfills_exactly_its_published_years(source, years):
    profile = profile_for(source, "opendatasus files")
    assert profile.max_year == years[-1]
    assert [u.year for u in plan_backfill(profile, current_year=2026)] == years


def test_frozen_bank_update_stops_once_the_last_year_is_in(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    profile = profile_for("srag_arquivos_2009_2012", "opendatasus files")
    assert [u.year for u in plan_update(profile, ledger, current_year=2026)] == [2009, 2010, 2011, 2012]
    ledger.append(_ok("srag_arquivos_2009_2012", 2012))
    assert plan_update(profile, ledger, current_year=2026) == []


def test_live_bank_keeps_its_open_ended_update(tmp_path):
    profile = profile_for("srag_arquivos", "opendatasus files")
    assert profile.max_year is None
    units = plan_update(profile, Ledger(tmp_path / "_ledger.csv"), current_year=date.today().year)
    assert [u.year for u in units] == [date.today().year]
