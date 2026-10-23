"""Camadas de GeoServer WFS (SGB e FUNAI) exportadas como tabelas.

Mesmo desenho do TerraBrasilis (``guaraci/inpe/terrabrasilis.py``): o WFS
serve ``GetFeature`` com ``outputFormat=csv`` e paginação por ``startIndex``.
Diferenças verificadas ao vivo em 2026-10-23:

- A versão do protocolo é POR CAMADA. A FUNAI só aceita ``1.0.0`` com
  ``typeName`` (``2.0.0`` com ``typeNames`` e a rota ``/wfs`` dão 403).
  O SGB pagina com ``startIndex`` só em ``1.1.0`` e exige ``sortBy`` (sem
  chave primária, o GeoServer recusa a ordem natural); em ``1.0.0`` o
  ``startIndex`` devolve ``ServiceExceptionReport``.
- A ordem dos eixos muda com a versão: na ``1.1.0`` o WKT sai como
  ``lat lon``. ``srsName=EPSG:4326`` na ``1.1.0`` devolve ``lon lat``, igual
  ao da ``1.0.0``; por isso as camadas do SGB pedem esse parâmetro.
- A FUNAI responde 403 a ``resultType=hits`` e ao User-Agent padrão do curl;
  com o User-Agent ``guaraci/<versão>`` o ``GetFeature`` responde 200. Sem
  ``hits`` não há conferência de total na FUNAI (as camadas são pequenas e
  cabem numa página).
- Em ``hits`` as camadas de suscetibilidade do SGB anunciam exatamente
  100000, que é um teto do servidor: a paginação segue além disso (testado em
  ``startIndex=400000``). A conferência de total ignora esse número.
- A geometria sai como WKT, em texto, na coluna que o GeoServer der
  (``the_geom`` na FUNAI, ``geom`` no SGB). A coluna sintética ``FID`` do CSV
  é descartada; o resto fica com o nome publicado, e tudo é texto.
"""

from __future__ import annotations

import csv
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    decode_text,
    is_timeout_reason,
    open_response,
    request_with_retry,
)

DEFAULT_PAGE_SIZE = 2000
DEFAULT_TIMEOUT = 300
EXPORT_FORMATS = ("csv", "parquet", "sqlite")
# Teto anunciado pelo ``resultType=hits`` das camadas grandes do SGB.
HITS_CEILING = 100000
_MATCHED_RE = re.compile(r'(?:numberMatched|numberOfFeatures)="(\d+)"')

# WKT de polígono de município pode passar do limite padrão de 128 KB do csv.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

ProgressCallback = Callable[[Dict[str, object]], None]


class WfsError(ApiClientError):
    """Falha de transporte ou resposta inválida de um WFS."""


@dataclass(frozen=True)
class WfsLayer:
    """Uma camada WFS exportada como tabela."""

    name: str  # valor do parâmetro ``camadas``
    typename: str
    version: str  # "1.0.0" ou "1.1.0"
    sort_field: Optional[str] = None
    srs_name: Optional[str] = None


@dataclass(frozen=True)
class WfsFamily:
    """Uma chave do catálogo: um servidor e um conjunto de camadas."""

    key: str
    title: str
    base_url: str
    layers: Tuple[WfsLayer, ...]
    # Camadas exportadas quando ``camadas`` é omitido.
    default_layers: Tuple[str, ...]
    description: str = ""

    def layer(self, name: str) -> WfsLayer:
        for item in self.layers:
            if item.name == name:
                return item
        raise ValueError(
            f"Camada inválida para {self.key}: {name}. "
            f"Válidas: {', '.join(l.name for l in self.layers)}."
        )


_SGB_URL = "https://geoservicos.sgb.gov.br/geoserver/wfs"
_FUNAI_URL = "https://geoserver.funai.gov.br/geoserver/Funai/ows"


def _sgb(name: str) -> WfsLayer:
    return WfsLayer(
        name=name,
        typename=f"gestao-territorial:{name}",
        version="1.1.0",
        sort_field="fid",
        srs_name="EPSG:4326",
    )


def _funai(name: str, sort_field: Optional[str]) -> WfsLayer:
    return WfsLayer(name=name, typename=f"Funai:{name}", version="1.0.0", sort_field=sort_field)


