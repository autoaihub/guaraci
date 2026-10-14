"""INPE TerraBrasilis (GeoServer WFS): DETER Amazonia, DETER Cerrado e PRODES.

Cada camada vira uma tabela de atributos, SEM geometria. O WFS 2.0.0 de
``terrabrasilis.dpi.inpe.br/geoserver/ows`` serve ``GetFeature`` com
``outputFormat=csv``, paginacao por ``count``/``startIndex`` e filtro por
``CQL_FILTER``. A lista de atributos vem do ``DescribeFeatureType`` da propria
camada (tudo que nao for tipo ``gml:*``), e entra em ``propertyName``; assim a
geometria nunca trafega e os nomes de coluna sao os publicados pelo INPE.

Notas verificadas ao vivo (13/10/2026):

- ``gid`` do DETER e texto (``1011_hist``), nao inteiro, e NAO e unico no
  DETER Cerrado; a paginacao ordena por ele mais ``view_date``, ``classname``
  e ``path_row`` (presentes nas duas camadas DETER) como desempate, e o total
  gravado e conferido contra ``numberMatched`` (``resultType=hits``).
- O CSV do GeoServer traz uma coluna ``FID`` sintetica, descartada aqui.
- Recorte anual: ``view_date`` (DETER, tipo date) ou ``year`` (PRODES, inteiro).
- O servidor responde ``200`` com ``ExceptionReport`` quando o pool de conexoes
  esgota; isso e tratado como erro transitorio e repetido.
- Camadas com geom obrigatorio (ex.: PRODES Pampa) enviam a geometria mesmo fora de
  ``propertyName``; ela e descartada ao gravar (so custa banda).
- Tudo sai como texto (``infer_schema=False`` nas conversoes).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
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

BASE_URL = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
DEFAULT_PAGE_SIZE = 5000
DEFAULT_TIMEOUT = 120
EXPORT_FORMATS = ("csv", "parquet", "sqlite")
BIOMAS = (
    "legal_amz",
    "amazon",
    "cerrado",
    "caatinga",
    "mata_atlantica",
    "pampa",
    "pantanal",
)
_MATCHED_RE = re.compile(r'numberMatched="(\d+)"')
_ELEMENT_RE = re.compile(r"<xsd:element\b[^>]*>")
_ATTR_RE = re.compile(r'\b(name|type)="([^"]*)"')

ProgressCallback = Callable[[Dict[str, object]], None]


class TerraBrasilisError(ApiClientError):
    """Falha de transporte ou resposta invalida do WFS do TerraBrasilis."""


@dataclass(frozen=True)
class LayerSpec:
    """Uma camada WFS exportada como tabela."""

    key: str
    typename: str
    filter_field: str
    filter_kind: str  # "date" (view_date) ou "year" (inteiro)
    sort_field: str


# Chave de ordenacao do DETER: ``gid`` repete no Cerrado, entao entram atributos
# que existem nas duas camadas (DescribeFeatureType de 13/10/2026) como desempate.
_DETER_SORT = "gid,view_date,classname,path_row"

DETER_LAYERS: Dict[str, LayerSpec] = {
    "inpe_deter_amazonia": LayerSpec(
        "inpe_deter_amazonia", "deter-amz:deter_amz", "view_date", "date", _DETER_SORT
    ),
    "inpe_deter_cerrado": LayerSpec(
        "inpe_deter_cerrado", "deter-cerrado-nb:deter_cerrado", "view_date", "date", _DETER_SORT
    ),
}

_PRODES_TYPENAMES: Dict[str, str] = {
    "legal_amz": "prodes-legal-amz:yearly_deforestation",
    "amazon": "prodes-amazon-nb:yearly_deforestation_biome",
    "cerrado": "prodes-cerrado-nb:yearly_deforestation",
    "caatinga": "prodes-caatinga-nb:yearly_deforestation",
    "mata_atlantica": "prodes-mata-atlantica-nb:yearly_deforestation",
    "pampa": "prodes-pampa-nb:yearly_deforestation",
    "pantanal": "prodes-pantanal-nb:yearly_deforestation",
}
PRODES_LAYERS: Dict[str, LayerSpec] = {
    bioma: LayerSpec(f"inpe_prodes_{bioma}", typename, "year", "year", "fid")
    for bioma, typename in _PRODES_TYPENAMES.items()
}

# Pisos de ano verificados ao vivo (primeira feicao por data/ano).
MIN_YEAR = {"inpe_deter_amazonia": 2016, "inpe_deter_cerrado": 2018, "inpe_prodes": 2002}


def build_cql(spec: LayerSpec, start_year: Optional[int], end_year: Optional[int]) -> Optional[str]:
    """Monta o ``CQL_FILTER`` do recorte anual (fim inclusivo)."""
    if start_year is None and end_year is None:
        return None
    parts: List[str] = []
    if spec.filter_kind == "date":
        if start_year is not None:
            parts.append(f"{spec.filter_field} >= '{int(start_year):04d}-01-01'")
        if end_year is not None:
            parts.append(f"{spec.filter_field} < '{int(end_year) + 1:04d}-01-01'")
    else:
        if start_year is not None:
            parts.append(f"{spec.filter_field} >= {int(start_year)}")
        if end_year is not None:
            parts.append(f"{spec.filter_field} <= {int(end_year)}")
    return " AND ".join(parts)


def parse_attributes(xsd: str) -> List[str]:
    """Nomes dos atributos nao geometricos de um ``DescribeFeatureType``."""
    names: List[str] = []
    for element in _ELEMENT_RE.findall(xsd):
        if "substitutionGroup" in element:
            continue  # elemento raiz da camada, nao atributo
        attrs = dict(_ATTR_RE.findall(element))
        name, type_ = attrs.get("name"), attrs.get("type", "")
        if not name or type_.startswith("gml:") or not type_:
            continue
        names.append(name)
    return names


class TerraBrasilisClient:
    """Cliente minimo do WFS (urllib + retry compartilhado)."""

    def __init__(self, base_url: Optional[str] = None, timeout_seconds: int = DEFAULT_TIMEOUT,
                 max_attempts: int = 4, opener: Callable[..., object] = urlopen) -> None:
        self.base_url = (base_url or BASE_URL).rstrip("?")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self._opener = opener

    def request(self, params: Dict[str, object]) -> str:
        query = {"service": "WFS", "version": "2.0.0", **params}
        url = f"{self.base_url}?{urlencode(query)}"
        req = Request(url, headers={"User-Agent": f"guaraci/{__version__}"})

        def on_http(exc: HTTPError) -> TerraBrasilisError:
            category, retryable = classify_http_status(exc.code)
            return TerraBrasilisError(
                f"TerraBrasilis WFS falhou ({exc.code}).",
                category=category, retryable=retryable,
            )

        def on_url(exc: URLError) -> TerraBrasilisError:
            category = "timeout" if is_timeout_reason(exc.reason) else "network"
            return TerraBrasilisError(
                f"Sem conexao com o TerraBrasilis: {exc.reason}",
                category=category, retryable=True,
            )

        def on_timeout(exc: Exception) -> TerraBrasilisError:
            return TerraBrasilisError(
                f"TerraBrasilis excedeu {self.timeout_seconds}s.",
                category="timeout", retryable=True,
                hint="Reduza page_size ou o intervalo de anos.",
            )

        def on_read(exc: Exception) -> TerraBrasilisError:
            return TerraBrasilisError(
                f"Conexao com o TerraBrasilis caiu durante a leitura: "
                f"{type(exc).__name__}: {exc}",
                category="network", retryable=True,
            )

        def send() -> str:
            raw, _ = open_response(
                self._opener, req, timeout=self.timeout_seconds,
                on_http_error=on_http, on_url_error=on_url, on_timeout=on_timeout,
                on_read_error=on_read,
            )
            text = decode_text(raw)
            if "ExceptionReport" in text[:600]:
                # 200 com excecao OWS: pool esgotado ou filtro invalido.
                transient = "pool" in text or "Timeout" in text
                raise TerraBrasilisError(
                    "WFS devolveu ExceptionReport: " + " ".join(text.split())[:300],
                    category="upstream" if transient else "bad_request",
                    retryable=transient,
                )
            return text

        return request_with_retry(send, max_attempts=self.max_attempts)

    def describe(self, typename: str) -> List[str]:
        xsd = self.request({"request": "DescribeFeatureType", "typeNames": typename})
        names = parse_attributes(xsd)
        if not names:
            raise TerraBrasilisError(
                f"DescribeFeatureType sem atributos para {typename}.", category="bad_response"
            )
        return names

    def count_matched(self, typename: str, cql: Optional[str]) -> Optional[int]:
        """Total que o servidor diz casar com o filtro (``numberMatched``).

        Serve so para conferir o que foi gravado; qualquer falha devolve
        ``None`` e a conferencia e pulada.
        """
        params: Dict[str, object] = {
            "request": "GetFeature", "typeNames": typename, "resultType": "hits",
        }
        if cql:
            params["CQL_FILTER"] = cql
        try:
            text = self.request(params)
        except ApiClientError:
            return None
        found = _MATCHED_RE.search(text[:2000])
        return int(found.group(1)) if found else None

    def get_page(self, typename: str, properties: Sequence[str], *, count: int,
                 start_index: int, sort_field: str, cql: Optional[str]) -> str:
        params: Dict[str, object] = {
            "request": "GetFeature",
            "typeNames": typename,
            "outputFormat": "csv",
            "propertyName": ",".join(properties),
            "sortBy": sort_field,
            "count": count,
            "startIndex": start_index,
        }
        if cql:
            params["CQL_FILTER"] = cql
        return self.request(params)


class TerraBrasilisDataSource(DataSource):
    """Exporta uma ou mais camadas do TerraBrasilis como tabelas de atributos."""

    def __init__(self, family: str, output_path: Optional[str] = None,
                 client: Optional[TerraBrasilisClient] = None) -> None:
        if family not in ("inpe_deter_amazonia", "inpe_deter_cerrado", "inpe_prodes"):
            raise ValueError(f"Familia desconhecida: {family}")
        super().__init__(name=family, output_path=output_path)
        self.family = family
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Leia o arquivo exportado com polars.scan_*.")

    def _layers(self, biomas: Optional[Sequence[str]]) -> List[LayerSpec]:
        if self.family != "inpe_prodes":
            return [DETER_LAYERS[self.family]]
        chosen = list(biomas) if biomas else list(BIOMAS)
        invalid = [b for b in chosen if b not in PRODES_LAYERS]
        if invalid:
            raise ValueError(f"Bioma(s) invalido(s): {', '.join(invalid)}. Validos: {', '.join(BIOMAS)}")
        return [PRODES_LAYERS[b] for b in dict.fromkeys(chosen)]

    def download(
        self,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        biomas: Optional[Sequence[str]] = None,
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
        if start_year is not None and end_year is not None and int(end_year) < int(start_year):
            raise ValueError("end_year nao pode ser menor que start_year.")
        page = max(1, int(page_size))
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or TerraBrasilisClient(timeout_seconds=timeout)
        layers = self._layers(biomas)

        exported: List[str] = []
        total_rows = 0
        failed = 0
        warnings: List[str] = []
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name,
                               "documents_total": len(layers)})
        for index, spec in enumerate(layers, start=1):
            csv_path = base_dir / f"{spec.key}.csv"
            try:
                rows, matched = self._fetch_layer(
                    client, spec, csv_path, start_year, end_year, page
                )
            except ApiClientError as exc:
                failed += 1
                warnings.append(f"{spec.key}: {exc}")
                csv_path.unlink(missing_ok=True)
                continue
            if matched is not None and matched != rows:
                warnings.append(
                    f"{spec.key}: gravadas {rows} linhas, mas o servidor anunciou "
                    f"{matched} (numberMatched); a paginacao pode ter perdido ou "
                    "repetido feicoes."
                )
            if rows == 0:
                # So cabecalho: nao e um artefato util e nao conta como exportado.
                csv_path.unlink(missing_ok=True)
                warnings.append(
                    f"{spec.key}: nenhuma linha para o recorte pedido; arquivo nao gerado."
                )
                continue
            total_rows += rows
            try:
                dest = self._convert(csv_path, base_dir, spec.key, fmt, keep_raw)
            except (ValueError, OSError, pl.exceptions.PolarsError) as exc:
                failed += 1
                warnings.append(f"{spec.key}: falha ao converter para {fmt}: {exc}")
                if not keep_raw:
                    csv_path.unlink(missing_ok=True)
                continue
            exported.append(str(dest))
            if progress_callback is not None:
                progress_callback({"event": "file_completed", "source": self.name,
                                   "documents_total": len(layers), "document_index": index,
                                   "file_path": str(dest)})
        return {
            "documents_found": len(layers),
            "downloaded_count": len(exported),
            "skipped_count": 0,
            "failed_count": failed,
            "rows": total_rows,
            "output_dir": str(base_dir),
            "source_url": BASE_URL,
            "output_format": fmt,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " | ".join(warnings) or None,
        }

    @staticmethod
    def _fetch_layer(client: TerraBrasilisClient, spec: LayerSpec, dest: Path,
                     start_year: Optional[int], end_year: Optional[int],
                     page: int) -> "tuple[int, Optional[int]]":
        """Grava a camada em CSV e devolve ``(linhas gravadas, numberMatched)``."""
        properties = client.describe(spec.typename)
        cql = build_cql(spec, start_year, end_year)
        written = 0
        start = 0
        with dest.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(properties)
            while True:
                text = client.get_page(spec.typename, properties, count=page,
                                       start_index=start, sort_field=spec.sort_field, cql=cql)
                reader = csv.reader(io.StringIO(text, newline=""))
                header = next(reader, None)
                if not header:
                    break
                header = [h.strip() for h in header]
                # O GeoServer antecede a coluna sintetica FID; as demais vem pelo nome.
                positions = [header.index(p) if p in header else None for p in properties]
                got = 0
                for row in reader:
                    if not row:
                        continue
                    got += 1
                    writer.writerow(
                        [row[i] if i is not None and i < len(row) else "" for i in positions]
                    )
                written += got
                if got < page:
                    break
                start += got
        return written, client.count_matched(spec.typename, cql)

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
                raise ValueError(f"{key} nao tem linhas para exportar em sqlite.")
        if not keep_raw:
            csv_path.unlink(missing_ok=True)
        return Path(dest)


def current_year() -> int:
    return datetime.now().year
