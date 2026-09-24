"""Datasources da CETESB: índice horário por poluente e cadastro de estações.

Duas fontes, porque respondem a perguntas diferentes:

- :class:`CetesbQualarDataSource` entrega a série: uma linha por estação, por
  poluente e por hora, nas últimas 48 horas;
- :class:`CetesbEstacoesDataSource` entrega o cadastro: uma linha por estação,
  com endereço, município, coordenada e o índice corrente.

O cadastro não é acessório. As camadas de poluente identificam a estação só
pelo nome (``STATNM``) e não dizem em que município ela fica, e sem município
não há como ligar poluição a dado de saúde, que no Guaraci é sempre indexado
por código ou nome de município. Por isso a série já sai com o município
anexado: a junção é feita aqui, uma vez, em vez de virar tarefa de quem
consome.

Sobre o que estes números são
-----------------------------
São ÍNDICE de qualidade do ar, não concentração em µg/m³. A distinção está
demonstrada no docstring de :mod:`guaraci.cetesb.client`. O índice é uma
transformação por faixas, definida pela Resolução CONAMA 506/2024, e não pode
ser usado como se fosse concentração em modelo dose-resposta.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import polars as pl
from loguru import logger

from guaraci.cetesb.client import (
    HOURS_PER_WINDOW,
    POLLUTANT_LAYERS,
    STATION_LAYER,
    CetesbClientError,
    CetesbQualarClient,
    epoch_ms_to_local_naive,
)
from guaraci.core.datasource import DataSource
from guaraci.datasus.frames import write_sqlite

ProgressCallback = Callable[[Dict[str, object]], None]

SERIES_COLUMNS: Tuple[str, ...] = (
    "estacao",
    "municipio",
    "latitude",
    "longitude",
    "poluente",
    "datahora",
    "indice",
)

STATION_COLUMNS: Tuple[str, ...] = (
    "id",
    "estacao",
    "municipio",
    "endereco",
    "tipo_rede",
    "situacao_rede",
    "latitude",
    "longitude",
    "datahora",
    "indice",
    "qualidade",
    "poluente_critico",
    "mensagem_saude",
    "efeito",
)

_EXPORT_FORMATS = {"csv", "parquet", "sqlite"}


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized not in _EXPORT_FORMATS:
        allowed = ", ".join(sorted(_EXPORT_FORMATS))
        raise ValueError(f"Unsupported CETESB export format '{value}'. Allowed: {allowed}")
    return normalized


def _normalize_names(values: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """Normaliza um filtro de texto livre para comparação sem caixa nem espaço."""
    if not values:
        return ()
    cleaned = []
    for item in values:
        text = str(item).strip()
        if text:
            cleaned.append(text.casefold())
    return tuple(dict.fromkeys(cleaned))


class _CetesbBase(DataSource):
    """Infraestrutura comum às duas fontes CETESB."""

    DEFAULT_TIMEOUT = CetesbQualarClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        name: str,
        output_path: Optional[str] = None,
        *,
        client: Optional[CetesbQualarClient] = None,
    ) -> None:
        super().__init__(name=name, output_path=output_path)
        self._client = client
        self._dataframe: pl.DataFrame = pl.DataFrame()

    def load_dataframe(self) -> pl.DataFrame:
        """Tabela materializada pelo download mais recente."""
        return self._dataframe

    def _resolve_client(
        self, *, api_base_url: Optional[str], timeout: int
    ) -> CetesbQualarClient:
        if self._client is not None:
            return self._client
        return CetesbQualarClient(base_url=api_base_url, timeout_seconds=timeout)

    def export(self, df: pl.DataFrame, format: str, name: str) -> Path:  # noqa: A003
        normalized = _normalize_format(format)
        if normalized is None:
            raise ValueError("CETESB export format cannot be empty.")
        if normalized == "csv":
            path = self.output_path / f"{name}.csv"
            df.write_csv(path)
            return path
        if normalized == "parquet":
            path = self.output_path / f"{name}.parquet"
            df.write_parquet(path)
            return path
        path = self.output_path / f"{name}.sqlite"
        written = write_sqlite(df, db_path=path, table=f"{self.name}_records")
        if written is None:
            raise ValueError("CETESB export to sqlite has no rows to write.")
        return written

    def _fetch_station_registry(
        self, client: CetesbQualarClient
    ) -> Dict[str, Dict[str, object]]:
        """Cadastro indexado pelo nome da estação, que é a chave das camadas."""
        features = client.query_layer(
            STATION_LAYER,
            out_fields="*",
            return_geometry=True,
        )
        registry: Dict[str, Dict[str, object]] = {}
        for feature in features:
            attributes = feature.get("attributes") or {}
            name = attributes.get("Nome")
            if not name:
                continue
            geometry = feature.get("geometry") or {}
            registry[str(name)] = {
                "id": attributes.get("ID"),
                "municipio": attributes.get("Municipio"),
                "endereco": attributes.get("Endereco"),
                "tipo_rede": attributes.get("Tipo_Rede"),
                "situacao_rede": attributes.get("Situacao_Rede"),
                "latitude": geometry.get("y"),
                "longitude": geometry.get("x"),
                "datahora": attributes.get("DATA"),
                "indice": attributes.get("Indice"),
                "qualidade": attributes.get("Qualidade"),
                "poluente_critico": attributes.get("POLUENTE"),
                "mensagem_saude": attributes.get("MsgSaude"),
                "efeito": attributes.get("Efeito"),
            }
        return registry

    def _write_manifest(self, *, base_dir: Path, payload: Mapping[str, object]) -> Path:
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"{self.name}_manifest.json"
        path.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path


class CetesbQualarDataSource(_CetesbBase):
    """Índice horário de qualidade do ar da CETESB, janela móvel de 48 horas."""

    POLLUTANTS: Tuple[str, ...] = tuple(POLLUTANT_LAYERS)

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[CetesbQualarClient] = None,
    ) -> None:
        super().__init__(name="cetesb_qualar", output_path=output_path, client=client)

    def download(
        self,
        *,
        pollutants: Optional[Sequence[str]] = None,
        stations: Optional[Sequence[str]] = None,
        municipios: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout: int = _CetesbBase.DEFAULT_TIMEOUT,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        selected = self._normalize_pollutants(pollutants)
        station_filter = _normalize_names(stations)
        municipio_filter = _normalize_names(municipios)

        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": len(selected),
                }
            )

        warnings: List[str] = []
        try:
            registry = self._fetch_station_registry(client)
        except CetesbClientError as exc:
            # O cadastro é enriquecimento, não a série. Sem ele a coleta segue
            # e o município fica nulo, o que é melhor que perder o download
            # inteiro por causa de uma camada acessória.
            registry = {}
            warnings.append(
                f"Cadastro de estações (camada {STATION_LAYER}) indisponível: {exc}. "
                "As colunas municipio/latitude/longitude ficarão nulas."
            )

        records: List[Dict[str, object]] = []
        raw_payloads: Dict[str, object] = {}
        failed: List[str] = []
        collected: List[str] = []

        for index, pollutant in enumerate(selected, start=1):
            layer = POLLUTANT_LAYERS[pollutant]
            try:
                features = client.query_layer(layer, out_fields="*", return_geometry=True)
            except CetesbClientError as exc:
                failed.append(f"{pollutant}: {exc}")
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "file_failed",
                            "source": self.name,
                            "document_index": index,
                            "documents_total": len(selected),
                            "document": pollutant,
                            "error": str(exc),
                        }
                    )
                continue

            if keep_raw:
                raw_payloads[pollutant] = features
            records.extend(self._features_to_records(features, pollutant, registry))
            collected.append(pollutant)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "document_index": index,
                        "documents_total": len(selected),
                        "document": pollutant,
                    }
                )

        dataframe = self._records_to_dataframe(records)
        dataframe = self._apply_filters(dataframe, station_filter, municipio_filter)
        self._dataframe = dataframe

        if dataframe.is_empty() and not failed:
            warnings.append(
                "Nenhuma medida retornada. A CETESB publica apenas as últimas 48 "
                "horas, e estações fora de operação devolvem valores nulos."
            )

        if keep_raw and raw_payloads:
            raw_path = base_dir / "raw" / "cetesb_qualar_raw.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps(raw_payloads, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        requested_format = _normalize_format(output_format)
        exported: List[str] = []
        if requested_format and not dataframe.is_empty():
            try:
                exported.append(
                    str(self.export(dataframe, format=requested_format, name=self.name))
                )
            except Exception as exc:  # noqa: BLE001 - reportado como warning
                warnings.append(f"CETESB export failed after download: {exc}")
        elif requested_format:
            warnings.append("No data artifact generated: parsed dataframe is empty.")
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        window = self._window_bounds(dataframe)
        payload: Dict[str, object] = {
            "documents_found": len(selected),
            "downloaded_count": len(collected),
            "skipped_count": 0,
            "failed_count": len(failed),
            "output_dir": str(base_dir),
            "pollutants": list(collected),
            "record_count": dataframe.height,
            "station_count": self._distinct_count(dataframe, "estacao"),
            "window_start": window[0],
            "window_end": window[1],
            "measure": "indice",
            "output_format": requested_format,
            "exported_files": exported,
            "keep_raw": keep_raw,
        }
        payload["manifest_path"] = str(
            self._write_manifest(
                base_dir=base_dir,
                payload={**payload, "failed": failed, "warnings": warnings},
            )
        )
        if failed:
            payload["failed"] = failed
        combined = " ".join(warnings).strip()
        if combined:
            payload["export_warning"] = combined
        if progress_callback is not None:
            progress_callback({"event": "download_complete", **payload})
        return payload

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------
    def _normalize_pollutants(self, values: Optional[Sequence[str]]) -> Tuple[str, ...]:
        """Resolve o filtro de poluentes, aceitando as grafias usuais.

        ``MP2.5`` é como a CETESB nomeia a camada, mas ``MP25`` e ``PM2.5``
        aparecem em qualquer planilha do assunto e não custam nada aceitar.
        """
        if not values:
            return self.POLLUTANTS
        aliases = {
            "MP25": "MP2.5",
            "MP2_5": "MP2.5",
            "PM2.5": "MP2.5",
            "PM25": "MP2.5",
            "PM10": "MP10",
        }
        resolved: List[str] = []
        unknown: List[str] = []
        for item in values:
            token = str(item).strip().upper()
            if not token:
                continue
            token = aliases.get(token, token)
            if token in POLLUTANT_LAYERS:
                resolved.append(token)
            else:
                unknown.append(str(item))
        if unknown:
            allowed = ", ".join(POLLUTANT_LAYERS)
            raise ValueError(
                f"Unknown CETESB pollutant(s): {', '.join(unknown)}. Allowed: {allowed}"
            )
        if not resolved:
            return self.POLLUTANTS
        return tuple(dict.fromkeys(resolved))

    @staticmethod
    def _features_to_records(
        features: Sequence[Mapping[str, Any]],
        pollutant: str,
        registry: Mapping[str, Mapping[str, object]],
    ) -> List[Dict[str, object]]:
        """Desdobra ``M1..M48``/``TM1..TM48`` em uma linha por hora.

        Horas sem leitura vêm com valor nulo e são descartadas: manter 48
        linhas por estação com o grosso em branco infla a tabela e não informa
        nada que a ausência da linha já não diga.
        """
        records: List[Dict[str, object]] = []
        for feature in features:
            attributes = feature.get("attributes") or {}
            station = attributes.get("STATNM")
            if not station:
                continue
            station_name = str(station)
            meta = registry.get(station_name, {})
            geometry = feature.get("geometry") or {}
            latitude = meta.get("latitude", geometry.get("y"))
            longitude = meta.get("longitude", geometry.get("x"))
            for slot in range(1, HOURS_PER_WINDOW + 1):
                value = attributes.get(f"M{slot}")
                if value is None:
                    continue
                moment = epoch_ms_to_local_naive(attributes.get(f"TM{slot}"))
                if moment is None:
                    continue
                records.append(
                    {
                        "estacao": station_name,
                        "municipio": meta.get("municipio"),
                        "latitude": latitude,
                        "longitude": longitude,
                        "poluente": pollutant,
                        "datahora": moment,
                        "indice": float(value),
                    }
                )
        return records

    @staticmethod
    def _records_to_dataframe(records: Sequence[Mapping[str, object]]) -> pl.DataFrame:
        if not records:
            return pl.DataFrame(
                schema={
                    "estacao": pl.Utf8,
                    "municipio": pl.Utf8,
                    "latitude": pl.Float64,
                    "longitude": pl.Float64,
                    "poluente": pl.Utf8,
                    "datahora": pl.Datetime,
                    "indice": pl.Float64,
                }
            )
        frame = pl.DataFrame(list(records))
        return frame.select(list(SERIES_COLUMNS)).sort(
            ["poluente", "estacao", "datahora"]
        )

    @staticmethod
    def _apply_filters(
        frame: pl.DataFrame,
        stations: Tuple[str, ...],
        municipios: Tuple[str, ...],
    ) -> pl.DataFrame:
        if frame.is_empty():
            return frame
        if stations:
            frame = frame.filter(
                pl.col("estacao").str.to_lowercase().is_in(list(stations))
            )
        if municipios:
            frame = frame.filter(
                pl.col("municipio").str.to_lowercase().is_in(list(municipios))
            )
        return frame

    @staticmethod
    def _distinct_count(frame: pl.DataFrame, column: str) -> int:
        if frame.is_empty() or column not in frame.columns:
            return 0
        return int(frame.select(pl.col(column).n_unique()).item())

    @staticmethod
    def _window_bounds(frame: pl.DataFrame) -> Tuple[Optional[str], Optional[str]]:
        if frame.is_empty() or "datahora" not in frame.columns:
            return (None, None)
        low = frame.select(pl.col("datahora").min()).item()
        high = frame.select(pl.col("datahora").max()).item()
        return (str(low) if low else None, str(high) if high else None)


class CetesbEstacoesDataSource(_CetesbBase):
    """Cadastro das estações de monitoramento da CETESB, com índice corrente."""

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[CetesbQualarClient] = None,
    ) -> None:
        super().__init__(name="cetesb_estacoes", output_path=output_path, client=client)

    def download(
        self,
        *,
        municipios: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout: int = _CetesbBase.DEFAULT_TIMEOUT,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        municipio_filter = _normalize_names(municipios)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": 1}
            )

        warnings: List[str] = []
        failed: List[str] = []
        registry: Dict[str, Dict[str, object]] = {}
        try:
            registry = self._fetch_station_registry(client)
        except CetesbClientError as exc:
            failed.append(str(exc))
            logger.warning(f"CETESB station registry failed: {exc}")

        records = [
            {
                "id": meta.get("id"),
                "estacao": name,
                "municipio": meta.get("municipio"),
                "endereco": meta.get("endereco"),
                "tipo_rede": meta.get("tipo_rede"),
                "situacao_rede": meta.get("situacao_rede"),
                "latitude": meta.get("latitude"),
                "longitude": meta.get("longitude"),
                "datahora": meta.get("datahora"),
                "indice": meta.get("indice"),
                "qualidade": meta.get("qualidade"),
                "poluente_critico": meta.get("poluente_critico"),
                "mensagem_saude": meta.get("mensagem_saude"),
                "efeito": meta.get("efeito"),
            }
            for name, meta in registry.items()
        ]

        frame = (
            pl.DataFrame(records).select(list(STATION_COLUMNS)).sort("estacao")
            if records
            else pl.DataFrame(schema={column: pl.Utf8 for column in STATION_COLUMNS})
        )
        if municipio_filter and not frame.is_empty():
            frame = frame.filter(
                pl.col("municipio").str.to_lowercase().is_in(list(municipio_filter))
            )
        self._dataframe = frame

        if keep_raw and records:
            raw_path = base_dir / "raw" / "cetesb_estacoes_raw.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        requested_format = _normalize_format(output_format)
        exported: List[str] = []
        if requested_format and not frame.is_empty():
            try:
                exported.append(
                    str(self.export(frame, format=requested_format, name=self.name))
                )
            except Exception as exc:  # noqa: BLE001 - reportado como warning
                warnings.append(f"CETESB export failed after download: {exc}")
        elif requested_format:
            warnings.append("No data artifact generated: parsed dataframe is empty.")
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is "
                "empty). Set output_format or enable keep_raw."
            )

        payload: Dict[str, object] = {
            "documents_found": 1,
            "downloaded_count": 0 if failed else 1,
            "skipped_count": 0,
            "failed_count": len(failed),
            "output_dir": str(base_dir),
            "record_count": frame.height,
            "output_format": requested_format,
            "exported_files": exported,
            "keep_raw": keep_raw,
        }
        payload["manifest_path"] = str(
            self._write_manifest(
                base_dir=base_dir,
                payload={**payload, "failed": failed, "warnings": warnings},
            )
        )
        if failed:
            payload["failed"] = failed
        combined = " ".join(warnings).strip()
        if combined:
            payload["export_warning"] = combined
        if progress_callback is not None:
            progress_callback({"event": "download_complete", **payload})
        return payload
