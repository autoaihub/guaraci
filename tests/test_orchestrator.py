"""Unit tests for the bronze orchestrator (guaraci/orchestrator).

Everything here runs offline: the FTP records provider, the FTP client and the
DownloadService are all faked, so the whole sweep — planning, materialisation,
ledger, idempotency, volumetria — is exercised without a network.
"""
from __future__ import annotations

from collections import namedtuple
from pathlib import Path

import polars as pl
import pytest

from guaraci.orchestrator import paths, refine
from guaraci.orchestrator.cadence import (
    CADENCE_OVERRIDES,
    profile_for,
)
from guaraci.orchestrator.ledger import (
    STATUS_EMPTY,
    STATUS_OK,
    STATUS_PLANNED,
    STATUS_SKIPPED,
    Ledger,
    LedgerRow,
)
from guaraci.orchestrator.model import Cadence, FetchUnit, Granularity, Kind
from guaraci.orchestrator.orchestrator import Orchestrator
from guaraci.orchestrator.planner import plan_backfill, plan_update
from guaraci.orchestrator.runner import run_ftp_batch, run_via_service


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeRec:
    """Duck-typed FileRecord."""

    def __init__(self, basename, group, state, year, month=None, size=10, path=None):
        self.basename = basename
        self.group = group
        self.state = state
        self.year = year
        self.month = month
        self.size = size
        self.path = path or f"/dissemin/{basename}"


def sih_records(kind, source, years):
    return [
        FakeRec(f"RDPR{y % 100:02d}01.dbc", "RD", "PR", y, month=1, size=10 + y)
        for y in years
    ]


def sinan_records(kind, source, years):
    return [
        FakeRec(f"DENGBR{y % 100:02d}.dbc", "DENG", None, y, month=None, size=5)
        for y in years
    ]