WFS_FAMILIES: Dict[str, WfsFamily] = {
    family.key: family
    for family in (
        WfsFamily(
            key="sgb_risco_geologico",
            title="SGB Setorização de Risco Geológico",
            base_url=_SGB_URL,
            layers=(_sgb("risco_geologico"),),
            default_layers=("risco_geologico",),
            description=(
                "Setores de risco geológico mapeados pelo Serviço Geológico do Brasil "
                "(SGB/CPRM): município, tipologia (COBRADE), grau de risco, número de "
                "edificações, domicílios e pessoas em risco, com o polígono do setor em WKT."
            ),
        ),
        WfsFamily(
            key="sgb_suscetibilidade",
            title="SGB Cartas de Suscetibilidade",
            base_url=_SGB_URL,
            layers=(_sgb("suscet_inundacao"), _sgb("suscet_movimento_de_massa")),
            default_layers=("suscet_inundacao", "suscet_movimento_de_massa"),
            description=(
                "Cartas de suscetibilidade a inundação e a movimento de massa do Serviço "
                "Geológico do Brasil, em polígonos WKT com UF, município, processo e classe. "
                "Cada camada passa de 400 mil polígonos: use o recorte por UF."
            ),
        ),
        WfsFamily(
            key="funai_terras_indigenas",
            title="FUNAI Terras Indígenas",
            base_url=_FUNAI_URL,
            layers=(
                _funai("tis_poligonais", "gid"),
                _funai("tis_pontos", "gid"),
                _funai("tis_cr", "undadm_codigo"),
                _funai("tis_amazonia_legal_poligonais", None),
            ),
            default_layers=(
                "tis_poligonais",
                "tis_pontos",
                "tis_cr",
                "tis_amazonia_legal_poligonais",
            ),
            description=(
                "Terras indígenas da FUNAI: limites (polígonos WKT), pontos, coordenações "
                "regionais e o recorte da Amazônia Legal, com etnia, município, fase e "
                "modalidade."
            ),
        ),
        WfsFamily(
            key="funai_aldeias",
            title="FUNAI Aldeias",
            base_url=_FUNAI_URL,
            layers=(_funai("aldeias_pontos", "cod_aldeia"),),
            default_layers=("aldeias_pontos",),
            description=(
                "Aldeias indígenas cadastradas na FUNAI, com terra indígena, município, "
                "coordenação regional, situação e coordenadas."
            ),
        ),
    )
}


