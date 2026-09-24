"""Varredura bronze das três fontes CETESB, sem rede.

Dois formatos que o orquestrador não tinha antes:

- ``SNAPSHOT``: o índice aberto é uma janela móvel de 48h sem histórico. O
  que não for guardado no dia se perde, então cada execução grava uma cópia
  datada, e a data da coleta é a identidade da partição.
- ``API_MONTHLY``: o QUALAR autenticado tem série histórica, varrida mês a
  mês num recorte fixo de estações, porque cada par estação/parâmetro é uma
  requisição.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from guaraci.cetesb.horario import SWEEP_PARAMETERS, SWEEP_STATIONS
from guaraci.orchestrator import paths
from guaraci.orchestrator.cadence import SourceProfile, profile_for, sweep_params
from guaraci.orchestrator.ledger import STATUS_OK, Ledger, LedgerRow
from guaraci.orchestrator.model import Cadence, FetchUnit, Granularity, Kind
from guaraci.orchestrator.planner import plan_backfill, plan_update
from guaraci.orchestrator.runner import run_via_service

TODAY = date(2026, 9, 24)
_HORARIO = SourceProfile("cetesb_qualar_horario", Kind.API_MONTHLY, Cadence.MONTHLY, 2022)


def _ok(unit: FetchUnit) -> LedgerRow:
    return LedgerRow(
        run_id="r", ts_utc="t", source=unit.source, kind=unit.kind.value,
        granularity=unit.granularity.value, status=STATUS_OK,
        partition_key=unit.partition_key(), year=unit.year, month=unit.month,
    )


# --- perfis -----------------------------------------------------------------


def test_open_cetesb_sources_are_swept_as_snapshots():
    qualar = profile_for("cetesb_qualar", "cetesb arcgis")
    estacoes = profile_for("cetesb_estacoes", "cetesb arcgis")
    assert qualar.kind is Kind.SNAPSHOT and qualar.cadence is Cadence.DAILY and qualar.auto
    assert estacoes.kind is Kind.SNAPSHOT and estacoes.cadence is Cadence.MONTHLY


def test_authenticated_qualar_is_skipped_without_credential(monkeypatch):
    monkeypatch.delenv("GUARACI_QUALAR_LOGIN", raising=False)
    monkeypatch.delenv("GUARACI_QUALAR_SENHA", raising=False)
    profile = profile_for("cetesb_qualar_horario")
    assert profile.kind is Kind.API_MONTHLY
    assert profile.auto is False
    assert "GUARACI_QUALAR_LOGIN" in profile.note


def test_authenticated_qualar_is_swept_with_credential(monkeypatch):
    monkeypatch.setenv("GUARACI_QUALAR_LOGIN", "user")
    monkeypatch.setenv("GUARACI_QUALAR_SENHA", "pass")
    profile = profile_for("cetesb_qualar_horario")
    assert profile.auto is True and profile.min_year == 2022


def test_sweep_recorte_is_greater_sao_paulo_with_meteorology():
    params = sweep_params("cetesb_qualar_horario")
    assert len(SWEEP_STATIONS) == 30
    assert "Pinheiros" in params["stations"]
    assert {"TEMP", "UR", "MP2.5"} <= set(params["parameters"])
    assert params["parameters"] == list(SWEEP_PARAMETERS)
    assert params["only_validated"] is False  # bronze guarda o dado como publicado
    assert sweep_params("dengue") == {}


# --- instantâneo ------------------------------------------------------------


def test_daily_snapshot_is_keyed_by_collection_date():
    unit = plan_backfill(profile_for("cetesb_qualar", "cetesb arcgis"), today=TODAY)[0]
    assert unit.granularity is Granularity.SNAPSHOT
    assert unit.start_date == unit.end_date == "2026-09-24"
    target = paths.bronze_path(Path("B"), unit).as_posix()
    assert target == "B/raw/CETESB_QUALAR/2026/09/cetesb_qualar_20260924.csv"


def test_two_days_never_share_a_file():
    profile = profile_for("cetesb_qualar", "cetesb arcgis")
    first = plan_backfill(profile, today=date(2026, 9, 24))[0]
    second = plan_backfill(profile, today=date(2026, 9, 25))[0]
    assert first.partition_key() != second.partition_key()
    assert paths.bronze_path(Path("B"), first) != paths.bronze_path(Path("B"), second)


def test_monthly_snapshot_one_file_per_month():
    unit = plan_backfill(profile_for("cetesb_estacoes", "cetesb arcgis"), today=TODAY)[0]
    assert paths.bronze_path(Path("B"), unit).name == "cetesb_estacoes_202609.csv"


def test_snapshot_update_is_idempotent_within_its_period(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    profile = profile_for("cetesb_qualar", "cetesb arcgis")
    [unit] = plan_update(profile, ledger, today=TODAY)
    ledger.append(_ok(unit))
    assert plan_update(profile, ledger, today=TODAY) == []
    assert len(plan_update(profile, ledger, today=date(2026, 9, 25))) == 1


# --- série mensal -----------------------------------------------------------


def test_monthly_backfill_covers_floor_to_current_month():
    units = plan_backfill(_HORARIO, today=TODAY)
    assert len(units) == 4 * 12 + 9  # 2022-01 .. 2026-09
    assert (units[0].start_date, units[0].end_date) == ("2022-01-01", "2022-01-31")
    assert units[-1].end_date == "2026-09-24"  # mês corrente só até hoje
    assert units[1].end_date == "2022-02-28"


def test_monthly_update_revalidates_recent_months(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    units = plan_update(_HORARIO, ledger, today=TODAY)
    assert [(u.year, u.month) for u in units] == [(2026, 7), (2026, 8), (2026, 9)]


def test_monthly_update_fills_the_gap_since_the_last_ok_month(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    old = [u for u in plan_backfill(_HORARIO, today=TODAY) if (u.year, u.month) == (2026, 3)][0]
    ledger.append(_ok(old))
    units = plan_update(_HORARIO, ledger, today=TODAY)
    assert [(u.year, u.month) for u in units] == [
        (2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8), (2026, 9)
    ]


def test_monthly_update_crosses_the_year_boundary(tmp_path):
    ledger = Ledger(tmp_path / "_ledger.csv")
    units = plan_update(_HORARIO, ledger, today=date(2027, 1, 10))
    assert [(u.year, u.month) for u in units] == [(2026, 11), (2026, 12), (2027, 1)]


# --- executor ---------------------------------------------------------------


class _Result:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _Service:
    def __init__(self, params):
        self._params = params
        self.calls = []

    def get_source_schema(self, source):
        return {"params": [{"name": name} for name in self._params]}

    def run(self, source, **kwargs):
        self.calls.append(kwargs)
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        csv = out / "x.csv"
        csv.write_text("a\n1\n", encoding="utf-8")
        return _Result({"documents_found": 1, "downloaded_count": 1, "exported_files": [str(csv)]})


def test_runner_passes_month_dates_and_the_fixed_recorte(tmp_path):
    service = _Service(
        ["stations", "parameters", "start_date", "end_date", "only_validated",
         "output_dir", "output_format"]
    )
    unit = plan_backfill(_HORARIO, today=TODAY)[-2]  # 2026-08
    row = run_via_service(unit, service=service, bronze_root=tmp_path, run_id="r", ts="t")
    assert row.status == STATUS_OK
    kwargs = service.calls[0]
    assert (kwargs["start_date"], kwargs["end_date"]) == ("2026-08-01", "2026-08-31")
    assert kwargs["stations"] == list(SWEEP_STATIONS)
    assert kwargs["only_validated"] is False
    assert Path(row.out_path).name == "cetesb_qualar_horario_202608.csv"


def test_runner_drops_recorte_keys_the_schema_does_not_know(tmp_path):
    service = _Service(["start_date", "end_date", "output_dir", "output_format"])
    unit = plan_backfill(_HORARIO, today=TODAY)[-1]
    run_via_service(unit, service=service, bronze_root=tmp_path, run_id="r", ts="t")
    assert "stations" not in service.calls[0]


def test_runner_passes_no_dates_to_a_snapshot(tmp_path):
    service = _Service(["output_dir", "output_format", "start_date"])
    unit = plan_backfill(profile_for("cetesb_qualar", "cetesb arcgis"), today=TODAY)[0]
    row = run_via_service(unit, service=service, bronze_root=tmp_path, run_id="r", ts="t")
    assert row.status == STATUS_OK
    assert "start_date" not in service.calls[0]
    assert Path(row.out_path).name == "cetesb_qualar_20260924.csv"
