"""Smoke opt-in das fontes novas do Pacote A, turno 1 (rede real).

Desligado por padrão; ``GUARACI_ARQUIVOS_EXT_SMOKE=1`` liga. Baixa só arquivos pequenos
(ISP-RJ 2,4 MB, Infosiga veículos 2015 com 0,8 MB, SISDEPEN 1S2017 com 6 MB, IBAMA bioma
14 MB e decisões de embargo 125 KB). Disque 100, autos de infração e todos os demais
recursos fazem só HEAD (ou Range de 1 byte), pois têm de 100 MB a 1,9 GB.
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from guaraci.arquivos import HttpFileClient, ibama, seguranca, transito_sp
from guaraci.arquivos.http_files import datasource_for_spec

SMOKE = os.environ.get("GUARACI_ARQUIVOS_EXT_SMOKE") == "1"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not SMOKE, reason="Set GUARACI_ARQUIVOS_EXT_SMOKE=1 to enable the live file smoke test"
    ),
]

_TODAS = (
    ibama.IBAMA_AUTOS_INFRACAO,
    ibama.IBAMA_TERMOS_EMBARGO,
    seguranca.MDHC_DISQUE100,
    seguranca.SENAPPEN_SISDEPEN,
    seguranca.ISP_RJ_DELEGACIAS_MENSAL,
    seguranca.ISP_RJ_MUNICIPIOS_MENSAL,
    transito_sp.DETRAN_SP_INFOSIGA_SINISTROS,
    transito_sp.DETRAN_SP_INFOSIGA_PESSOAS,
    transito_sp.DETRAN_SP_INFOSIGA_VEICULOS,
)


def _run(spec, tmp_path, **kwargs):
    out = tmp_path / spec.key
    return datasource_for_spec(spec)(output_path=str(out)).download(
        output_dir=str(out), output_format="csv", **kwargs
    )


def test_live_isp_municipios_inteiro(tmp_path):
    payload = _run(seguranca.ISP_RJ_MUNICIPIOS_MENSAL, tmp_path)
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.width == 62 and frame.columns[:3] == ["fmun_cod", "fmun", "ano"]
    assert "Angra dos Reis" in frame["fmun"].to_list()


def test_live_infosiga_veiculos_2015(tmp_path):
    payload = _run(transito_sp.DETRAN_SP_INFOSIGA_VEICULOS, tmp_path, start_year=2015)
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns[:3] == ["id_sinistro", "id_veiculo", "marca_modelo"]
    assert frame.width == 12


def test_live_sisdepen_1s2017(tmp_path):
    payload = _run(seguranca.SENAPPEN_SISDEPEN, tmp_path, anos=[2017], meses=["S1"])
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.width == 1333
    assert frame.columns[:3] == ["ciclo", "Ano", "Referência"]


def test_live_ibama_bioma_e_decisoes(tmp_path):
    payload = _run(ibama.IBAMA_AUTOS_INFRACAO, tmp_path, indicadores=["bioma"])
    frame = pl.read_csv(payload["exported_files"][0], infer_schema=False)
    assert frame.columns[:4] == [
        "SEQ_AUTO_INFRACAO", "NUM_AUTO_INFRACAO", "CD_SERIE__AUTO_INFRACAO", "BIOMA",
    ]
    payload = _run(ibama.IBAMA_TERMOS_EMBARGO, tmp_path, indicadores=["decisao"])
    assert payload["failed_count"] == 0 and payload["exported_files"]


@pytest.mark.parametrize("spec", _TODAS, ids=lambda s: s.key)
def test_live_head_de_todos_os_recursos(spec):
    client = HttpFileClient(timeout_seconds=60, max_attempts=2)
    kwargs = {"probe": spec.probe} if spec.probe != "head" else {}
    missing = []
    for resource in spec.resources:
        try:
            remote = client.head(resource.url, **kwargs)
            assert remote.size and remote.size > 0
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{resource.code}: {str(exc)[:80]}")
    # O ano corrente do Infosiga ainda responde 404.
    allowed = 1 if spec.key.startswith("detran_sp_infosiga") else 0
    assert len(missing) <= allowed, missing