class WfsClient:
    """Cliente mínimo de WFS (urllib + retry compartilhado)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 4,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("?")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self._opener = opener

    def request(self, version: str, params: Dict[str, object]) -> str:
        query = {"service": "WFS", "version": version, **params}
        url = f"{self.base_url}?{urlencode(query)}"
        req = Request(url, headers={"User-Agent": f"guaraci/{__version__}"})

        def on_http(exc: HTTPError) -> WfsError:
            category, retryable = classify_http_status(exc.code)
            return WfsError(
                f"WFS falhou ({exc.code}) em {self.base_url}.",
                category=category,
                retryable=retryable,
            )

        def on_url(exc: URLError) -> WfsError:
            category = "timeout" if is_timeout_reason(exc.reason) else "network"
            return WfsError(
                f"Sem conexão com {self.base_url}: {exc.reason}", category=category, retryable=True
            )

        def on_timeout(exc: Exception) -> WfsError:
            return WfsError(
                f"{self.base_url} excedeu {self.timeout_seconds}s.",
                category="timeout",
                retryable=True,
                hint="Reduza page_size.",
            )

        def on_read(exc: Exception) -> WfsError:
            return WfsError(
                f"Conexão caiu durante a leitura: {type(exc).__name__}: {exc}",
                category="network",
                retryable=True,
            )

        def send() -> str:
            raw, _ = open_response(
                self._opener,
                req,
                timeout=self.timeout_seconds,
                on_http_error=on_http,
                on_url_error=on_url,
                on_timeout=on_timeout,
                on_read_error=on_read,
            )
            text = decode_text(raw)
            if "ExceptionReport" in text[:600]:
                # 200 com exceção OWS (ou ServiceExceptionReport da 1.0.0).
                transient = "pool" in text or "Timeout" in text
                raise WfsError(
                    "WFS devolveu ExceptionReport: " + " ".join(text.split())[:300],
                    category="upstream" if transient else "bad_request",
                    retryable=transient,
                )
            return text

        return request_with_retry(send, max_attempts=self.max_attempts)

    def count_matched(self, layer: WfsLayer, cql: Optional[str]) -> Optional[int]:
        """Total anunciado por ``resultType=hits``; ``None`` se o servidor não responder."""
        params: Dict[str, object] = {
            "request": "GetFeature",
            "typeName": layer.typename,
            "resultType": "hits",
        }
        if cql:
            params["CQL_FILTER"] = cql
        try:
            text = self.request(layer.version, params)
        except ApiClientError:
            return None
        found = _MATCHED_RE.search(text[:2000])
        return int(found.group(1)) if found else None

    def get_page(self, layer: WfsLayer, *, count: int, start_index: int, cql: Optional[str]) -> str:
        params: Dict[str, object] = {
            "request": "GetFeature",
            "typeName": layer.typename,
            "outputFormat": "csv",
            "maxFeatures": count,
            "startIndex": start_index,
        }
        if layer.sort_field:
            params["sortBy"] = layer.sort_field
        if layer.srs_name:
            params["srsName"] = layer.srs_name
        if cql:
            params["CQL_FILTER"] = cql
        return self.request(layer.version, params)


def fetch_layer(
    client: WfsClient, layer: WfsLayer, dest: Path, *, page: int, cql: Optional[str]
) -> Tuple[int, Optional[int]]:
    """Grava a camada em CSV UTF-8 e devolve ``(linhas gravadas, total anunciado)``."""
    written = 0
    start = 0
    seen: set = set()
    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        wrote_header = False
        while True:
            text = client.get_page(layer, count=page, start_index=start, cql=cql)
            reader = csv.reader(io.StringIO(text, newline=""))
            header = next(reader, None)
            if not header:
                break
            header = [h.strip() for h in header]
            drop_fid = header[0] == "FID"
            if not wrote_header:
                writer.writerow(header[1:] if drop_fid else header)
                wrote_header = True
            got = 0
            for row in reader:
                if not row:
                    continue
                got += 1
                if drop_fid:
                    fid, row = row[0], row[1:]
                    if fid in seen:
                        raise WfsError(
                            f"{layer.typename}: a feição {fid} veio em duas páginas; "
                            "a paginação deste servidor não é estável.",
                            category="bad_response",
                        )
                    seen.add(fid)
                writer.writerow(row)
            written += got
            if got < page:
                break
            start += got
    return written, client.count_matched(layer, cql)


class WfsDataSource(DataSource):
    """Exporta as camadas de uma família WFS como tabelas de atributos com geometria WKT."""

    def __init__(
        self,
        family: str,
        output_path: Optional[str] = None,
        client: Optional[WfsClient] = None,
    ) -> None:
        if family not in WFS_FAMILIES:
            raise ValueError(f"Família desconhecida: {family}")
        super().__init__(name=family, output_path=output_path)
        self.family = WFS_FAMILIES[family]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Leia o arquivo exportado com polars.scan_*.")

    def _layers(self, camadas: Optional[Sequence[str]]) -> List[WfsLayer]:
        chosen = list(camadas) if camadas else list(self.family.default_layers)
        return [self.family.layer(name) for name in dict.fromkeys(chosen)]

    def download(
        self,
        *,
        camadas: Optional[Sequence[str]] = None,
        cql_filter: Optional[str] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        page_size: int = DEFAULT_PAGE_SIZE,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = (output_format or "csv").lower()
        if fmt not in EXPORT_FORMATS:
            raise ValueError(f"output_format deve ser um de {', '.join(EXPORT_FORMATS)}.")
        page = max(1, int(page_size))
        cql = (cql_filter or "").strip() or None
        layers = self._layers(camadas)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or WfsClient(self.family.base_url, timeout_seconds=timeout)

        exported: List[str] = []
        warnings: List[str] = []
        total_rows = 0
        failed = 0
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(layers)}
            )
        single = len(self.family.layers) == 1
        for index, layer in enumerate(layers, start=1):
            stem = self.family.key if single else f"{self.family.key}_{layer.name}"
            csv_path = base_dir / f"{stem}.csv"
            try:
                rows, matched = fetch_layer(client, layer, csv_path, page=page, cql=cql)
            except ApiClientError as exc:
                failed += 1
                warnings.append(f"{stem}: {exc}")
                csv_path.unlink(missing_ok=True)
                continue
            if matched is not None and matched != rows and matched != HITS_CEILING:
                warnings.append(
                    f"{stem}: gravadas {rows} linhas, mas o servidor anunciou {matched}; "
                    "a paginação pode ter perdido ou repetido feições."
                )
            if rows == 0:
                csv_path.unlink(missing_ok=True)
                warnings.append(f"{stem}: nenhuma linha para o recorte pedido; arquivo não gerado.")
                continue
            total_rows += rows
            try:
                dest = self._convert(csv_path, base_dir, stem, fmt, keep_raw)
            except (ValueError, OSError, pl.exceptions.PolarsError) as exc:
                failed += 1
                warnings.append(f"{stem}: falha ao converter para {fmt}: {exc}")
                if not keep_raw:
                    csv_path.unlink(missing_ok=True)
                continue
            exported.append(str(dest))
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "documents_total": len(layers),
                        "document_index": index,
                        "file_path": str(dest),
                    }
                )
        return {
            "documents_found": len(layers),
            "downloaded_count": len(exported),
            "skipped_count": 0,
            "failed_count": failed,
            "rows": total_rows,
            "output_dir": str(base_dir),
            "source_url": self.family.base_url,
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " | ".join(warnings) or None,
        }

    @staticmethod
    def _convert(csv_path: Path, base_dir: Path, key: str, fmt: str, keep_raw: bool) -> Path:
        if fmt == "csv":
            return csv_path
        frame = pl.scan_csv(csv_path, infer_schema=False)
        if fmt == "parquet":
            dest = base_dir / f"{key}.parquet"
            frame.sink_parquet(dest)
        else:
            from guaraci.datasus.frames import write_sqlite

            dest = write_sqlite(frame, db_path=base_dir / f"{key}.sqlite", table=key)
            if dest is None:
                raise ValueError(f"{key} não tem linhas para exportar em sqlite.")
        if not keep_raw:
            csv_path.unlink(missing_ok=True)
        return Path(dest)
