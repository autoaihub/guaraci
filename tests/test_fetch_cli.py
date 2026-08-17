"""Tests for the generic schema-driven `guaraci fetch` CLI.

All tests are offline/deterministic: they exercise coercion, listing, schema
introspection, and error handling without performing any network fetch.
"""
import click
import pytest
from click.testing import CliRunner

from guaraci.cli.fetch_cli import _coerce, _parse_sets, fetch


def test_coerce_integer():
    assert _coerce("2020", "integer") == 2020
    assert _coerce("  2019 ", "integer") == 2019


def test_coerce_boolean():
    assert _coerce("true", "boolean") is True
    assert _coerce("No", "boolean") is False
    assert _coerce("1", "boolean") is True
    assert _coerce("off", "boolean") is False


def test_coerce_string_list():
    assert _coerce("A, B ,C", "string_list") == ["A", "B", "C"]
    assert _coerce("SP", "string_list") == ["SP"]
    assert _coerce("", "string_list") == []


def test_coerce_string_passthrough():
    assert _coerce("  SP ", "string") == "SP"


def test_coerce_bad_integer_raises():
    with pytest.raises(click.BadParameter):
        _coerce("abc", "integer")


def test_coerce_bad_boolean_raises():
    with pytest.raises(click.BadParameter):
        _coerce("maybe", "boolean")


def test_parse_sets_unknown_param():
    schema = {"start_year": {"type": "integer"}}
    with pytest.raises(click.BadParameter):
        _parse_sets(("bogus=1",), schema)


def test_parse_sets_missing_equals():
    with pytest.raises(click.BadParameter):
        _parse_sets(("start_year",), {"start_year": {"type": "integer"}})


def test_fetch_list_runs():
    result = CliRunner().invoke(fetch, ["list"])
    assert result.exit_code == 0
    assert "nasa_power" in result.output


def test_fetch_schema_nasa_power():
    result = CliRunner().invoke(fetch, ["schema", "nasa_power"])
    assert result.exit_code == 0
    assert "latitude" in result.output
    assert "longitude" in result.output


def test_fetch_schema_unknown_source():
    result = CliRunner().invoke(fetch, ["schema", "does_not_exist"])
    assert result.exit_code != 0


def test_fetch_run_bad_set_syntax():
    result = CliRunner().invoke(fetch, ["run", "nasa_power", "--set", "latitude"])
    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output


def test_fetch_run_unknown_param():
    result = CliRunner().invoke(fetch, ["run", "nasa_power", "--set", "bogus=1"])
    assert result.exit_code != 0
    assert "unknown parameter" in result.output.lower()


def test_fetch_run_surfaces_validation_error(monkeypatch):
    """A validation ValueError surfaces as a clean usage error (no network)."""
    from guaraci.services import downloads as downloads_module

    def _raise(self, source, params):
        raise ValueError("Missing required parameter: start_year")

    monkeypatch.setattr(
        downloads_module.DownloadService, "validate_source_params", _raise
    )
    result = CliRunner().invoke(
        fetch, ["run", "nasa_power", "--set", "latitude=-23.55"]
    )
    assert result.exit_code != 0
    assert "start_year" in result.output


def test_fetch_run_no_format_does_not_force_export(monkeypatch):
    """Without --format, output_format must NOT be injected (download-only)."""
    from guaraci.services import downloads as downloads_module

    captured: dict = {}
    monkeypatch.setattr(
        downloads_module.DownloadService,
        "validate_source_params",
        lambda self, source, params: None,
    )

    def _run(self, source, **kwargs):
        captured.update(kwargs)
        return {"exported_files": []}

    monkeypatch.setattr(downloads_module.DownloadService, "run", _run)
    result = CliRunner().invoke(
        fetch, ["run", "nasa_power", "--set", "latitude=-23.55"]
    )
    assert result.exit_code == 0
    assert "output_format" not in captured


def test_fetch_run_explicit_format_is_injected(monkeypatch):
    """With --format, output_format is injected for sources that declare it."""
    from guaraci.services import downloads as downloads_module

    captured: dict = {}
    monkeypatch.setattr(
        downloads_module.DownloadService,
        "validate_source_params",
        lambda self, source, params: None,
    )

    def _run(self, source, **kwargs):
        captured.update(kwargs)
        return {"exported_files": ["/tmp/x.parquet"]}

    monkeypatch.setattr(downloads_module.DownloadService, "run", _run)
    result = CliRunner().invoke(
        fetch,
        ["run", "nasa_power", "--set", "latitude=-23.55", "--format", "parquet"],
    )
    assert result.exit_code == 0
    assert captured.get("output_format") == "parquet"


