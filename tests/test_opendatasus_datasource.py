"""Tests for OpenDataSUS datasource DEMAS mode behavior."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from guaraci.opendatasus.client import OpenDataSUSClientError
from guaraci.opendatasus.datasource import OpenDataSUSDataSource


def _slice_rows(rows, params):  # noqa: ANN001
    """Simula a paginação real do DEMAS: offset conta LINHAS, não páginas."""
    offset = int(params.get("offset", 0))
    limit = int(params.get("limit", len(rows)))
    return rows[offset : offset + limit]


class _FakeDemasClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    ROWS = [
        {"codigo_documento": "a", "data_vacina": "2025-01-10 00:00:00-03", "sigla_uf_estabelecimento": "SP"},
        {"codigo_documento": "b", "data_vacina": "2025-02-01 00:00:00-03", "sigla_uf_estabelecimento": "SP"},
        {"codigo_documento": "c", "data_vacina": "2025-01-20 00:00:00-03", "sigla_uf_estabelecimento": "RJ"},
        {"codigo_documento": "d", "data_vacina": "2025-01-25 00:00:00-03", "sigla_uf_estabelecimento": "SP"},
    ]

    def demas_get(self, path: str, params):  # noqa: ANN001
        if path != "/vacinacao/doses-aplicadas-pni-2025":
            return {"doses_aplicadas_pni": []}
        return {"doses_aplicadas_pni": _slice_rows(self.ROWS, params)}


class _FakeDemasMixedTypeClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def demas_get(self, path: str, params):  # noqa: ANN001
        offset = int(params.get("offset", 0))
        if path != "/vacinacao/doses-aplicadas-pni-2025":
            return {"doses_aplicadas_pni": []}
        if offset == 0:
            return {
                "doses_aplicadas_pni": [
                    {
                        "codigo_documento": "a",
                        "data_vacina": "2025-01-10 00:00:00-03",
                        "sigla_uf_estabelecimento": "SP",
                        "descricao_dose_vacina": 1,
                    },
                    {
                        "codigo_documento": "b",
                        "data_vacina": "2025-01-11 00:00:00-03",
                        "sigla_uf_estabelecimento": "SP",
                        "descricao_dose_vacina": "Registro anterior/Transcrição de caderneta",
                    },
                ]
            }
        return {"doses_aplicadas_pni": []}


class _FakeDemasZikavirusClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    ROWS = [
        {"tp_not": "2", "dt_notific": "2016-01-05", "sg_uf_not": "35"},
        {"tp_not": "2", "dt_notific": "2016-02-01", "sg_uf_not": "35"},
        {"tp_not": "2", "dt_notific": "2016-01-12", "sg_uf_not": "29"},
    ]

    def demas_get(self, path: str, params):  # noqa: ANN001
        if path != "/arboviroses/zikavirus":
            return {"arboviroses_zikavirus": []}
        return {"arboviroses_zikavirus": _slice_rows(self.ROWS, params)}


class _FakeDemasFebreAmarelaClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    ROWS = [
        {"mun_lpi": "ALTO ALEGRE", "dt_is": "29/11/1994", "uf_lpi": "RR"},
        {"mun_lpi": "PACARAIMA", "dt_is": "19/02/1995", "uf_lpi": "RR"},
        {"mun_lpi": "AMARANTE", "dt_is": "01/04/1995", "uf_lpi": "MA"},
    ]

    def demas_get(self, path: str, params):  # noqa: ANN001
        if path != "/arboviroses/febre-amarela-humanos-primatas-nao-humanos":
            return {"febre_amarela_humanos_primatas": []}
        return {"febre_amarela_humanos_primatas": _slice_rows(self.ROWS, params)}


class _FakeDemasGenericClient:
    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self) -> None:
        self.calls = []

    def demas_get(self, path: str, params):  # noqa: ANN001
        self.calls.append((path, dict(params)))
        if path == "/cnes/estabelecimentos":
            return {"cnes_estabelecimentos": [{"codigo_cnes": "123", "nome": "UBS"}]}
        if path == "/cnes/estabelecimentos/123":
            return {"cnes_estabelecimentos": [{"codigo_cnes": "123", "nome": "UBS"}]}
        return {"items": []}


def test_download_demas_filters_date_and_uf(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=10,
    )

    assert payload["downloaded_count"] == 2
    assert payload["documents_found"] == 2
    assert payload["api_base_url"] == "https://apidadosabertos.saude.gov.br"
    assert payload["raw_file"] is None
    assert payload["keep_raw"] is False

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["request"]["filters"]["api_mode"] == "demas"
    assert manifest["request"]["filters"]["pages_scanned"] == 2
    assert manifest["request"]["filters"]["truncated"] is False
    assert not manifest["artifacts"]["materialized_paths"]


def test_download_generic_demas_source_passes_swagger_query_params(tmp_path) -> None:  # noqa: ANN001
    client = _FakeDemasGenericClient()
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=client,  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="cnes/estabelecimentos",
        codigo_uf="35",
        status="ATIVO",
        batch_size=10,
        max_pages=1,
        keep_raw=True,
    )

    assert payload["downloaded_count"] == 1
    assert client.calls[0][0] == "/cnes/estabelecimentos"
    assert client.calls[0][1]["codigo_uf"] == "35"
    assert client.calls[0][1]["status"] == "ATIVO"
    assert client.calls[0][1]["limit"] == 10
    assert client.calls[0][1]["offset"] == 0
    assert payload["api_params"] == {"codigo_uf": "35", "status": "ATIVO"}

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["request"]["filters"]["api_params"] == {"codigo_uf": "35", "status": "ATIVO"}
    assert manifest["request"]["filters"]["endpoint_query_params"][0]["params"] == {
        "codigo_uf": "35",
        "status": "ATIVO",
    }


def test_download_generic_demas_source_substitutes_path_params(tmp_path) -> None:  # noqa: ANN001
    client = _FakeDemasGenericClient()
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=client,  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="cnes/estabelecimentos/{codigo_cnes}",
        codigo_cnes="123",
        batch_size=10,
        max_pages=1,
        keep_raw=True,
    )

    assert payload["downloaded_count"] == 1
    assert client.calls[0][0] == "/cnes/estabelecimentos/123"
    assert "codigo_cnes" not in client.calls[0][1]


def test_download_generic_demas_source_requires_path_params(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasGenericClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="codigo_cnes"):
        datasource.download(
            dataset="cnes/estabelecimentos/{codigo_cnes}",
            batch_size=10,
            max_pages=1,
        )


def test_download_demas_marks_truncated_when_max_pages_is_reached(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=1,
    )

    assert payload["downloaded_count"] == 1
    assert "max_pages" in str(payload.get("export_warning", "")).lower()

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["request"]["filters"]["truncated"] is True


def test_download_demas_mixed_types_does_not_break_job(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasMixedTypeClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=3,
        output_format="csv",
    )

    assert payload["downloaded_count"] == 2
    assert payload["documents_found"] == 2
    assert (payload.get("exported_files") or payload.get("export_warning")) is not None


def test_download_demas_export_error_becomes_warning(tmp_path) -> None:  # noqa: ANN001
    class _BrokenExportDataSource(OpenDataSUSDataSource):
        def export(self, df, format: str, name: str):  # noqa: A003, ANN001
            raise RuntimeError("forced export failure")

    datasource = _BrokenExportDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        start_date="2025-01-01",
        end_date="2025-01-31",
        uf="SP",
        batch_size=2,
        max_pages=3,
        output_format="csv",
    )

    assert payload["downloaded_count"] == 2
    assert payload["exported_files"] == []
    warning = str(payload.get("export_warning", "")).lower()
    assert "export failed after download" in warning
    assert "keep_raw=true" in warning

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["warnings"]


def test_download_demas_failure_adds_endpoint_context(tmp_path) -> None:  # noqa: ANN001
    class _FailingDemasClient:
        mode = "demas"
        base_url = "https://apidadosabertos.saude.gov.br"

        def demas_get(self, path: str, params):  # noqa: ANN001
            raise OpenDataSUSClientError(
                "OpenDataSUS request failed (503): temporarily unavailable",
                category="http_error",
                retryable=True,
                hint="Retry later, reduce the query window, or lower request volume.",
            )

    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FailingDemasClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(OpenDataSUSClientError) as excinfo:
        datasource.download(
            dataset="doses_aplicadas_pni",
            start_year=2025,
            end_year=2025,
            batch_size=2,
            max_pages=2,
        )

    message = str(excinfo.value)
    assert "dataset 'doses_aplicadas_pni'" in message
    assert "/vacinacao/doses-aplicadas-pni-2025" in message
    assert "page 1" in message
    assert "retry later" in message.lower()


def test_download_zikavirus_filters_by_date_and_uf_code(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasZikavirusClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="zikavirus",
        start_year=2016,
        end_year=2016,
        start_date="2016-01-01",
        end_date="2016-01-31",
        uf="SP",
        batch_size=2,
        max_pages=5,
    )

    assert payload["downloaded_count"] == 1
    assert payload["documents_found"] == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    endpoints = manifest.get("request", {}).get("filters", {}).get("endpoints", [])
    assert "/arboviroses/zikavirus" in endpoints


def test_download_febre_amarela_filters_by_date_and_uf(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasFebreAmarelaClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="febre_amarela",
        start_year=1994,
        end_year=1995,
        start_date="1994-11-01",
        end_date="1994-12-31",
        uf="RR",
        batch_size=2,
        max_pages=5,
    )

    assert payload["downloaded_count"] == 1
    assert payload["documents_found"] == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    endpoints = manifest.get("request", {}).get("filters", {}).get("endpoints", [])
    assert "/arboviroses/febre-amarela-humanos-primatas-nao-humanos" in endpoints


def test_download_demas_keep_raw_true_generates_jsonl(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        uf="SP",
        batch_size=2,
        max_pages=2,
        keep_raw=True,
    )

    raw_file = payload.get("raw_file")
    assert isinstance(raw_file, str)
    assert raw_file.endswith(".jsonl")
    assert (tmp_path / "raw").exists()


# --------------------------------------------------------------------------
# srag_demas: dt_notific do endpoint DEMAS srag-2019-2026 vem colapsado no
# marcador de temporada (verificado ao vivo em 2026-09-02), entao refinamento
# por data e recusado em vez de descartar registros em silencio.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "refinement",
    [{"start_date": "2024-01-01"}, {"end_date": "2024-03-31"}],
)
def test_srag_demas_rejects_date_refinement(tmp_path, refinement) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path))

    with pytest.raises(ValueError, match="Refinamento por data"):
        datasource.download(
            dataset="srag_demas",
            start_year=2024,
            end_year=2024,
            **refinement,
        )


def test_srag_demas_date_refinement_check_is_reusable() -> None:
    with pytest.raises(ValueError, match="srag_arquivos"):
        OpenDataSUSDataSource.check_unsupported_refinements(
            dataset="srag_demas",
            start_date="2024-01-01",
        )

    # Sem refinamento de data, ou em datasets cuja coluna e confiavel, passa.
    OpenDataSUSDataSource.check_unsupported_refinements(dataset="srag_demas")
    OpenDataSUSDataSource.check_unsupported_refinements(dataset="srag_demas", start_date="  ")
    OpenDataSUSDataSource.check_unsupported_refinements(
        dataset="dengue",
        start_date="2024-01-01",
    )


def test_srag_demas_uf_refinement_still_allowed(tmp_path) -> None:  # noqa: ANN001
    """sg_uf e preenchido normalmente; so a coluna de data e inutilizavel."""
    OpenDataSUSDataSource.check_unsupported_refinements(dataset="srag_demas", uf="SP")


class _ProbeClient:
    """Responde a sonda de pre-voo: ha ou nao dado alem do offset pedido."""

    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self, total_rows: int = 0, raises: bool = False) -> None:
        self.total_rows = total_rows
        self.raises = raises
        self.probes = []

    def demas_get(self, path: str, params):  # noqa: ANN001
        self.probes.append((path, int(params.get("offset", 0))))
        if self.raises:
            raise ConnectionError("API fora do ar durante o pre-voo")
        beyond = int(params.get("offset", 0)) < self.total_rows
        return {"linhas": [{"x": 1}] if beyond else []}


def test_preflight_warns_when_the_source_really_exceeds_the_cap() -> None:
    """A sonda pergunta a API em vez de adivinhar pelo nome da fonte."""
    client = _ProbeClient(total_rows=4_000_000)
    datasource = OpenDataSUSDataSource(client=client)  # type: ignore[arg-type]

    warnings = datasource.preflight_warnings(dataset="srag_demas", start_year=2024, end_year=2024)

    assert any("VAI TRUNCAR" in item and "250.000 linhas" in item for item in warnings)
    assert any("srag_arquivos" in item for item in warnings)
    # A sonda pede exatamente uma linha no offset do teto.
    assert client.probes and all(offset == 250_000 for _, offset in client.probes)
    # 2024 cai no bloco 2019-2026 inteiro: o aviso precisa dizer isso.
    assert any("blocos fixos" in item and "2019-2026" in item for item in warnings)


def test_preflight_is_quiet_when_the_source_fits_in_the_cap() -> None:
    client = _ProbeClient(total_rows=1_000)
    datasource = OpenDataSUSDataSource(client=client)  # type: ignore[arg-type]

    warnings = datasource.preflight_warnings(dataset="dengue", start_year=2024, end_year=2024)

    assert warnings == []


def test_preflight_warns_for_any_demas_source_not_just_the_curated_ones() -> None:
    """O aviso nao depende de alguem ter marcado a fonte a mao."""
    client = _ProbeClient(total_rows=4_000_000)
    datasource = OpenDataSUSDataSource(client=client)  # type: ignore[arg-type]

    for dataset in ("dengue", "zikavirus"):
        warnings = datasource.preflight_warnings(dataset=dataset, start_year=2024, end_year=2024)
        assert any("VAI TRUNCAR" in item for item in warnings), dataset
        # Sem fonte em lote, o remedio e levar a paginacao ate o fim.
        assert any("Aumente max_pages" in item for item in warnings), dataset


def test_preflight_probe_follows_max_pages_and_batch_size() -> None:
    client = _ProbeClient(total_rows=20_000_000)
    datasource = OpenDataSUSDataSource(client=client)  # type: ignore[arg-type]

    warnings = datasource.preflight_warnings(
        dataset="srag_demas",
        start_year=2019,
        end_year=2026,
        max_pages=20000,
        batch_size=500,
    )

    assert any("10.000.000 linhas" in item for item in warnings)
    assert all(offset == 10_000_000 for _, offset in client.probes)
    # Janela igual ao bloco: nada a avisar sobre alargamento.
    assert not any("blocos fixos" in item for item in warnings)


def test_preflight_never_blocks_the_launch_when_the_probe_fails() -> None:
    """Pre-voo e informativo: API fora do ar nao pode impedir o download."""
    client = _ProbeClient(raises=True)
    datasource = OpenDataSUSDataSource(client=client)  # type: ignore[arg-type]

    warnings = datasource.preflight_warnings(dataset="dengue", start_year=2024, end_year=2024)

    assert warnings == []


def test_preflight_ignores_unknown_datasets() -> None:
    datasource = OpenDataSUSDataSource(client=_ProbeClient())  # type: ignore[arg-type]
    assert datasource.preflight_warnings(dataset="dataset_inexistente") == []


def test_download_demas_payload_reports_truncation(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        batch_size=1,
        max_pages=1,
        keep_raw=True,
    )

    assert payload["truncated"] is True
    warnings = payload["warnings"]
    assert any("DOWNLOAD TRUNCADO" in item for item in warnings)
    assert any("max_pages=1" in item for item in warnings)


def test_download_demas_payload_not_truncated_when_pages_exhausted(tmp_path) -> None:  # noqa: ANN001
    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )

    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        batch_size=10,
        max_pages=10,
        keep_raw=True,
    )

    assert payload["truncated"] is False
    assert not any("DOWNLOAD TRUNCADO" in item for item in payload["warnings"])


def test_truncation_remedy_points_to_the_bulk_source_when_one_exists(tmp_path) -> None:  # noqa: ANN001
    """Para srag_demas, "aumente max_pages" e conselho ruim: 4,4M linhas
    esgotariam em ~8h acumulando ~36 GB em memoria. O remedio e srag_arquivos."""
    assert OpenDataSUSDataSource.DATASET_SPECS["srag_demas"].bulk_alternative == "srag_arquivos"

    datasource = OpenDataSUSDataSource(
        output_path=str(tmp_path),
        client=_FakeDemasClient(),  # type: ignore[arg-type]
    )
    payload = datasource.download(
        dataset="doses_aplicadas_pni",
        start_year=2025,
        end_year=2025,
        batch_size=1,
        max_pages=1,
        keep_raw=True,
    )

    # doses_aplicadas_pni nao tem fonte em lote: ai sim o remedio e max_pages.
    truncation = next(item for item in payload["warnings"] if "DOWNLOAD TRUNCADO" in item)
    assert "Aumente max_pages" in truncation
    assert "srag_arquivos" not in truncation


# --------------------------------------------------------------------------
# Modo DEMAS: escrita por página + retomada por offset. Antes o download
# acumulava tudo em memória e só escrevia no fim — teto de ~36 GB para os
# 4,45M de linhas do bloco SRAG 2019-2026, e qualquer falha perdia tudo.
# --------------------------------------------------------------------------


class _BulkDemasClient:
    """Gera `total` linhas paginadas, registrando os offsets pedidos."""

    mode = "demas"
    base_url = "https://apidadosabertos.saude.gov.br"

    def __init__(self, total, fail_from_page=None, page_size=10):  # noqa: ANN001
        self.total = total
        # Falha decidida pela PÁGINA, não por um contador de chamadas: com
        # busca paralela a ordem das chamadas varia, e um contador tornaria o
        # teste dependente de qual thread chegou primeiro.
        self.fail_from_page = fail_from_page
        self.page_size = page_size
        self.calls = 0
        self.offsets_requested = []

    def demas_get(self, path: str, params):  # noqa: ANN001
        if path != "/vacinacao/doses-aplicadas-pni-2025":
            return {"doses_aplicadas_pni": []}
        page = int(params.get("offset", 0)) // self.page_size
        if self.fail_from_page is not None and page >= self.fail_from_page:
            raise ConnectionError("simulated network drop")
        self.calls += 1
        offset = int(params.get("offset", 0))
        self.offsets_requested.append(offset)
        limit = int(params.get("limit", 1))
        rows = [
            {
                "codigo_documento": f"doc-{index}",
                "data_vacina": "2025-01-10 00:00:00-03",
                "sigla_uf_estabelecimento": "SP",
            }
            for index in range(offset, min(offset + limit, self.total))
        ]
        return {"doses_aplicadas_pni": rows}


def _download_bulk(datasource, **overrides):  # noqa: ANN001
    kwargs = {
        "dataset": "doses_aplicadas_pni",
        "start_year": 2025,
        "end_year": 2025,
        "batch_size": 10,
        "max_pages": 100,
        "keep_raw": True,
    }
    kwargs.update(overrides)
    return datasource.download(**kwargs)


def _spool_ids(path):  # noqa: ANN001
    with Path(path).open(encoding="utf-8") as handler:
        return [json.loads(line)["codigo_documento"] for line in handler]


def test_demas_writes_each_page_to_disk_instead_of_buffering(tmp_path) -> None:  # noqa: ANN001
    client = _BulkDemasClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    payload = _download_bulk(datasource)

    spool = Path(payload["raw_file"])
    assert spool.exists()
    assert payload["downloaded_count"] == 95
    assert _spool_ids(spool) == [f"doc-{index}" for index in range(95)]


def test_demas_drops_memory_buffer_and_still_exports_from_the_spool(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(OpenDataSUSDataSource, "MAX_RECORDS_IN_MEMORY", 20)
    client = _BulkDemasClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    payload = _download_bulk(datasource, output_format="csv")

    assert payload["downloaded_count"] == 95
    exported = Path(payload["exported_files"][0])
    assert exported.exists()
    with exported.open(encoding="utf-8") as handler:
        assert sum(1 for _ in handler) == 96  # 95 linhas + cabeçalho
    # load_dataframe segue respondendo, caindo para o spool em disco.
    assert datasource.load_dataframe("doses_aplicadas_pni").height == 95


def test_demas_keeps_the_spool_when_the_buffer_was_dropped(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """keep_raw=false não pode apagar o único artefato completo do download."""
    monkeypatch.setattr(OpenDataSUSDataSource, "MAX_RECORDS_IN_MEMORY", 20)
    client = _BulkDemasClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    payload = _download_bulk(datasource, keep_raw=False, output_format="csv")

    spools = list((tmp_path / "raw").glob("*.jsonl"))
    assert len(spools) == 1
    assert len(_spool_ids(spools[0])) == 95
    assert any("keep_raw=false" in item for item in payload["warnings"])


def test_demas_deletes_the_spool_for_small_downloads_without_keep_raw(tmp_path) -> None:  # noqa: ANN001
    client = _BulkDemasClient(total=30)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    _download_bulk(datasource, keep_raw=False, output_format="csv")

    assert list((tmp_path / "raw").glob("*.jsonl")) == []


def test_demas_resumes_an_interrupted_download_without_duplicating_rows(tmp_path) -> None:  # noqa: ANN001
    # Primeira tentativa cai depois de 4 páginas (40 linhas).
    failing = _BulkDemasClient(total=95, fail_from_page=4)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=failing)  # type: ignore[arg-type]
    with pytest.raises(ConnectionError):
        _download_bulk(datasource)

    checkpoints = list((tmp_path / "raw" / ".partial").glob("*.checkpoint.json"))
    assert len(checkpoints) == 1
    state = json.loads(checkpoints[0].read_text(encoding="utf-8"))
    assert state["rows_written"] == 40
    assert state["pages_done"] == 4

    # Segunda tentativa retoma do offset 40 em vez de rebaixar o começo.
    healthy = _BulkDemasClient(total=95)
    resumed = OpenDataSUSDataSource(output_path=str(tmp_path), client=healthy)  # type: ignore[arg-type]
    payload = _download_bulk(resumed)

    assert min(healthy.offsets_requested) == 40
    assert payload["resumed_from_rows"] == 40
    assert payload["downloaded_count"] == 95
    ids = _spool_ids(payload["raw_file"])
    assert len(set(ids)) == 95  # nenhuma linha duplicada na emenda
    assert ids == [f"doc-{index}" for index in range(95)]


def test_demas_checkpoint_is_removed_after_a_complete_run(tmp_path) -> None:  # noqa: ANN001
    client = _BulkDemasClient(total=30)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    _download_bulk(datasource)

    # Corrida completa não deixa checkpoint: a próxima execução busca dados novos.
    assert list((tmp_path / "raw" / ".partial").glob("*.checkpoint.json")) == []


def test_demas_truncates_a_half_written_page_on_resume(tmp_path) -> None:  # noqa: ANN001
    failing = _BulkDemasClient(total=95, fail_from_page=4)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=failing)  # type: ignore[arg-type]
    with pytest.raises(ConnectionError):
        _download_bulk(datasource)

    # Simula o processo morrendo no meio de um write: lixo depois do checkpoint.
    spool = next((tmp_path / "raw" / ".partial").glob("*.jsonl"))
    with spool.open("ab") as handler:
        handler.write(b'{"codigo_documento": "lix')

    healthy = _BulkDemasClient(total=95)
    resumed = OpenDataSUSDataSource(output_path=str(tmp_path), client=healthy)  # type: ignore[arg-type]
    payload = _download_bulk(resumed)

    assert _spool_ids(payload["raw_file"]) == [f"doc-{index}" for index in range(95)]


def test_demas_does_not_resume_across_different_queries(tmp_path) -> None:  # noqa: ANN001
    failing = _BulkDemasClient(total=95, fail_from_page=4)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=failing)  # type: ignore[arg-type]
    with pytest.raises(ConnectionError):
        _download_bulk(datasource)

    # Mesmo stem de artefato, mas página de tamanho diferente: o spool anterior
    # não é reaproveitável, então a coleta recomeça do zero.
    healthy = _BulkDemasClient(total=95)
    resumed = OpenDataSUSDataSource(output_path=str(tmp_path), client=healthy)  # type: ignore[arg-type]
    payload = _download_bulk(resumed, batch_size=5)

    assert payload["resumed_from_rows"] == 0
    assert min(healthy.offsets_requested) == 0
    assert _spool_ids(payload["raw_file"]) == [f"doc-{index}" for index in range(95)]


def test_demas_streaming_export_matches_the_eager_one(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """O export em lotes precisa produzir o mesmo dado do caminho em memória."""
    import polars as pl

    client = _BulkDemasClient(total=95)
    eager_ds = OpenDataSUSDataSource(output_path=str(tmp_path / "eager"), client=client)  # type: ignore[arg-type]
    eager_payload = _download_bulk(eager_ds, output_format="parquet")

    monkeypatch.setattr(OpenDataSUSDataSource, "MAX_RECORDS_IN_MEMORY", 20)
    streamed_ds = OpenDataSUSDataSource(
        output_path=str(tmp_path / "streamed"),
        client=_BulkDemasClient(total=95),  # type: ignore[arg-type]
    )
    streamed_payload = _download_bulk(streamed_ds, output_format="parquet")

    eager = pl.read_parquet(eager_payload["exported_files"][0]).sort("codigo_documento")
    streamed = pl.read_parquet(streamed_payload["exported_files"][0]).sort("codigo_documento")
    assert set(eager.columns) == set(streamed.columns)
    assert eager.height == streamed.height == 95
    assert streamed.select(sorted(streamed.columns)).equals(eager.select(sorted(eager.columns)))


def test_spool_schema_handles_all_null_and_mixed_columns(tmp_path) -> None:  # noqa: ANN001
    """Coluna só-nula viraria dtype Null e estouraria no primeiro valor real."""
    import polars as pl

    spool = tmp_path / "sample.jsonl"
    spool.write_text(
        "\n".join(
            [
                json.dumps({"a": None, "b": 1, "c": "x", "d": 1}),
                json.dumps({"a": None, "b": 2, "c": "y", "d": 1.5}),
                json.dumps({"a": "apareceu tarde", "b": 3, "c": "z", "d": 2}),
            ]
        ),
        encoding="utf-8",
    )

    schema = OpenDataSUSDataSource._infer_spool_schema(spool)
    assert schema["a"] == pl.String  # só-nula na amostra inicial
    assert schema["b"] == pl.Int64
    assert schema["c"] == pl.String
    assert schema["d"] == pl.Float64  # int + float

    datasource = OpenDataSUSDataSource(output_path=str(tmp_path))
    exported = datasource._export_spool(spool_path=spool, format="parquet", name="amostra")
    frame = pl.read_parquet(exported)
    assert frame.height == 3
    assert frame["a"].to_list() == [None, None, "apareceu tarde"]


def test_spool_export_falls_back_to_eager_for_sqlite(tmp_path) -> None:  # noqa: ANN001
    """SQLite não tem sink incremental: o caminho eager continua valendo."""
    spool = tmp_path / "sample.jsonl"
    spool.write_text(json.dumps({"a": 1, "b": "x"}) + "\n", encoding="utf-8")

    datasource = OpenDataSUSDataSource(output_path=str(tmp_path))
    exported = datasource._export_spool(spool_path=spool, format="sqlite", name="amostra")

    assert exported.exists()
    assert exported.suffix == ".sqlite"


# --------------------------------------------------------------------------
# Paginação concorrente. O gargalo do modo DEMAS é a latência por request
# (~200 linhas/s numa conexão, ~1.200 em oito), então as páginas são buscadas
# em ondas paralelas — mas gravadas em ordem, para o checkpoint continuar
# significando "as N primeiras páginas estão no disco".
# --------------------------------------------------------------------------


class _ConcurrencyProbeClient(_BulkDemasClient):
    """Registra a concorrência real observada durante o download."""

    def __init__(self, total, **kwargs):  # noqa: ANN001
        super().__init__(total, **kwargs)
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    def demas_get(self, path: str, params):  # noqa: ANN001
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            time.sleep(0.02)  # janela para as threads irmãs se sobreporem
            return super().demas_get(path, params)
        finally:
            with self._lock:
                self.in_flight -= 1


def test_pages_are_fetched_in_parallel(tmp_path) -> None:  # noqa: ANN001
    client = _ConcurrencyProbeClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    payload = _download_bulk(datasource, concurrency=4)

    assert client.max_in_flight > 1
    assert client.max_in_flight <= 4
    assert payload["downloaded_count"] == 95


def test_concurrency_one_keeps_requests_sequential(tmp_path) -> None:  # noqa: ANN001
    client = _ConcurrencyProbeClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    _download_bulk(datasource, concurrency=1)

    assert client.max_in_flight == 1


def test_concurrency_is_clamped_to_the_measured_ceiling(tmp_path) -> None:  # noqa: ANN001
    """Acima do teto a própria API rende menos, então o pedido é limitado."""
    client = _ConcurrencyProbeClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    _download_bulk(datasource, concurrency=999)

    assert client.max_in_flight <= OpenDataSUSDataSource.MAX_CONCURRENCY


def test_parallel_pages_are_written_in_order(tmp_path) -> None:  # noqa: ANN001
    """A onda chega fora de ordem, mas o spool tem que sair sequencial."""
    client = _ConcurrencyProbeClient(total=95)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    payload = _download_bulk(datasource, concurrency=8)

    assert _spool_ids(payload["raw_file"]) == [f"doc-{index}" for index in range(95)]


def test_parallel_download_keeps_the_prefix_when_a_page_fails(tmp_path) -> None:  # noqa: ANN001
    """Falha no meio de uma onda ainda grava e checkpointa o que veio antes."""
    client = _BulkDemasClient(total=95, fail_from_page=4)
    datasource = OpenDataSUSDataSource(output_path=str(tmp_path), client=client)  # type: ignore[arg-type]

    with pytest.raises(ConnectionError):
        _download_bulk(datasource, concurrency=4)

    state = json.loads(
        next((tmp_path / "raw" / ".partial").glob("*.checkpoint.json")).read_text(encoding="utf-8")
    )
    # A primeira onda (páginas 0-3) entrou; a segunda morreu inteira.
    assert state["pages_done"] == 4
    assert state["rows_written"] == 40

    healthy = _BulkDemasClient(total=95)
    resumed = OpenDataSUSDataSource(output_path=str(tmp_path), client=healthy)  # type: ignore[arg-type]
    payload = _download_bulk(resumed, concurrency=4)

    assert payload["resumed_from_rows"] == 40
    assert _spool_ids(payload["raw_file"]) == [f"doc-{index}" for index in range(95)]


def test_parallel_download_matches_the_sequential_result(tmp_path) -> None:  # noqa: ANN001
    sequential = OpenDataSUSDataSource(
        output_path=str(tmp_path / "seq"), client=_BulkDemasClient(total=95)  # type: ignore[arg-type]
    )
    parallel = OpenDataSUSDataSource(
        output_path=str(tmp_path / "par"), client=_BulkDemasClient(total=95)  # type: ignore[arg-type]
    )

    seq_payload = _download_bulk(sequential, concurrency=1)
    par_payload = _download_bulk(parallel, concurrency=8)

    assert seq_payload["downloaded_count"] == par_payload["downloaded_count"] == 95
    assert seq_payload["truncated"] == par_payload["truncated"] is False
    assert _spool_ids(seq_payload["raw_file"]) == _spool_ids(par_payload["raw_file"])
