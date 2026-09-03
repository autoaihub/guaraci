"""Shared base for IBGE SIDRA aggregate datasources.

Every SIDRA aggregate (table + variable, optionally split by classifications
such as sex and age) shares the same shape: request one year at a time, flatten
the ``resultados -> series -> serie`` nesting into tidy rows, and export/manifest
the result. That common tail lives in :class:`SidraAggregateSource`; each
concrete source is a thin subclass that pins the table/variable and (when it has
classifications) builds the SIDRA ``classificacao`` filter.

Output is one row per (locality, year[, classification categories]):
``nivel, localidade_id, localidade_nome, ano, [<classif> ...], variavel_id,
unidade, valor``. Missing markers ("-", "..") become null; a year with no data
is skipped with a warning, not a failure.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.datasus.frames import write_sqlite
from guaraci.ibge.client import IbgeClientError, IbgeSidraClient

_EXPORT_FORMATS = {"csv", "parquet", "sqlite"}


class SidraAggregateSource(DataSource):
    """Base for a single SIDRA aggregate table/variable, swept year by year."""

    TABLE: str = ""
    VARIABLE: str = ""
    DEFAULT_TIMEOUT = 120
    DEFAULT_LEVEL = "municipio"
    LEVELS: Dict[str, str] = {
        "municipio": "N6",
        "uf": "N3",
        "estado": "N3",
        "regiao": "N2",
        "brasil": "N1",
        "pais": "N1",
        "n6": "N6",
        "n3": "N3",
        "n2": "N2",
        "n1": "N1",
    }
    _MISSING = {"-", "..", "...", "x", "X", ""}

    def __init__(
        self,
        name: str,
        output_path: Optional[str] = None,
        *,
        client: Optional[IbgeSidraClient] = None,
    ) -> None:
        super().__init__(name=name, output_path=output_path)
        self._client = client
        self._records: List[Dict[str, object]] = []

    # -- shared collection ----------------------------------------------------
    def _collect(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str,
        classificacao: Optional[str] = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        y0 = self._parse_year(start_year, "start_year")
        y1 = self._parse_year(end_year, "end_year")
        if y0 > y1:
            raise ValueError("Parameter 'start_year' cannot be after 'end_year'.")
        nivel = self._resolve_level(level)
        localities = f"{nivel}[all]"
        client = self._resolve_client(api_base_url=api_base_url, timeout=timeout)

        years = list(range(y0, y1 + 1))
        total = len(years)
        records: List[Dict[str, object]] = []
        raw_by_year: Dict[str, Any] = {}
        warnings: List[str] = []
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": total}
            )

        for index, year in enumerate(years, start=1):
            try:
                payload = client.aggregate(
                    table=self.TABLE,
                    variable=self.VARIABLE,
                    period=str(year),
                    localities=localities,
                    classificacao=classificacao,
                )
            except IbgeClientError as exc:
                warnings.append(f"IBGE year {year} skipped: {exc}")
                payload = None
            if payload:
                records.extend(self._parse(payload, nivel))
                if keep_raw:
                    raw_by_year[str(year)] = payload
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "documents_total": total,
                        "document_index": index,
                        "files_completed": index,
                        "file_path": f"{self.name}_{year}",
                    }
                )

        self._records = records
        stem = self._artifact_stem(nivel, y0, y1)
        raw_path = self._write_raw(stem, raw_by_year) if (keep_raw and raw_by_year) else None

        requested_format = self._normalize_format(output_format)
        exported: List[str] = []
        if not records:
            warnings.append("IBGE returned no rows for the requested years/level.")
        if requested_format and records:
            try:
                exported.append(str(self.export(self._to_df(records), format=requested_format, name=stem)))
            except Exception as exc:  # noqa: BLE001 - reported as a warning
                warnings.append(f"IBGE export failed after download. Error: {exc}")
        elif not requested_format and not keep_raw:
            warnings.append(
                "No artifact generated (output_format empty and keep_raw=false). "
                "Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            nivel=nivel,
            start_year=y0,
            end_year=y1,
            classificacao=classificacao,
            record_count=len(records),
            raw_path=raw_path,
            keep_raw=keep_raw,
            output_format=requested_format,
            exported=exported,
            api_base_url=client.base_url,
            warnings=warnings,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": self.name,
                    "documents_total": total,
                    "downloaded_count": len(records),
                    "failed_count": 0,
                    "skipped_count": 0,
                    "output_dir": str(self.output_path),
                }
            )

        payload_out: Dict[str, object] = {
            "documents_found": len(records),
            "downloaded_count": len(records),
            "skipped_count": 0,
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "table": self.TABLE,
            "variable": self.VARIABLE,
            "level": nivel,
            "start_year": y0,
            "end_year": y1,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw,
            "output_format": requested_format,
            "exported_files": exported,
        }
        combined = " ".join(item for item in warnings if item.strip())
        if combined:
            payload_out["export_warning"] = combined
        return payload_out

    def load_dataframe(self) -> pl.DataFrame:
        return self._to_df(self._records) if self._records else pl.DataFrame()

    def export(self, df: pl.DataFrame, format: str, name: str) -> Path:  # noqa: A003
        normalized = format.strip().lower()
        if normalized == "csv":
            path = self.output_path / f"{name}.csv"
            df.write_csv(path)
            return path
        if normalized == "parquet":
            path = self.output_path / f"{name}.parquet"
            df.write_parquet(path)
            return path
        if normalized == "sqlite":
            path = self.output_path / f"{name}.sqlite"
            escrito = write_sqlite(df, db_path=path, table=self.name)
            if escrito is None:
                raise ValueError("IBGE export to sqlite has no rows to write.")
            return escrito
        raise ValueError(
            f"Unsupported IBGE export format '{format}'. Allowed: csv, parquet, sqlite"
        )

    # -- parsing --------------------------------------------------------------
    def _parse(self, payload: List[Any], nivel: str) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for variable in payload:
            if not isinstance(variable, dict):
                continue
            variable_id = variable.get("id")
            unidade = variable.get("unidade")
            for resultado in variable.get("resultados") or []:
                classif_cols = self._classification_columns(resultado)
                for serie in resultado.get("series") or []:
                    localidade = serie.get("localidade") or {}
                    values = serie.get("serie") or {}
                    for year_key, raw_value in values.items():
                        row: Dict[str, object] = {
                            "nivel": nivel,
                            "localidade_id": localidade.get("id"),
                            "localidade_nome": localidade.get("nome"),
                            "ano": self._to_int(year_key),
                        }
                        row.update(classif_cols)
                        row["variavel_id"] = variable_id
                        row["unidade"] = unidade
                        row["valor"] = self._to_value(raw_value)
                        rows.append(row)
        return rows

    def _classification_columns(self, resultado: Dict[str, Any]) -> Dict[str, object]:
        """Map a resultado's classifications to ``{column: category_name}``."""
        columns: Dict[str, object] = {}
        for classificacao in resultado.get("classificacoes") or []:
            nome = classificacao.get("nome")
            categoria = classificacao.get("categoria") or {}
            category_name = next(iter(categoria.values()), None)
            if nome:
                columns[self._column_name(nome)] = category_name
        return columns

    @staticmethod
    def _column_name(nome: str) -> str:
        ascii_text = (
            unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode("ascii").lower()
        )
        cleaned = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
        return cleaned or "classificacao"

    def _to_value(self, value: object) -> Optional[float]:
        if value is None:
            return None
        text = str(value).strip()
        if text in self._MISSING:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None

    @staticmethod
    def _to_int(value: object) -> Optional[int]:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_df(records: List[Dict[str, object]]) -> pl.DataFrame:
        return pl.from_dicts(records, infer_schema_length=None)

    # -- helpers --------------------------------------------------------------
    def _resolve_client(self, *, api_base_url: Optional[str], timeout: int) -> IbgeSidraClient:
        timeout_value = max(1, int(timeout))
        if api_base_url and str(api_base_url).strip():
            return IbgeSidraClient(base_url=str(api_base_url).strip(), timeout_seconds=timeout_value)
        if self._client is not None:
            return self._client
        return IbgeSidraClient(timeout_seconds=timeout_value)

    def _resolve_level(self, level: str) -> str:
        key = str(level).strip().lower()
        if key not in self.LEVELS:
            allowed = ", ".join(sorted({v for v in self.LEVELS}))
            raise ValueError(f"Unsupported IBGE level '{level}'. Allowed: {allowed}")
        return self.LEVELS[key]

    @staticmethod
    def _parse_year(value: object, field_name: str) -> int:
        try:
            year = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{field_name}' must be a year (integer).") from exc
        if not (1900 <= year <= 2100):
            raise ValueError(f"Parameter '{field_name}' must be a plausible year.")
        return year

    @staticmethod
    def _normalize_format(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip().lower()
        if not cleaned:
            return None
        if cleaned not in _EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported output format '{value}'. Allowed: csv, parquet, sqlite"
            )
        return cleaned

    def _artifact_stem(self, nivel: str, start_year: int, end_year: int) -> str:
        return f"{self.name}_{nivel}_{start_year}_{end_year}"

    def _write_raw(self, stem: str, raw_by_year: Dict[str, Any]) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{stem}.json"
        path.write_text(json.dumps(raw_by_year, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _write_manifest(
        self,
        *,
        nivel: str,
        start_year: int,
        end_year: int,
        classificacao: Optional[str],
        record_count: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported: List[str],
        api_base_url: str,
        warnings: List[str],
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        manifest = DownloadManifest(
            source=self.name,
            results_url=api_base_url,
            filters={
                "table": self.TABLE,
                "variable": self.VARIABLE,
                "level": nivel,
                "classificacao": classificacao,
                "start_year": start_year,
                "end_year": end_year,
                "keep_raw": keep_raw,
                "output_format": output_format,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            documents_found=record_count,
            downloaded_files=[],
            materialized_paths=[str(raw_path)] if raw_path else [],
            exported_files=list(exported),
            warnings=list(warnings),
        )
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest_path


class IbgePibMunicipiosDataSource(SidraAggregateSource):
    """Municipal GDP (PIB dos Municípios) — SIDRA table 5938, variable 37.

    Annual (2002+), values in R$ 1000 (Mil Reais). The socioeconomic context /
    denominator layer alongside population.
    """

    TABLE = "5938"
    VARIABLE = "37"
    DEFAULT_LEVEL = "municipio"

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None) -> None:
        super().__init__(name="ibge_pib_municipios", output_path=output_path, client=client)

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )


class IbgePopulacaoIdadeSexoDataSource(SidraAggregateSource):
    """Census population by sex and age — SIDRA table 9514, variable 93.

    Census reference (2022), split by sex (``sexo``) and age (``faixa_etaria``).
    The default is 5-year age groups by sex per UF — the denominators for
    age-standardised rates. Set ``level=municipio`` for the municipal breakdown
    (a much larger extract).
    """

    TABLE = "9514"
    VARIABLE = "93"
    DEFAULT_LEVEL = "uf"

    SEXO = {
        "ambos": "4,5",
        "homens": "4",
        "mulheres": "5",
        "total": "6794",
        "todos": "all",
    }
    # C287 5-year age groups (0-4 ... 95-99) plus 100+ (6653).
    _QUINQUENAL = (
        "93070,93084,93085,93086,93087,93088,93089,93090,93091,93092,93093,"
        "93094,93095,93096,93097,93098,49108,49109,60040,60041,6653"
    )
    FAIXA_ETARIA = {
        "quinquenal": _QUINQUENAL,
        "total": "100362",
        "todos": "all",
    }

    def __init__(self, output_path: Optional[str] = None, *, client: Optional[IbgeSidraClient] = None) -> None:
        super().__init__(name="ibge_populacao_idade_sexo", output_path=output_path, client=client)

    def download(
        self,
        *,
        start_year: object,
        end_year: object,
        level: str = DEFAULT_LEVEL,
        sexo: str = "ambos",
        faixa_etaria: str = "quinquenal",
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        api_base_url: Optional[str] = None,
        timeout: int = SidraAggregateSource.DEFAULT_TIMEOUT,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        sexo_token = self.SEXO.get(str(sexo).strip().lower())
        if sexo_token is None:
            raise ValueError(f"Unsupported sexo '{sexo}'. Allowed: {', '.join(self.SEXO)}")
        idade_token = self.FAIXA_ETARIA.get(str(faixa_etaria).strip().lower())
        if idade_token is None:
            raise ValueError(
                f"Unsupported faixa_etaria '{faixa_etaria}'. Allowed: {', '.join(self.FAIXA_ETARIA)}"
            )
        classificacao = f"2[{sexo_token}]|287[{idade_token}]"
        return self._collect(
            start_year=start_year,
            end_year=end_year,
            level=level,
            classificacao=classificacao,
            output_format=output_format,
            keep_raw=keep_raw,
            api_base_url=api_base_url,
            timeout=timeout,
            progress_callback=progress_callback,
        )