def test_fetch_run_payload_dump_only_with_verbose(monkeypatch):
    """The raw payload dict is only printed under --verbose."""
    from guaraci.services import downloads as downloads_module

    monkeypatch.setattr(
        downloads_module.DownloadService,
        "validate_source_params",
        lambda self, source, params: None,
    )

    def _run(self, source, **kwargs):
        return {"exported_files": [], "secret_marker_key": "xyz"}

    monkeypatch.setattr(downloads_module.DownloadService, "run", _run)

    quiet = CliRunner().invoke(fetch, ["run", "nasa_power", "--set", "latitude=-23.55"])
    assert quiet.exit_code == 0
    assert "secret_marker_key" not in quiet.output

    verbose = CliRunner().invoke(
        fetch, ["run", "nasa_power", "--set", "latitude=-23.55", "--verbose"]
    )
    assert verbose.exit_code == 0
    assert "secret_marker_key" in verbose.output


def test_fetch_run_json_flag(monkeypatch):
    import json

    from guaraci.services import downloads as downloads_module

    monkeypatch.setattr(
        downloads_module.DownloadService,
        "validate_source_params",
        lambda self, source, params: None,
    )

    def _run(self, source, **kwargs):
        return {"exported_files": ["/tmp/x.parquet"], "documents_found": 1}

    monkeypatch.setattr(downloads_module.DownloadService, "run", _run)

    result = CliRunner().invoke(
        fetch, ["run", "nasa_power", "--set", "latitude=-23.55", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["exported_files"] == ["/tmp/x.parquet"]
    assert payload["documents_found"] == 1


def test_human_bytes():
    from guaraci.cli.fetch_cli import _human_bytes

    assert _human_bytes(512) == "512 B"
    assert _human_bytes(1024) == "1.0 KB"
    assert _human_bytes(1_572_864) == "1.5 MB"
    assert _human_bytes(None) == "None"


def test_fetch_discover_count_and_size(monkeypatch):
    from guaraci.services import downloads as downloads_module

    captured: dict = {}
    monkeypatch.setattr(
        downloads_module.DownloadService,
        "get_source_schema",
        lambda self, source: {
            "source": source,
            "title": source,
            "mode": "datasus ftp",
            "params": [
                {"name": "start_year", "type": "integer"},
                {"name": "end_year", "type": "integer"},
                {"name": "groups", "type": "string_list"},
            ],
        },
    )

    def _discover(self, source, *, fetch_sizes=False, **kwargs):
        captured["fetch_sizes"] = fetch_sizes
        captured.update(kwargs)
        return {"documents_found": 12, "total_size_bytes": 1_572_864, "by_group": {"PA": 12}}

    monkeypatch.setattr(downloads_module.DownloadService, "discover", _discover)
    result = CliRunner().invoke(
        fetch,
        ["discover", "sia", "--set", "start_year=2024", "--set", "end_year=2024", "--sizes"],
    )
    assert result.exit_code == 0
    assert "12" in result.output
    assert "1.5 MB" in result.output
    assert captured["fetch_sizes"] is True
    assert captured.get("start_year") == 2024


def test_fetch_discover_unsupported_source(monkeypatch):
    from guaraci.services import downloads as downloads_module

    monkeypatch.setattr(
        downloads_module.DownloadService,
        "get_source_schema",
        lambda self, source: {"source": source, "title": source, "mode": "nasa", "params": []},
    )

    def _discover(self, source, *, fetch_sizes=False, **kwargs):
        raise ValueError(f"Discovery is not supported for source '{source}'.")

    monkeypatch.setattr(downloads_module.DownloadService, "discover", _discover)
    result = CliRunner().invoke(fetch, ["discover", "nasa_power"])
    assert result.exit_code != 0
    assert "not supported" in result.output.lower()


def test_fetch_fields_known_source():
    result = CliRunner().invoke(fetch, ["fields", "sih"])
    assert result.exit_code == 0
    assert "DT_INTER" in result.output  # SIH always carries the admission-date field


def test_fetch_fields_unknown_source():
    result = CliRunner().invoke(fetch, ["fields", "does_not_exist_xyz"])
    assert result.exit_code != 0
