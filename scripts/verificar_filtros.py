"""Confere, fonte a fonte, se cada filtro é aplicado de verdade.

Para cada fonte faz uma coleta pequena sem filtro (a linha de base) e, para
cada parâmetro de filtro, uma coleta com um valor escolhido assim:

- parâmetro com lista de valores permitidos: um valor diferente do padrão;
- parâmetro de texto livre cujo nome também é coluna do dado: o valor mais
  comum dessa coluna na linha de base (código de município, CNES...).

O filtro falha quando a coleta quebra, quando o resultado sai idêntico ao da
linha de base (filtro ignorado) ou quando a coluna de mesmo nome traz valor
diferente do pedido. Filtro que devolve vazio sai como aviso: pode ser a
combinação que não existe, não defeito.

    python scripts/verificar_filtros.py [--fontes a,b] [--workers 4]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verificar_rotas as vr  # noqa: E402

import polars as pl  # noqa: E402
from loguru import logger  # noqa: E402

from guaraci.services.downloads import DownloadService  # noqa: E402

# Não são filtros de conteúdo: técnica, exportação, janela de tempo (já
# exercitada pelas outras camadas) e paginação.
_NAO_FILTRO = {
    "output_dir", "output_format", "keep_raw", "api_base_url", "timeout", "batch_size",
    "max_pages", "start_year", "end_year", "start_date", "end_date", "results_url",
    "overwrite", "extract_archives", "pause_seconds", "latitude", "longitude",
    "codigo_cnes", "codigo_tipo_unidade", "station_ids", "stations",
}
# Colunas em que o valor do filtro aparece com outro nome.
_ALIASES = {
    "uf": ["uf", "sg_uf", "sg_uf_not", "estado", "sigla_uf", "uf_residencia"],
    "states": ["uf", "sg_uf", "sg_uf_not", "estado", "sigla_uf"],
    "sexo": ["sexo", "cs_sexo", "tp_sexo"],
}


def _frame(resultado: Dict[str, Any]) -> Optional[pl.DataFrame]:
    arquivos = [Path(p) for p in (resultado.get("exported_files") or []) if str(p).endswith(".csv")]
    if not arquivos:
        return None
    frames = [pl.read_csv(a, infer_schema=False) for a in arquivos]
    return pl.concat(frames, how="diagonal") if len(frames) > 1 else frames[0]


def _coleta(service: DownloadService, s: str, params: Dict[str, Any]) -> Optional[pl.DataFrame]:
    """Coleta, lê o CSV para a memória e apaga a pasta: o disco não acumula."""
    try:
        return _frame(service.run(s, **params).to_dict())
    finally:
        shutil.rmtree(params["output_dir"], ignore_errors=True)


def _assinatura(frame: Optional[pl.DataFrame]) -> str:
    if frame is None:
        return "vazio"
    return hashlib.sha1(frame.write_csv().encode("utf-8")).hexdigest()


def _valores_de_filtro(
    spec: Dict[str, Any], base: Optional[pl.DataFrame], base_params: Dict[str, Any]
) -> Optional[Any]:
    nome, tipo, padrao = spec["name"], spec["type"], spec.get("default")
    permitidos = spec.get("allowed_values") or []
    if permitidos:
        padroes = set(padrao if isinstance(padrao, list) else [padrao])
        na_base = base_params.get(nome)
        padroes |= set(na_base if isinstance(na_base, list) else [na_base])
        preferidos = [v for v in permitidos if v not in padroes]
        if nome == "states":
            # FTP: a base já vem com AC; outra UF pequena mantém a coleta leve.
            preferidos = [v for v in ("RR", "AP") if v in permitidos] or preferidos
        elif nome in ("uf", "ufs") and "states" in base_params:
            preferidos = [v for v in ("RR", "AP") if v in permitidos] or preferidos
        elif nome in ("uf", "ufs"):
            preferidos = [v for v in ("SP", "BA", "RJ") if v in permitidos] or preferidos
        if not preferidos:
            return None
        return [preferidos[0]] if tipo == "string_list" else preferidos[0]
    if tipo == "string" and base is not None:
        coluna = next((c for c in base.columns if c.lower() == nome.lower()), None)
        if coluna is None:
            return None
        comuns = base[coluna].drop_nulls().value_counts(sort=True)
        if comuns.height == 0:
            return None
        return str(comuns[coluna][0])
    return None


def _coluna_do_filtro(nome: str, frame: pl.DataFrame) -> Optional[str]:
    candidatos = [nome.lower()] + _ALIASES.get(nome, [])
    for c in frame.columns:
        if c.lower() in candidatos:
            return c
    return None


def confere_fonte(service: DownloadService, s: str, pasta: Path) -> Dict[str, Any]:
    schema = service.get_source_schema(s)
    specs = [p for p in schema["params"] if p["name"] not in _NAO_FILTRO and p["type"] != "boolean"
             and p["type"] != "integer"]
    if not specs or "output_format" not in {p["name"] for p in schema["params"]}:
        return {"pulada": "sem filtro de conteúdo"}
    base_params = vr.params_pequenos(schema, s, pasta / "base")
    base_params["output_format"] = "csv"
    # Nas APIs a base vai sem recorte de UF. No FTP fica o AC do verificador:
    # sem ele a base baixava o país inteiro (CIHA 4,8 GB, CNES 3,8 GB) e a
    # verificação semanal esgotava o disco do runner.
    for spec in specs:
        if spec["name"] in ("uf", "ufs") and s not in vr._OVERRIDES:
            base_params.pop(spec["name"], None)
    try:
        base = _coleta(service, s, base_params)
    except Exception as exc:  # noqa: BLE001
        texto = f"{type(exc).__name__}: {exc}"
        if any(c in texto for c in vr._CREDENCIAIS) or "is required" in texto:
            return {"pulada": texto[:160]}
        return {"problemas": [f"linha de base falhou: {texto[:250]}"], "avisos": [], "filtros": {}}
    assinatura_base = _assinatura(base)

    problemas: List[str] = []
    avisos: List[str] = []
    filtros: Dict[str, Any] = {}
    for spec in specs:
        valor = _valores_de_filtro(spec, base, base_params)
        if valor is None:
            filtros[spec["name"]] = "sem valor testável"
            continue
        params = dict(base_params, output_dir=str(pasta / spec["name"]))
        params[spec["name"]] = valor
        if spec["name"] in ("uf", "ufs") and "states" in params:
            # uf filtra dentro dos arquivos baixados por states; com UFs
            # diferentes a combinação sai sempre vazia.
            params["states"] = valor if isinstance(valor, list) else [valor]
        rotulo = f"{spec['name']}={valor}"
        try:
            frame = _coleta(service, s, params)
        except Exception as exc:  # noqa: BLE001
            problemas.append(f"{rotulo}: coleta quebrou: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        if frame is None or frame.height == 0:
            avisos.append(f"{rotulo}: nada voltou")
            filtros[spec["name"]] = "vazio"
            continue
        if _assinatura(frame) == assinatura_base and base is not None and base.height > 0:
            problemas.append(f"{rotulo}: resultado idêntico ao sem filtro ({frame.height} linhas): filtro ignorado?")
            continue
        coluna = _coluna_do_filtro(spec["name"], frame)
        esperado = {str(v).upper() for v in (valor if isinstance(valor, list) else [valor])}
        if coluna is not None:
            vistos = {str(v).upper() for v in frame[coluna].drop_nulls().unique().to_list()}
            fora = vistos - esperado
            # Coluna de UF pode vir como código IBGE (35) em vez de sigla (SP):
            # só acusa quando os valores são do mesmo tipo do pedido.
            mesmo_tipo = all(v.isalpha() == next(iter(esperado)).isalpha() for v in vistos) if vistos else True
            if fora and mesmo_tipo:
                problemas.append(f"{rotulo}: coluna {coluna} traz {sorted(fora)[:5]}")
                continue
        filtros[spec["name"]] = f"ok ({frame.height} linhas{', conferido em ' + coluna if coluna else ''})"
    return {"problemas": problemas, "avisos": avisos, "filtros": filtros}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fontes", default="")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="ERROR")
    service = DownloadService()
    fontes = [d.source for d in service.list_sources()]
    if args.fontes:
        fontes = [f for f in fontes if f in set(args.fontes.split(","))]
    base = Path(vr.tempfile.mkdtemp(prefix="guaraci_filtros_"))

    def um(s: str) -> Tuple[str, Dict[str, Any]]:
        try:
            return s, confere_fonte(service, s, base / s)
        except Exception as exc:  # noqa: BLE001
            return s, {"problemas": [f"verificador quebrou: {type(exc).__name__}: {str(exc)[:300]}"], "avisos": []}

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        resultados = dict(pool.map(um, fontes))

    # Segunda tentativa só para o que falhou: a origem oscila, e a
    # verificação semanal não deve abrir issue por um 500 passageiro.
    repetir = [s for s, r in resultados.items() if r.get("problemas")]
    if repetir:
        time.sleep(60)
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados.update(dict(pool.map(um, repetir)))
    saida = vr.ROOT / "reports" / f"verificacao_filtros_{time.strftime('%Y%m%d_%H%M')}.json"
    saida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    testados = sum(1 for r in resultados.values() for v in (r.get("filtros") or {}).values() if str(v).startswith("ok"))
    falhas = {s: r for s, r in resultados.items() if r.get("problemas")}
    print(f"{len(fontes)} fontes, {testados} filtros confirmados, {len(falhas)} fontes com problema, "
          f"{time.monotonic() - t0:.0f}s -> {saida}")
    for s, r in sorted(falhas.items()):
        for p in r["problemas"]:
            print(f"PROBLEMA {s:<45} {p}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
