"""Recursos zipados e fontes cumulativas do portal de dados abertos do MS.

Antes desta correção, as 14 fontes SISAGUA nunca chegavam ao bronze: o
recurso é um ``.zip``, a conversão abortava, e o orquestrador registrava
``empty`` a cada execução (verificado ao vivo em 2026-09-24). As dez
cumulativas ainda eram pedidas uma vez por ano, baixando o mesmo arquivo.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

from guaraci.opendatasus.portal_files import PortalFileDataSource, _extract_csv_members
from guaraci.orchestrator import paths
from guaraci.orchestrator.cadence import profile_for
from guaraci.orchestrator.model import Cadence, FetchUnit, Kind
from guaraci.orchestrator.runner import run_via_service
from guaraci.services.downloads import DownloadService
from guaraci.services.sources.opendatasus_files import CUMULATIVE_SOURCES


def _zip(path: Path, members: dict) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, text in members.items():
            bundle.writestr(name, text)
    return path


# --- extração ---------------------------------------------------------------


def test_only_csv_members_are_extracted_and_zip_slip_is_blocked(tmp_path):
    archive = _zip(
        tmp_path / "a.csv.zip",
        {"pasta/x.csv": "a;b\n1;2\n", "leia.pdf": "%PDF", "../../fora.csv": "a\n1\n"},
    )
    extracted = _extract_csv_members(archive)
    assert sorted(p.name for p in extracted) == ["fora.csv", "x.csv"]
    assert all(p.parent == tmp_path for p in extracted)
    assert not (tmp_path.parent.parent / "fora.csv").exists()


def test_zipped_csv_converts_to_parquet_and_cleans_up(tmp_path):
    archive = _zip(tmp_path / "t.csv.zip", {"t.csv": "uf;casos\nPA;3\nAM;5\n"})
    source = PortalFileDataSource(output_path=str(tmp_path))
    [exported] = source._convert_resource(archive, "parquet")
    assert pl.read_parquet(exported)["casos"].to_list() == ["3", "5"]  # texto: nada se perde
    assert not (tmp_path / "t.csv").exists()  # CSV intermediário removido


def test_zipped_csv_to_csv_is_the_extracted_file(tmp_path):
    archive = _zip(tmp_path / "t.csv.zip", {"t.csv": "uf;casos\nPA;3\n"})
    source = PortalFileDataSource(output_path=str(tmp_path))
    assert source._convert_resource(archive, "csv") == [tmp_path / "t.csv"]


def test_zip_with_several_banks_yields_one_export_each(tmp_path):
    archive = _zip(tmp_path / "e.csv.zip", {f"banco_{i}.csv": "a;b\n1;2\n" for i in range(3)})
    source = PortalFileDataSource(output_path=str(tmp_path))
    assert len(source._convert_resource(archive, "parquet")) == 3


def test_zip_without_csv_is_still_an_explicit_error(tmp_path):
    archive = _zip(tmp_path / "j.json.zip", {"j.json": "[]"})
    source = PortalFileDataSource(output_path=str(tmp_path))
    try:
        source._convert_resource(archive, "parquet")
    except ValueError as exc:
        assert "no CSV inside" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


# --- cumulativas ------------------------------------------------------------


def test_cumulative_set_matches_the_schema_flag():
    service = DownloadService()
    flagged = set()
    for descriptor in service.list_sources():
        if descriptor.mode != "opendatasus files":
            continue
        params = service.get_source_schema(descriptor.source)["params"]
        start = next(p for p in params if p["name"] == "start_year")
        if "cumulativo" in (start.get("description") or ""):
            flagged.add(descriptor.source)
    assert flagged == set(CUMULATIVE_SOURCES)


def test_cumulative_sources_are_monthly_snapshots():
    for source in CUMULATIVE_SOURCES:
        profile = profile_for(source, "opendatasus files")
        assert profile.kind is Kind.SNAPSHOT and profile.cadence is Cadence.MONTHLY


def test_year_segmented_sisagua_stays_a_year_window():
    assert profile_for("sisagua_controle_semestral", "opendatasus files").kind is Kind.API_WINDOW


def test_new_portal_sources_have_the_expected_profiles():
    enani = profile_for("enani_2019", "opendatasus files")
    assert (enani.min_year, enani.max_year) == (2019, 2019)
    assert profile_for("sesai_tuberculose", "opendatasus files").kind is Kind.API_WINDOW


# --- orquestrador -----------------------------------------------------------


class _Result:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _MultiCsvService:
    def get_source_schema(self, source):
        return {"params": [{"name": n} for n in ("start_year", "end_year", "output_dir", "output_format")]}

    def run(self, source, **kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        files = []
        for name in ("data_crianca", "data_bioq_1a"):
            path = out / f"{name}.csv"
            path.write_text("a\n1\n", encoding="utf-8")
            files.append(str(path))
        return _Result({"documents_found": 1, "downloaded_count": 1, "exported_files": files})


def test_every_csv_of_a_multi_bank_resource_reaches_bronze(tmp_path):
    unit = FetchUnit("enani_2019", Kind.API_WINDOW, year=2019)
    row = run_via_service(unit, service=_MultiCsvService(), bronze_root=tmp_path, run_id="r", ts="t")
    folder = paths.bronze_path(tmp_path, unit).parent
    assert sorted(p.name for p in folder.glob("*.csv")) == [
        "enani_2019_2019_data_bioq_1a.csv",
        "enani_2019_2019_data_crianca.csv",
    ]
    assert Path(row.out_path).name == "enani_2019_2019_data_crianca.csv"
    assert row.n_bytes == sum(p.stat().st_size for p in folder.glob("*.csv"))


class _RejectsService(_MultiCsvService):
    def run(self, source, **kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        data = out / "a.csv"
        data.write_text("a\n1\n", encoding="utf-8")
        rejects = out / "a.rejeitadas.csv"
        rejects.write_text("linha;conteudo_original\n3;x;y\n", encoding="utf-8")
        return _Result({
            "documents_found": 1, "downloaded_count": 1,
            "exported_files": [str(data)], "rejected_file": str(rejects),
        })


def test_rejected_rows_file_travels_with_the_bronze_file(tmp_path):
    unit = FetchUnit("anvisa_tecnovigilancia", Kind.SNAPSHOT, year=2026, month=9)
    row = run_via_service(unit, service=_RejectsService(), bronze_root=tmp_path, run_id="r", ts="t")
    target = Path(row.out_path)
    assert target.name == "anvisa_tecnovigilancia_202609.csv"
    assert (target.parent / "anvisa_tecnovigilancia_202609.rejeitadas.csv").exists()


# --- fidelidade dos valores -------------------------------------------------


def test_conversion_keeps_every_value_and_leading_zeros(tmp_path):
    linhas = ["cnes;cod"] + [f"{i:07d};{i}" for i in range(15000)] + ["0012345;10A"]
    (tmp_path / "t.csv").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    source = PortalFileDataSource(output_path=str(tmp_path))
    for formato in ("parquet", "sqlite"):
        exported = source._convert_to_format(tmp_path / "t.csv", formato)
        if formato == "parquet":
            frame = pl.read_parquet(exported)
        else:
            import sqlite3

            with sqlite3.connect(exported) as conn:
                frame = pl.DataFrame(conn.execute("SELECT cnes, cod FROM records").fetchall(),
                                     schema=["cnes", "cod"], orient="row")
        assert frame["cod"].null_count() == 0, formato
        assert frame["cod"][-1] == "10A" and frame["cnes"][-1] == "0012345", formato


def test_csv_export_is_utf8_with_commas(tmp_path):
    raw = tmp_path / "INFLUD16.csv"
    raw.write_bytes("NOME;UF\nJOSÉ;SP\n".encode("latin-1"))
    source = PortalFileDataSource(output_path=str(tmp_path))
    [exported] = source._convert_resource(raw, "csv", keep_raw=True)
    assert exported.read_text(encoding="utf-8") == "NOME,UF\nJOSÉ,SP\n"
    assert (tmp_path / "INFLUD16.original.csv").read_bytes().decode("latin-1").startswith("NOME;UF")


def test_headerless_csv_gets_the_declared_header_and_keeps_the_first_row(tmp_path):
    from guaraci.opendatasus.portal_files import _prepend_header

    csv_path = tmp_path / "p.csv"
    csv_path.write_bytes('"SUL";"RS";"4ª CRS"\r\n"NORDESTE";"BA";"19 DIRES"\r\n'.encode("latin-1"))
    _prepend_header(csv_path, ("NO_REGIAO", "SG_UF", "NO_REGIONAL"))
    _prepend_header(csv_path, ("NO_REGIAO", "SG_UF", "NO_REGIONAL"))  # idempotente
    frame = pl.read_csv(csv_path, separator=";", encoding="latin-1", infer_schema=False)
    assert frame.columns == ["NO_REGIAO", "SG_UF", "NO_REGIONAL"]
    assert frame["NO_REGIAO"].to_list() == ["SUL", "NORDESTE"]


def test_headerless_csv_with_another_layout_fails_loudly(tmp_path):
    from guaraci.opendatasus.portal_files import _prepend_header

    csv_path = tmp_path / "p.csv"
    csv_path.write_text('"SUL";"RS"\n', encoding="utf-8")
    try:
        _prepend_header(csv_path, ("A", "B", "C"))
    except ValueError as exc:
        assert "changed its layout" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
