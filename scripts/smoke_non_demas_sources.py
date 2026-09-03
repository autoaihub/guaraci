"""Smoke ao vivo das fontes que não são da API DEMAS.

Cada fonte é chamada pelo mesmo caminho do usuário (``DownloadService.run``),
com a menor janela que o schema aceita, e o resultado é classificado em ok,
vazio, credencial ausente ou erro. Serve para achar fonte quebrada antes que
alguém a encontre em produção.

Uso:
    python scripts/smoke_non_demas_sources.py [prefixo ...]
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guaraci.services.downloads import DownloadService

MODOS_ALVO = {
    "ana hidro api",
    "ibge api",
    "inmet portal zip",
    "inpe queimadas api",
    "nasa firms api",
    "nasa gpm api",
    "nasa power api",
    "gov.br crawl",
}

# Janela mínima: ano já fechado, para não esbarrar em publicação em curso.
ANO = 2023

# Valores plausíveis para parâmetros obrigatórios que não têm default útil.
PALPITES = {
    "uf": "SP",
    "ufs": "SP",
    "states": "SP",
    "sigla_uf": "SP",
    "latitude": "-23.55",
    "longitude": "-46.63",
    "lat": "-23.55",
    "lon": "-46.63",
    "start_date": f"{ANO}-01-01",
    "end_date": f"{ANO}-01-07",
    "level": "uf",
    "nivel": "uf",
    # A ANA recorta por estação, não por território: 58880001 é a régua de
    # Guaratinguetá, no Paraíba do Sul.
    "station_ids": ["58880001"],
    "stations": ["58880001"],
}


def monta_params(schema: dict, saida: Path) -> dict:
    params: dict[str, object] = {"output_dir": str(saida), "output_format": "parquet"}
    for item in schema["params"]:
        nome = item["name"]
        if nome in params:
            continue
        if nome in {"start_year", "end_year"}:
            # Respeita a cobertura declarada: as séries censitárias param em
            # 2022, e pedir fora dela testaria a validação, não a coleta.
            teto = item.get("maximum")
            piso = item.get("minimum")
            ano = ANO
            if isinstance(teto, int):
                ano = min(ano, teto)
            if isinstance(piso, int):
                ano = max(ano, piso)
            params[nome] = ano
            continue
        if not item.get("required"):
            continue
        if item.get("default") is not None:
            params[nome] = item["default"]
        elif nome in PALPITES:
            params[nome] = PALPITES[nome]
        elif item.get("allowed_values"):
            params[nome] = item["allowed_values"][0]
        else:
            params[nome] = PALPITES.get(nome, "1")
    return params


def classifica(exc: Exception) -> str:
    texto = str(exc).lower()
    if any(t in texto for t in ("token", "api key", "map_key", "credential", "unauthorized", "senha")):
        return "SEM CREDENCIAL"
    return "ERRO"


def main() -> None:
    prefixos = [a.lower() for a in sys.argv[1:]]
    service = DownloadService()
    alvos = [
        d.source
        for d in service.list_sources()
        if d.mode in MODOS_ALVO
        and (not prefixos or any(d.source.startswith(p) for p in prefixos))
    ]

    print(f"{len(alvos)} fontes a testar\n")
    resumo: dict[str, list[str]] = {}
    for fonte in sorted(alvos):
        with TemporaryDirectory() as tmp:
            saida = Path(tmp)
            inicio = time.perf_counter()
            try:
                schema = service.get_source_schema(fonte)
                resultado = service.run(fonte, **monta_params(schema, saida))
                payload = resultado.to_dict()
                exportados = payload.get("exported_files") or []
                baixados = payload.get("downloaded_count") or 0
                estado = "ok" if (exportados or baixados) else "VAZIO"
                detalhe = f"{baixados} registros, {len(exportados)} arquivo(s)"
            except Exception as exc:  # noqa: BLE001 - é um levantamento, não a coleta
                estado = classifica(exc)
                detalhe = str(exc).strip().replace("\n", " ")[:110]
                if estado == "ERRO" and "-v" in sys.argv:
                    traceback.print_exc()
            duracao = time.perf_counter() - inicio
        print(f"  {estado:14} {fonte:42} {duracao:6.1f}s  {detalhe}")
        resumo.setdefault(estado, []).append(fonte)

    print("\n=== resumo ===")
    for estado in sorted(resumo):
        print(f"  {estado:14} {len(resumo[estado])}")


if __name__ == "__main__":
    main()