class FakeClient:
    """Async context manager whose download is a no-op (dbc_reader is faked)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def download(self, remote, local):  # noqa: D401 - no-op
        return None


def good_dbc_reader(path):
    return pl.DataFrame({"UF": ["PR", "PR"], "n": [1, 2]})


def make_dbc_reader_failing_on(bad_basename):
    def reader(path: Path):
        if Path(path).name == bad_basename:
            raise RuntimeError("decode boom")
        return pl.DataFrame({"UF": ["PR"], "n": [1]})

    return reader


class FakeResult:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


Desc = namedtuple("Desc", "source title mode")


class FakeService:
    def __init__(self, descriptors, schemas=None, runner=None):
        self._descriptors = descriptors
        self._schemas = schemas or {}
        self._runner = runner

    def list_sources(self):
        return list(self._descriptors)

    def get_source_schema(self, source):
        return self._schemas[source]

    def run(self, source, **kwargs):
        return self._runner(source, **kwargs)


# --------------------------------------------------------------------------- #
# model + cadence
# --------------------------------------------------------------------------- #
def test_profile_resolution_across_shapes():
    assert profile_for("sinan", "pysus ftp").kind is Kind.FTP_SINAN
    assert profile_for("sim", "pysus ftp").kind is Kind.FTP_SIM
    assert profile_for("sih", "pysus ftp").kind is Kind.FTP_SIH
    assert profile_for("sia", "datasus ftp").kind is Kind.FTP_GENERIC
    assert profile_for("dengue", "opendatasus api").kind is Kind.API_WINDOW
    nasa = profile_for("nasa_power", "nasa")
    assert nasa.kind is Kind.API_POINT and nasa.auto is False
    assert profile_for("snis", "gov.br crawl").kind is Kind.CRAWLER
    assert profile_for("mystery", "???").kind is Kind.UNKNOWN
    inpe = profile_for("inpe_queimadas", "inpe queimadas api")
    assert inpe.kind is Kind.API_WINDOW
    assert inpe.cadence is Cadence.MONTHLY
    assert inpe.min_year == 2003
    assert inpe.auto is True


def test_cadence_override(monkeypatch):
    monkeypatch.setitem(CADENCE_OVERRIDES, "sih", Cadence.DAILY)
    assert profile_for("sih", "pysus ftp").cadence is Cadence.DAILY


def test_profile_resolution_for_portal_file_sources():
    """Fase A: bulk-file sources ('opendatasus files' mode) resolve like the
    DEMAS/CKAN API sources (Kind.API_WINDOW), but SISAGUA gets a MONTHLY
    override (see CADENCE_OVERRIDES) since SRAG keeps the WEEKLY default.
    """
    srag = profile_for("srag_arquivos", "opendatasus files")
    assert srag.kind is Kind.API_WINDOW
    assert srag.cadence is Cadence.WEEKLY
    assert srag.auto is True

    for name in (
        "sisagua_controle_mensal_parametros_basicos",
        "sisagua_controle_semestral",
        "sisagua_vigilancia_parametros_basicos",
        "sisagua_tratamento_agua",
        "sisagua_populacao_abastecida",
    ):
        profile = profile_for(name, "opendatasus files")
        assert profile.kind is Kind.API_WINDOW
        assert profile.cadence is Cadence.MONTHLY, name


def test_fetchunit_granularity_and_key():
    monthly = FetchUnit("sih", Kind.FTP_SIH, group="RD", state="PR", year=2024, month=1)
    annual = FetchUnit("sinan", Kind.FTP_SINAN, group="DENG", year=2024)
    window = FetchUnit("dengue", Kind.API_WINDOW, year=2023)
    assert monthly.granularity is Granularity.MONTHLY
    assert annual.granularity is Granularity.ANNUAL
    assert window.granularity is Granularity.ANNUAL  # year-only window
    assert monthly.partition_key() == "sih|RD|PR|2024|01||"
    assert monthly.partition_key() != annual.partition_key()


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def test_bronze_paths_native_granularity():
    root = Path("/b")
    sinan = FetchUnit("sinan", Kind.FTP_SINAN, group="DENG", year=2024, src_basename="DENGBR24.dbc")
    sih = FetchUnit("sih", Kind.FTP_SIH, group="RD", state="PR", year=2024, month=1, src_basename="RDPR2401.dbc")
    sia = FetchUnit("sia", Kind.FTP_GENERIC, group="PA", state="SP", year=2024, month=3, src_basename="PASP2403.dbc")
    api = FetchUnit("dengue", Kind.API_WINDOW, year=2023)

    assert paths.bronze_path(root, sinan) == root / "raw/SINAN/DENG/2024/DENGBR24.csv"
    assert paths.bronze_path(root, sih) == root / "raw/SIH/RD/PR/2024/01/RDPR2401.csv"
    assert paths.bronze_path(root, sia) == root / "raw/SIA/PA/SP/2024/03/PASP2403.csv"
    assert paths.bronze_path(root, api) == root / "raw/DENGUE/2023/dengue_2023.csv"


def test_crawler_dir():
    unit = FetchUnit("snis", Kind.CRAWLER)
    assert paths.crawler_dir(Path("/b"), unit) == Path("/b/raw/SNIS")


# --------------------------------------------------------------------------- #
# refined tier
# --------------------------------------------------------------------------- #
def test_month_in_year_is_format_agnostic_with_year_oracle():
    assert refine.month_in_year("2024-07-15", 2024) == 7   # ISO
    assert refine.month_in_year("20240715", 2024) == 7     # YYYYMMDD
    assert refine.month_in_year("15072024", 2024) == 7     # DDMMYYYY
    assert refine.month_in_year("202407", 2024) == 7       # YYYYMM
    assert refine.month_in_year("072024", 2024) == 7       # MMYYYY
    assert refine.month_in_year("2023-07-15", 2024) == 0   # wrong year -> unknown
    assert refine.month_in_year("2024-13-01", 2024) == 0   # invalid month
    assert refine.month_in_year("garbage", 2024) == 0
    assert refine.month_in_year(None, 2024) == 0


def test_write_refined_monthly_passthrough(tmp_path):
    unit = FetchUnit("sih", Kind.FTP_SIH, group="RD", state="PR", year=2024, month=1, src_basename="RDPR2401.dbc")
    written = refine.write_refined(pl.DataFrame({"UF": ["PR"], "n": [1]}), unit, tmp_path)
    assert len(written) == 1
    assert written[0] == tmp_path / "refined/SIH/RD/PR/2024/01/RDPR2401-202401.csv"


def test_write_refined_annual_split_by_event_date(tmp_path):
    unit = FetchUnit("sinan", Kind.FTP_SINAN, group="DENG", year=2024, src_basename="DENGBR24.dbc")
    frame = pl.DataFrame(
        {
            "DT_NOTIFIC": ["2024-01-10", "2024-01-20", "2024-02-05", "bad", "2023-12-01"],
            "x": [1, 2, 3, 4, 5],
        }
    )
    written = refine.write_refined(frame, unit, tmp_path)
    by_month = {p.parent.name: p for p in written}
    assert set(by_month) == {"01", "02", "00"}  # 00 = unknown (bad + wrong-year)
    assert pl.read_csv(by_month["01"]).height == 2
    assert pl.read_csv(by_month["00"]).height == 2


def test_write_refined_year_level_when_no_event_column(tmp_path):
    unit = FetchUnit("sim", Kind.FTP_SIM, group="CID10", state="SP", year=2020, src_basename="DOSP2020.dbc")
    written = refine.write_refined(pl.DataFrame({"SOMECOL": [1, 2]}), unit, tmp_path)
    assert len(written) == 1
    assert written[0].parent == tmp_path / "refined/SIM/CID10/SP/2020"  # no month dir


# --------------------------------------------------------------------------- #
# ledger
# --------------------------------------------------------------------------- #
def _ok_row(unit, size, run_id="r", ts="t"):
    return LedgerRow(
        run_id=run_id,
        ts_utc=ts,
        source=unit.source,
        kind=unit.kind.value,
        granularity=unit.granularity.value,
        status=STATUS_OK,
        partition_key=unit.partition_key(),
        year=unit.year,
        month=unit.month,
        src_size=size,
    )


def test_ledger_roundtrip_and_header_once(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    u = FetchUnit("sih", Kind.FTP_SIH, group="RD", state="PR", year=2024, month=1)
    ledger.append(_ok_row(u, 100))
    ledger.append(_ok_row(u, 200, ts="t2"))
    rows = ledger.read_all()
    assert len(rows) == 2
    # header written exactly once
    assert (tmp_path / "_ledger.csv").read_text(encoding="utf-8").count("partition_key") == 1
    # index keeps the latest row per key
    assert ledger.index()[u.partition_key()].src_size == 200


def test_ledger_satisfied_volumetria(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    u = FetchUnit("sinan", Kind.FTP_SINAN, group="DENG", year=2026, src_size=500)
    assert ledger.satisfied(u) is False  # nothing recorded yet
    ledger.append(_ok_row(u, 500))
    assert ledger.satisfied(u) is True  # same size -> satisfied
    grew = FetchUnit("sinan", Kind.FTP_SINAN, group="DENG", year=2026, src_size=900)
    assert ledger.satisfied(grew) is False  # grown current-year file -> re-pull


def test_ledger_max_year(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    for y in (2021, 2023, 2022):
        u = FetchUnit("dengue", Kind.API_WINDOW, year=y)
        ledger.append(_ok_row(u, 1))
    assert ledger.max_year("dengue") == 2023
    assert ledger.max_year("absent") is None


# --------------------------------------------------------------------------- #
# planner
# --------------------------------------------------------------------------- #
def test_plan_backfill_ftp_sih_units():
    prof = profile_for("sih", "pysus ftp")
    units = plan_backfill(prof, current_year=1993, records_provider=sih_records)
    # min_year 1992 -> years 1992, 1993
    assert [u.year for u in units] == [1992, 1993]
    assert all(u.month == 1 and u.state == "PR" and u.kind is Kind.FTP_SIH for u in units)
    assert units[0].src_basename == "RDPR9201.dbc"


def test_plan_backfill_sinan_no_state_no_month():
    prof = profile_for("sinan", "pysus ftp")
    units = plan_backfill(prof, current_year=2002, records_provider=sinan_records)
    assert units and all(u.state is None and u.month is None for u in units)
    assert units[0].group == "DENG"
    assert units[0].granularity is Granularity.ANNUAL


def test_plan_backfill_api_window_years():
    prof = profile_for("dengue", "opendatasus api")
    units = plan_backfill(prof, current_year=2024, api_backfill_years=3)
    assert [u.year for u in units] == [2022, 2023, 2024]
    assert all(u.kind is Kind.API_WINDOW for u in units)


def test_plan_backfill_crawler_single_unit():
    prof = profile_for("snis", "gov.br crawl")
    units = plan_backfill(prof, current_year=2024)
    assert len(units) == 1 and units[0].kind is Kind.CRAWLER


def test_plan_backfill_skips_non_auto():
    assert plan_backfill(profile_for("nasa_power", "nasa"), current_year=2024) == []
    assert plan_backfill(profile_for("x", "?"), current_year=2024) == []


def test_plan_update_filters_satisfied(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    prof = profile_for("sih", "pysus ftp")
    first = plan_update(prof, ledger, current_year=2024, records_provider=sih_records)
    assert {u.year for u in first} == {2023, 2024}  # lookback 1
    done = first[0]
    ledger.append(_ok_row(done, done.src_size))
    second = plan_update(prof, ledger, current_year=2024, records_provider=sih_records)
    keys = {u.partition_key() for u in second}
    assert done.partition_key() not in keys  # already satisfied -> excluded


def test_plan_update_api_from_max_year(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    ledger.append(_ok_row(FetchUnit("dengue", Kind.API_WINDOW, year=2022), 1))
    prof = profile_for("dengue", "opendatasus api")
    units = plan_update(prof, ledger, current_year=2024)
    assert [u.year for u in units] == [2022, 2023, 2024]  # re-pull last + newer


# --------------------------------------------------------------------------- #
# runner — FTP batch
# --------------------------------------------------------------------------- #
def test_run_ftp_batch_dry_run_writes_nothing(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    unit = FetchUnit("sih", Kind.FTP_SIH, group="RD", state="PR", year=2024, month=1, src_basename="RDPR2401.dbc", src_path="/x/RDPR2401.dbc", src_size=10)
    rows = run_ftp_batch([unit], bronze_root=tmp_path, run_id="r", ts="t", ledger=ledger, dry_run=True)
    assert rows[0].status == STATUS_PLANNED
    assert not paths.bronze_path(tmp_path, unit).exists()


def test_run_ftp_batch_materialises_and_is_idempotent(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    unit = FetchUnit("sinan", Kind.FTP_SINAN, group="DENG", year=2024, src_basename="DENGBR24.dbc", src_path="/s/DENGBR24.dbc", src_size=5)

    rows = run_ftp_batch(
        [unit], bronze_root=tmp_path, run_id="r", ts="t", ledger=ledger,
        client_factory=FakeClient, dbc_reader=good_dbc_reader,
    )
    assert rows[0].status == STATUS_OK
    target = paths.bronze_path(tmp_path, unit)
    assert target.exists() and target.read_text(encoding="utf-8").startswith("UF,n")
    assert rows[0].out_path == str(target)

    # persist and re-run -> skipped (file present + ledger satisfied)
    for r in rows:
        ledger.append(r)
    rows2 = run_ftp_batch(
        [unit], bronze_root=tmp_path, run_id="r2", ts="t2", ledger=ledger,
        client_factory=FakeClient, dbc_reader=good_dbc_reader,
    )
    assert rows2[0].status == STATUS_SKIPPED


def test_run_ftp_batch_records_failure(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    unit = FetchUnit("sinan", Kind.FTP_SINAN, group="BAD", year=2024, src_basename="BADBR24.dbc", src_path="/s/BADBR24.dbc", src_size=5)
    rows = run_ftp_batch(
        [unit], bronze_root=tmp_path, run_id="r", ts="t", ledger=ledger,
        client_factory=FakeClient, dbc_reader=make_dbc_reader_failing_on("BADBR24.dbc"),
    )
    assert rows[0].status == "error"
    assert not paths.bronze_path(tmp_path, unit).exists()


# --------------------------------------------------------------------------- #
# runner — service path
# --------------------------------------------------------------------------- #
def _dengue_service(write_csv=True):
    schema = {"params": [{"name": n} for n in ("start_year", "end_year", "output_dir", "output_format")]}

    def runner(source, **kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        exported = []
        if write_csv:
            csv = out / "dengue_raw.csv"
            csv.write_text("a,b\n1,2\n", encoding="utf-8")
            exported = [str(csv)]
        return FakeResult({"documents_found": 1, "downloaded_count": 1, "exported_files": exported})

    return FakeService([Desc("dengue", "Dengue", "opendatasus api")], {"dengue": schema}, runner)


def test_run_via_service_moves_csv_to_bronze(tmp_path):
    service = _dengue_service(write_csv=True)
    unit = FetchUnit("dengue", Kind.API_WINDOW, year=2023)
    row = run_via_service(unit, service=service, bronze_root=tmp_path, run_id="r", ts="t")
    assert row.status == STATUS_OK
    target = paths.bronze_path(tmp_path, unit)
    assert Path(row.out_path) == target and target.exists()
    assert target.name == "dengue_2023.csv"


def test_run_via_service_empty_when_no_export(tmp_path):
    service = _dengue_service(write_csv=False)
    unit = FetchUnit("dengue", Kind.API_WINDOW, year=2023)
    row = run_via_service(unit, service=service, bronze_root=tmp_path, run_id="r", ts="t")
    assert row.status == STATUS_EMPTY


# --------------------------------------------------------------------------- #
# orchestrator — full sweep, offline
# --------------------------------------------------------------------------- #
def _mixed_service():
    schema = {"params": [{"name": n} for n in ("start_year", "end_year", "output_dir", "output_format")]}

    def runner(source, **kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        csv = out / "raw.csv"
        csv.write_text("a\n1\n", encoding="utf-8")
        return FakeResult({"documents_found": 1, "downloaded_count": 1, "exported_files": [str(csv)]})

    descriptors = [
        Desc("sinan", "SINAN", "pysus ftp"),
        Desc("dengue", "Dengue", "opendatasus api"),
        Desc("nasa_power", "NASA POWER", "nasa"),
    ]
    return FakeService(descriptors, {"dengue": schema}, runner)


def test_orchestrator_backfill_writes_ledger_and_skips_nasa(tmp_path):
    orch = Orchestrator(
        bronze_root=tmp_path,
        service=_mixed_service(),
        records_provider=sinan_records,
        clock=lambda: "2026-07-13T00:00:00+00:00",
        ftp_client_factory=FakeClient,
        dbc_reader=good_dbc_reader,
    )
    report = orch.backfill(current_year=2002)  # sinan min 2001 -> 2001, 2002

    assert report.by_source["sinan"]["ok"] == 2
    # dengue is API-window: bounded 5-year backfill floor -> 1998..2002
    assert report.by_source["dengue"]["ok"] == 5
    assert any(s["source"] == "nasa_power" for s in report.skipped_sources)

    # ledger persisted with the ok rows (2 SINAN + 5 dengue)
    rows = Ledger(tmp_path / "_ledger.csv").read_all()
    assert sum(1 for r in rows if r.status == STATUS_OK) == 7
    # bronze tree materialised (raw tier)
    assert (tmp_path / "raw" / "SINAN" / "DENG" / "2001" / "DENGBR01.csv").exists()


def test_orchestrator_dry_run_leaves_no_ledger(tmp_path):
    orch = Orchestrator(
        bronze_root=tmp_path,
        service=_mixed_service(),
        records_provider=sinan_records,
        ftp_client_factory=FakeClient,
        dbc_reader=good_dbc_reader,
    )
    report = orch.backfill(current_year=2002, dry_run=True)
    assert report.totals[STATUS_PLANNED] >= 2
    assert not (tmp_path / "_ledger.csv").exists()


def test_plan_update_requests_fetch_sizes(tmp_path):
    """Volumetria: plan_update must ask the provider for real file sizes."""
    seen = {}

    def provider(kind, source, years, *, fetch_sizes=False):
        seen["fetch_sizes"] = fetch_sizes
        return []

    ledger = Ledger(tmp_path / "_ledger.csv")
    prof = profile_for("sih", "pysus ftp")
    plan_update(prof, ledger, current_year=2024, records_provider=provider)
    assert seen["fetch_sizes"] is True


def test_plan_update_accepts_legacy_provider_signature(tmp_path):
    """Providers with the historical 3-arg signature keep working."""
    ledger = Ledger(tmp_path / "_ledger.csv")
    prof = profile_for("sih", "pysus ftp")
    units = plan_update(
        prof, ledger, current_year=2024, records_provider=sih_records
    )
    assert units  # discovery ran without TypeError
