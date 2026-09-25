"""Confere o CONTEÚDO do que cada fonte exporta, nos três formatos.

``verificar_rotas.py`` prova que a coleta termina e grava arquivo. Este
script abre o arquivo. Para cada fonte, faz a mesma coleta pequena em CSV,
Parquet e SQLite (mesma pasta, então o download bruto é reaproveitado) e
confere:

- cada formato exporta, e o arquivo tem linhas;
- os três formatos trazem as mesmas colunas e o mesmo número de linhas;
- nenhuma coluna genérica (``column_1``), sinal de cabeçalho perdido;
- nenhum texto com acentuação quebrada (``Ã§``, ``�``), sinal de encoding
  errado;
- as colunas batem com ``guaraci/data/field_dictionary.json``.

Colunas inteiramente vazias e colunas novas em relação ao dicionário saem
como aviso. As colunas vistas vão para ``reports/conteudo_colunas.json``,
de onde ``--promover`` preenche o dicionário das fontes que não têm campos.

    python scripts/verificar_conteudo.py [--fontes a,b] [--workers 5]
    python scripts/verificar_conteudo.py --promover
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verificar_rotas as vr  # noqa: E402  (define GUARACI_DATA_ROOT antes do import do pacote)

import polars as pl  # noqa: E402
from loguru import logger  # noqa: E402

from guaraci.services.downloads import DownloadService  # noqa: E402

ROOT = vr.ROOT
FORMATOS = ("csv", "parquet", "sqlite")
DICIONARIO = ROOT / "guaraci" / "data" / "field_dictionary.json"
COLUNAS_VISTAS = ROOT / "reports" / "conteudo_colunas.json"

# Mojibake típico de UTF-8 lido como latin-1 (Ã§, Ã£, Ã©...) e o caractere
# de substituição de um decode que falhou.
_MOJIBAKE = re.compile("Ã[\u0080-¿]|Â[ -¿]|�")
_GENERICA = re.compile(r"^(column_\d+|unnamed(: ?\d+)?|_duplicated_\d+)$", re.IGNORECASE)

# Acentuação quebrada que vem no arquivo publicado, conferida à mão
# (2026-09-24): não há o que o Guaraci corrigir sem inventar dado.
_MOJIBAKE_DA_ORIGEM = {
    "srag_arquivos": "29 lotes de vacina com 'Â'+NBSP no próprio parquet do banco vivo 2026",
}


def _brutos(pasta: Path) -> set:
    return set((pasta / "raw").glob("*.jsonl"))


def _bruto_da_coleta(pasta: Path, antes: set) -> Optional[pl.DataFrame]:
    """JSON bruto (keep_raw) gravado por esta coleta, se houver.

    As APIs do DEMAS não garantem ordem: duas chamadas iguais devolvem
    linhas diferentes (conferido com doses_aplicadas_pni e sisvan). Comparar
    um formato com outro acusava perda que não existe; cada export é
    comparado com o bruto da mesma coleta.
    """
    brutos = sorted(_brutos(pasta) - antes)
    if not brutos:
        return None
    linhas = [json.loads(l) for p in brutos for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not linhas:
        return None
    return pl.DataFrame(
        [{k: (None if v in (None, "") else str(v)) for k, v in r.items()} for r in linhas],
        infer_schema_length=None,
    )


def _ler(path: Path) -> List[Tuple[str, pl.DataFrame]]:
    """Devolve (rótulo, frame) por tabela do arquivo exportado."""
    ext = path.suffix.lower()
    if ext == ".csv":
        return [(path.stem, pl.read_csv(path, infer_schema=False, encoding="utf8"))]
    if ext == ".parquet":
        return [(path.stem, pl.read_parquet(path))]
    if ext in (".sqlite", ".db", ".sqlite3"):
        saida = []
        with sqlite3.connect(path) as conn:
            tabelas = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for tabela in tabelas:
                cur = conn.execute(f'SELECT * FROM "{tabela}"')
                nomes = [c[0] for c in cur.description]
                linhas = cur.fetchall()
                frame = pl.DataFrame(
                    {n: [str(r[i]) if r[i] is not None else None for r in linhas] for i, n in enumerate(nomes)},
                    schema={n: pl.Utf8 for n in nomes},
                )
                saida.append((f"{path.stem}:{tabela}", frame))
        return saida
    raise ValueError(f"extensão inesperada no export: {path.name}")


def _resumo(frames: List[Tuple[str, pl.DataFrame]]) -> Dict[str, Any]:
    linhas = sum(f.height for _, f in frames)
    colunas: List[str] = []
    for _, f in frames:
        colunas.extend(c for c in f.columns if c not in colunas)
    nulos: Dict[str, int] = {}
    for _, f in frames:
        for nome, n in zip(f.columns, f.null_count().row(0)):
            nulos[nome] = nulos.get(nome, 0) + int(n)
    mojibake = 0
    exemplos: List[str] = []
    vazias: List[str] = []
    for _, f in frames:
        amostra = f.head(50_000)
        for nome, tipo in amostra.schema.items():
            if amostra[nome].null_count() == amostra.height and amostra.height > 0:
                vazias.append(nome)
            if tipo == pl.Utf8:
                achados = amostra.filter(pl.col(nome).str.contains(_MOJIBAKE.pattern))[nome]
                if achados.len():
                    mojibake += achados.len()
                    exemplos.extend(str(v)[:60] for v in achados.head(2).to_list())
    return {
        "linhas": linhas,
        "colunas": colunas,
        "genericas": [c for c in colunas if _GENERICA.match(str(c))],
        "mojibake": mojibake,
        "mojibake_exemplos": exemplos[:4],
        "vazias": sorted(set(vazias)),
        "nulos": nulos,
    }


def confere_fonte(service: DownloadService, s: str, base: Path, dicionario: Dict[str, Any]) -> Dict[str, Any]:
    schema = service.get_source_schema(s)
    nomes = {p["name"] for p in schema["params"]}
    if "output_format" not in nomes:
        return {"pulada": "fonte sem exportação (crawler de arquivos brutos)"}
    pasta = base / s
    params = vr.params_pequenos(schema, s, pasta)
    if "keep_raw" in nomes:
        params["keep_raw"] = True
    por_formato: Dict[str, Any] = {}
    brutos: Dict[str, pl.DataFrame] = {}
    problemas: List[str] = []
    avisos: List[str] = []
    for formato in FORMATOS:
        params["output_format"] = formato
        t0 = time.monotonic()
        antes = _brutos(pasta)
        try:
            resultado = service.run(s, **params).to_dict()
        except Exception as exc:  # noqa: BLE001
            texto = f"{type(exc).__name__}: {exc}"
            if any(c in texto for c in vr._CREDENCIAIS) or "is required" in texto:
                return {"pulada": texto[:200]}
            problemas.append(f"{formato}: coleta falhou: {texto[:300]}")
            continue
        arquivos = [Path(p) for p in (resultado.get("exported_files") or [])]
        if not arquivos:
            if s in vr._ORIGEM_VAZIA:
                return {"pulada": "origem vazia (documentado)"}
            problemas.append(f"{formato}: nada exportado ({resultado.get('export_warning')})")
            continue
        try:
            frames = [fr for arq in arquivos for fr in _ler(arq)]
        except Exception as exc:  # noqa: BLE001
            problemas.append(f"{formato}: arquivo ilegível: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        info = _resumo(frames)
        bruto = _bruto_da_coleta(pasta, antes)
        if bruto is not None:
            brutos[formato] = bruto
            if info["mojibake"] and _resumo([("bruto", bruto)])["mojibake"]:
                avisos.append(f"{formato}: acentuação quebrada já vem da origem, ex. {info['mojibake_exemplos'][:2]}")
                info["mojibake"] = 0
        if info["mojibake"] and s in _MOJIBAKE_DA_ORIGEM:
            avisos.append(f"acentuação quebrada da origem: {_MOJIBAKE_DA_ORIGEM[s]}")
            info["mojibake"] = 0
        info["arquivos"] = [a.name for a in arquivos]
        info["s"] = round(time.monotonic() - t0, 1)
        por_formato[formato] = info
        if info["linhas"] == 0:
            problemas.append(f"{formato}: arquivo exportado sem linhas")
        if info["genericas"]:
            problemas.append(f"{formato}: colunas genéricas {info['genericas'][:5]}")
        if info["mojibake"]:
            problemas.append(f"{formato}: {info['mojibake']} célula(s) com acentuação quebrada, ex. {info['mojibake_exemplos']}")

    if brutos:
        # Fonte de API: cada formato contra o bruto da própria coleta.
        for formato, info in por_formato.items():
            bruto = brutos.get(formato)
            if bruto is None:
                continue
            if info["linhas"] != bruto.height:
                problemas.append(f"{formato}: {info['linhas']} linhas exportadas de {bruto.height} coletadas")
            cheios_bruto = {c: bruto.height - n for c, n in zip(bruto.columns, bruto.null_count().row(0))}
            perdas = {c: cheios_bruto[c] - (info["linhas"] - info["nulos"].get(c, info["linhas"]))
                      for c in cheios_bruto if c in info["nulos"] or c not in info["colunas"]}
            perdas = {c: n for c, n in perdas.items() if n > 0}
            if perdas:
                pior = sorted(perdas.items(), key=lambda kv: -kv[1])[:5]
                problemas.append(f"{formato} perdeu valores do bruto (coluna: valores a menos): {pior}")
    elif len(por_formato) > 1:
        linhas = {f: i["linhas"] for f, i in por_formato.items()}
        if len(set(linhas.values())) > 1:
            problemas.append(f"linhas diferem entre formatos: {linhas}")
        cols = {f: tuple(i["colunas"]) for f, i in por_formato.items()}
        ref = cols.get("csv") or next(iter(cols.values()))
        for f, c in cols.items():
            if set(c) != set(ref):
                problemas.append(
                    f"colunas diferem ({f} x csv): só em {f} {sorted(set(c) - set(ref))[:5]}, "
                    f"só no csv {sorted(set(ref) - set(c))[:5]}"
                )

    # Valor que some na tipagem: a conversão lê com tipo inferido e
    # ignore_errors, e o que não cabe no tipo vira nulo sem aviso. O CSV é a
    # referência (texto); coluna com mais nulos em outro formato perdeu dado.
    ref_nulos = {} if brutos else ((por_formato.get("csv") or {}).get("nulos") or {})
    for formato in ("parquet", "sqlite"):
        outros = (por_formato.get(formato) or {}).get("nulos") or {}
        perdas = {c: outros[c] - ref_nulos[c] for c in outros if c in ref_nulos and outros[c] > ref_nulos[c]}
        if perdas:
            pior = sorted(perdas.items(), key=lambda kv: -kv[1])[:5]
            problemas.append(f"{formato} perdeu valores na conversão (coluna: nulos a mais): {pior}")

    for info in por_formato.values():
        info.pop("nulos", None)
    vistas = next(iter(por_formato.values()))["colunas"] if por_formato else []
    esperado = (dicionario.get(s) or {}).get("fields") or []
    if vistas and esperado:
        faltam = [c for c in esperado if c not in vistas]
        sobram = [c for c in vistas if c not in esperado]
        if len(faltam) == len(esperado):
            problemas.append(f"nenhuma coluna do dicionário apareceu (esperado {esperado[:5]}, veio {vistas[:5]})")
        elif faltam:
            avisos.append(f"{len(faltam)} coluna(s) do dicionário ausentes: {faltam[:8]}")
        if sobram:
            avisos.append(f"{len(sobram)} coluna(s) fora do dicionário: {sobram[:8]}")
    elif vistas and not esperado:
        avisos.append("fonte sem campos no dicionário")
    if por_formato:
        vazias = next(iter(por_formato.values()))["vazias"]
        if vazias:
            avisos.append(f"{len(vazias)} coluna(s) inteiramente vazias na amostra: {vazias[:8]}")
    return {"problemas": problemas, "avisos": avisos, "formatos": por_formato, "colunas": vistas}


def promover(forcar: set) -> int:
    """Preenche o dicionário das fontes sem campos com as colunas vistas.

    ``forcar`` substitui também campos já existentes: é o caso do SISAGUA,
    cujo dicionário veio da antiga API do DEMAS (``regiao_geografica``)
    enquanto o Guaraci baixa os arquivos do portal (``NO_REGIAO``).
    """
    from guaraci.services.dictionary_io import atomic_write_json, render_data_dictionary_md

    vistas = json.loads(COLUNAS_VISTAS.read_text(encoding="utf-8"))
    dicionario = json.loads(DICIONARIO.read_text(encoding="utf-8"))
    hoje = date.today().isoformat()
    mudou = []
    for s, colunas in vistas.items():
        entrada = dicionario.setdefault(s, {})
        if not colunas or (entrada.get("fields") and s not in forcar):
            continue
        entrada["fields"] = colunas
        entrada["status"] = "ok"
        entrada["note"] = f"Colunas do export real (scripts/verificar_conteudo.py, {hoje})."
        mudou.append(s)
    atomic_write_json(DICIONARIO, dicionario)
    md = ROOT / "docs" / "DATA_DICTIONARY.md"
    md.write_text(render_data_dictionary_md(dicionario), encoding="utf-8")
    print(f"{len(mudou)} fonte(s) ganharam campos: {', '.join(mudou)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fontes", default="")
    parser.add_argument("--excluir", default="")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--promover", action="store_true")
    parser.add_argument("--forcar", default="", help="com --promover: fontes cujo dicionário é substituído")
    args = parser.parse_args()
    if args.promover:
        return promover({f for f in args.forcar.split(",") if f})

    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    service = DownloadService()
    fontes = [d.source for d in service.list_sources()]
    if args.fontes:
        fontes = [f for f in fontes if f in set(args.fontes.split(","))]
    if args.excluir:
        fontes = [f for f in fontes if f not in set(args.excluir.split(","))]
    dicionario = json.loads(DICIONARIO.read_text(encoding="utf-8"))
    base = Path(vr.tempfile.mkdtemp(prefix="guaraci_conteudo_"))

    def um(s: str) -> Tuple[str, Dict[str, Any]]:
        try:
            return s, confere_fonte(service, s, base, dicionario)
        except Exception as exc:  # noqa: BLE001
            return s, {"problemas": [f"verificador quebrou: {type(exc).__name__}: {str(exc)[:300]}"], "avisos": []}
        finally:
            # O resultado já está em memória; sem isto o runner do GitHub
            # (14 GB de disco) esgota antes do fim das 124 fontes.
            shutil.rmtree(base / s, ignore_errors=True)

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

    saida = ROOT / "reports" / f"verificacao_conteudo_{time.strftime('%Y%m%d_%H%M')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    vistas = {s: r.get("colunas") for s, r in resultados.items() if r.get("colunas")}
    anteriores = json.loads(COLUNAS_VISTAS.read_text(encoding="utf-8")) if COLUNAS_VISTAS.exists() else {}
    anteriores.update(vistas)
    COLUNAS_VISTAS.write_text(json.dumps(anteriores, ensure_ascii=False, indent=1), encoding="utf-8")

    falhas = {s: r for s, r in resultados.items() if r.get("problemas")}
    puladas = {s: r["pulada"] for s, r in resultados.items() if r.get("pulada")}
    com_aviso = {s: r for s, r in resultados.items() if r.get("avisos")}
    print(f"{len(fontes)} fontes, {len(falhas)} com problema, {len(com_aviso)} com aviso, "
          f"{len(puladas)} puladas, {time.monotonic() - t0:.0f}s -> {saida}")
    for s, r in sorted(falhas.items()):
        for p in r["problemas"]:
            print(f"PROBLEMA {s:<45} {p}")
    for s, motivo in sorted(puladas.items()):
        print(f"PULADA   {s:<45} {motivo}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
