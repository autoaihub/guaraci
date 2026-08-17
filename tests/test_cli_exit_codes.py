"""Tests for CLI exit codes, --json output and verbose propagation.

Covers the fixes from the CLI audit: export-loop failures must exit 1,
orchestrate backfill/update must exit 1 on source errors, --config-file was
removed, `filter` no longer shadows the builtin, and the root -v propagates
to the subgroups through ctx.obj.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from guaraci.cli._common import resolve_verbose
from guaraci.cli.main import app
from guaraci.cli.sih_cli import sih
from guaraci.cli.sim_cli import sim
from guaraci.cli.sinan_cli import sinan


class _FakeHealthDs:
    """Minimal stand-in for Sih/Sim/SinanDataSource in download tests."""

    DEFAULT_GROUPS = ["RD"]
    NEGLECTED_DISEASES = ["DENG"]

    def __init__(self, *, fail_group: bool = False, **kwargs) -> None:
        self._fail_group = fail_group

    def download(self, *args, **kwargs):
        return {
            "total_files": 2,
            "successful_downloads": 2,
            "failed_downloads": [],
        }

    def load_dataframe(self, group):
        if self._fail_group:
            raise RuntimeError(f"corrupted file for {group}")
        return [1, 2, 3]

    def filter(self, df, **kwargs):
        return df

    def export(self, df, format, name):
        return Path(f"{name}.{format}")


@pytest.mark.parametrize(
    ("cli", "module_path", "class_name"),
    [
        (sih, "guaraci.cli.sih_cli", "SihDataSource"),
        (sim, "guaraci.cli.sim_cli", "SimDataSource"),
        (sinan, "guaraci.cli.sinan_cli", "SinanDataSource"),
    ],
)
def test_download_export_failure_exits_nonzero(monkeypatch, cli, module_path, class_name):
    monkeypatch.setattr(
        f"{module_path}.{class_name}",
        lambda **kwargs: _FakeHealthDs(fail_group=True),
    )
    result = CliRunner().invoke(cli, ["download", "2020", "2020"])
    assert result.exit_code == 1, result.output
    assert "failed during processing" in result.output


@pytest.mark.parametrize(
    ("cli", "module_path", "class_name", "source_name"),
    [
        (sih, "guaraci.cli.sih_cli", "SihDataSource", "sih"),
        (sim, "guaraci.cli.sim_cli", "SimDataSource", "sim"),
        (sinan, "guaraci.cli.sinan_cli", "SinanDataSource", "sinan"),
    ],
)
def test_download_success_exits_zero_and_json_flag(
    monkeypatch, cli, module_path, class_name, source_name
):
    monkeypatch.setattr(
        f"{module_path}.{class_name}", lambda **kwargs: _FakeHealthDs()
    )
    result = CliRunner().invoke(cli, ["download", "2020", "2020", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == source_name
    assert payload["downloaded_count"] == 2
    assert payload["exported_files"]
    assert payload["failed_groups"] == []


def test_download_json_failure_still_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        "guaraci.cli.sih_cli.SihDataSource",
        lambda **kwargs: _FakeHealthDs(fail_group=True),
    )
    result = CliRunner().invoke(sih, ["download", "2020", "2020", "--json"])
    assert result.exit_code == 1
    # stdout still starts with the JSON payload
    payload = json.loads(result.output[: result.output.rindex("}") + 1])
    assert payload["failed_groups"] == ["RD"]


@pytest.mark.parametrize("cli", [sih, sim, sinan])
def test_config_file_flag_removed(cli):
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--config-file" not in result.output


@pytest.mark.parametrize(
    ("cli", "module_name"),
    [
        (sih, "guaraci.cli.sih_cli"),
        (sim, "guaraci.cli.sim_cli"),
        (sinan, "guaraci.cli.sinan_cli"),
    ],
)
def test_filter_command_kept_but_builtin_not_shadowed(cli, module_name):
    import importlib

    module = importlib.import_module(module_name)
    assert "filter" in cli.commands  # CLI command name preserved
    assert not hasattr(module, "filter")  # module no longer shadows builtin
    assert hasattr(module, "filter_cmd")


def test_resolve_verbose_inherits_from_parent_context():
    parent = click.Context(click.Group("root"), obj={"verbose": True})
    child = click.Context(click.Group("sub"), parent=parent)
    assert resolve_verbose(child, False) is True
    assert child.obj["verbose"] is True


def test_resolve_verbose_local_flag_wins_without_parent():
    ctx = click.Context(click.Group("sub"))
    assert resolve_verbose(ctx, True) is True
    assert resolve_verbose(click.Context(click.Group("sub2")), False) is False


def test_root_verbose_sets_ctx_obj():
    result = CliRunner().invoke(app, ["--verbose", "info"])
    assert result.exit_code == 0
    assert "Verbose mode enabled" in result.output


def test_info_does_not_announce_api_subcommand():
    result = CliRunner().invoke(app, ["info"])
    assert result.exit_code == 0
    assert "uvicorn guaraci.api.main:app" in result.output
    # The API must not be listed as if it were a `guaraci api` subcommand.
    assert "• api" not in result.output.replace("[cyan]", "")


def _fake_report(*, source_errors=None, error_units=0):
    from guaraci.orchestrator.orchestrator import RunReport

    report = RunReport(run_id="r1", mode="backfill")
    report.totals = Counter({"ok": 1, "error": error_units})
    report.by_source = {"sih": Counter({"ok": 1, "error": error_units})}
    report.source_errors = source_errors or []
    return report


@pytest.mark.parametrize("command", ["backfill", "update"])
def test_orchestrate_exits_nonzero_on_source_errors(monkeypatch, command, tmp_path):
    from guaraci.cli import orchestrate_cli

    report = _fake_report(source_errors=[{"source": "sih", "error": "boom"}])

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def backfill(self, *args, **kwargs):
            return report

        def update(self, *args, **kwargs):
            return report

    monkeypatch.setattr(orchestrate_cli, "Orchestrator", FakeOrchestrator)
    result = CliRunner().invoke(
        orchestrate_cli.orchestrate, [command, "-o", str(tmp_path)]
    )
    assert result.exit_code == 1, result.output


@pytest.mark.parametrize("command", ["backfill", "update"])
def test_orchestrate_exits_nonzero_on_error_units(monkeypatch, command, tmp_path):
    from guaraci.cli import orchestrate_cli

    report = _fake_report(error_units=3)

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def backfill(self, *args, **kwargs):
            return report

        def update(self, *args, **kwargs):
            return report

    monkeypatch.setattr(orchestrate_cli, "Orchestrator", FakeOrchestrator)
    result = CliRunner().invoke(
        orchestrate_cli.orchestrate, [command, "-o", str(tmp_path)]
    )
    assert result.exit_code == 1, result.output


@pytest.mark.parametrize("command", ["backfill", "update"])
def test_orchestrate_exits_zero_when_clean(monkeypatch, command, tmp_path):
    from guaraci.cli import orchestrate_cli

    report = _fake_report()

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def backfill(self, *args, **kwargs):
            return report

        def update(self, *args, **kwargs):
            return report

    monkeypatch.setattr(orchestrate_cli, "Orchestrator", FakeOrchestrator)
    result = CliRunner().invoke(
        orchestrate_cli.orchestrate, [command, "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
