"""Série horária de CONCENTRAÇÃO da CETESB, pelo QUALAR autenticado.

Esta é a contraparte de :class:`~guaraci.cetesb.qualar.CetesbQualarDataSource`.
As duas falam da mesma rede de estações e entregam coisas diferentes:

===========================  ==================  ===========================
                             `cetesb_qualar`     `cetesb_qualar_horario`
===========================  ==================  ===========================
Medida                       índice              concentração (µg/m³, ppm…)
Período                      últimas 48h         qualquer intervalo
Credencial                   nenhuma             conta no QUALAR
Parâmetros                   6 poluentes         12 poluentes + 8 meteorológicos
===========================  ==================  ===========================

Quem vai correlacionar poluição com desfecho de saúde precisa desta, não
daquela: o índice é uma transformação por faixas e não serve para
dose-resposta.

A credencial é lida SÓ do ambiente (``GUARACI_QUALAR_LOGIN`` e
``GUARACI_QUALAR_SENHA``), nunca de parâmetro de job, pelo mesmo motivo que
vale para NASA FIRMS e ANA: parâmetro de job é persistido em disco no
manifesto e no histórico de execuções.

Estado: **experimental.** O protocolo foi reconstruído a partir do HTML do
sistema e do pacote R `qualR`, e os testes offline cobrem o parser com uma
página real fixada. A validação contra o sistema ao vivo depende de uma conta
no QUALAR, que ainda não existe no momento desta integração. É a mesma
situação em que `ana_hidro` entrou.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import polars as pl

from guaraci.cetesb.client import CetesbClientError
from guaraci.cetesb.codes import resolve_parameter, resolve_station
from guaraci.cetesb.qualar import _CetesbBase, _normalize_format
from guaraci.cetesb.qualar_client import REGISTRATION_URL, QualarClient

ProgressCallback = Callable[[Dict[str, object]], None]

_LOGIN_ENV = "GUARACI_QUALAR_LOGIN"
_SENHA_ENV = "GUARACI_QUALAR_SENHA"

HOURLY_COLUMNS: Tuple[str, ...] = (
    "estacao",
    "codigo_estacao",
    "latitude",
    "longitude",
    "parametro",
    "codigo_parametro",
    "unidade",
    "datahora",
    "valor",
    "validado",
)

# Os seis poluentes que a rede automática mede em praticamente toda estação.
# Servem de default para quem não quer escolher, e coincidem com o que o
# conector do ArcGIS cobre, o que torna as duas fontes comparáveis.
DEFAULT_PARAMETERS: Tuple[str, ...] = ("MP10", "MP2.5", "O3", "NO2", "SO2", "CO")


class CetesbQualarHorarioDataSource(_CetesbBase):
    """Concentração horária medida, por estação e parâmetro, via QUALAR."""

    DEFAULT_TIMEOUT = QualarClient.DEFAULT_TIMEOUT
    DEFAULT_PAUSE_SECONDS = QualarClient.DEFAULT_PAUSE_SECONDS

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[QualarClient] = None,
        login: Optional[str] = None,
        senha: Optional[str] = None,
    ) -> None:
        super().__init__(name="cetesb_qualar_horario", output_path=output_path)
        self._qualar_client = client
        self._injected_login = login
        self._injected_senha = senha

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def download(
        self,
        *,
        stations: Sequence[object],
        start_date: object,
        end_date: object,
        parameters: Optional[Sequence[object]] = None,
        only_validated: bool = True,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        pause_seconds: float = DEFAULT_PAUSE_SECONDS,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        resolved_stations = self._resolve_stations(stations)
        resolved_parameters = self._resolve_parameters(parameters)
        start = self._parse_date(start_date, field_name="start_date")
        end = self._parse_date(end_date, field_name="end_date")
        if end < start:
            raise ValueError("Parameter 'end_date' cannot be before 'start_date'.")

        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._resolve_qualar_client(
            api_base_url=api_base_url, timeout=timeout, pause_seconds=pause_seconds
        )

        pairs = [
            (station, parameter)
            for station in resolved_stations
            for parameter in resolved_parameters
        ]
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": self.name,
                    "documents_total": len(pairs),
                }
            )

        records: List[Dict[str, object]] = []
        failed: List[str] = []
        collected = 0
        empty_pairs: List[str] = []

        for index, (station, parameter) in enumerate(pairs, start=1):
            label = f"{station.name}/{parameter.abbreviation}"
            try:
                readings = client.fetch_readings(
                    station=station,
                    parameter=parameter,
                    start=start,
                    end=end,
                    only_validated=only_validated,
                )
            except CetesbClientError as exc:
                failed.append(f"{label}: {exc}")
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "file_failed",
                            "source": self.name,
                            "document_index": index,
                            "documents_total": len(pairs),
                            "document": label,
                            "error": str(exc),
                        }
                    )
                continue
            if readings:
                records.extend(readings)
            else:
                # Estação que não mede aquele parâmetro é o caso comum, não
                # erro: nem toda estação da rede tem todos os sensores.
                empty_pairs.append(label)
            collected += 1
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "file_completed",
                        "source": self.name,
                        "document_index": index,
                        "documents_total": len(pairs),
                        "document": label,
                    }
                )

        dataframe = self._records_to_dataframe(records)
        self._dataframe = dataframe

        warnings: List[str] = []
        if empty_pairs:
            warnings.append(
                f"{len(empty_pairs)} par(es) estação/parâmetro sem leitura no "
                "período (a estação pode não medir esse parâmetro): "
                + ", ".join(empty_pairs[:10])
                + ("…" if len(empty_pairs) > 10 else "")
            )
        if only_validated and dataframe.is_empty() and not failed:
            warnings.append(
                "Nenhuma leitura validada no período. Use only_validated=false "
                "para incluir também as leituras ainda não validadas pela CETESB."
            )

        if keep_raw and records:
            raw_path = base_dir / "raw" / "cetesb_qualar_horario_raw.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        requested_format = _normalize_format(output_format)
        exported: List[str] = []
        stem = f"cetesb_qualar_horario_{start:%Y%m%d}_{end:%Y%m%d}"
        if requested_format and not dataframe.is_empty():
            try:
                exported.append(
                    str(self.export(dataframe, format=requested_format, name=stem))
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
            "documents_found": len(pairs),
            "downloaded_count": collected,
            "skipped_count": 0,
            "failed_count": len(failed),
            "output_dir": str(base_dir),
            "measure": "concentracao",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "stations": [item.name for item in resolved_stations],
            "parameters": [item.abbreviation for item in resolved_parameters],
            "only_validated": only_validated,
            "record_count": dataframe.height,
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
    @staticmethod
    def _resolve_stations(values: Sequence[object]) -> Tuple:
        if not values:
            raise ValueError(
                "Parameter 'stations' is required: the QUALAR answers one "
                "station at a time, so there is no meaningful default. Use "
                "guaraci.cetesb.codes.station_names() to list them."
            )
        resolved = [resolve_station(item) for item in values]
        # dedup preservando a ordem pedida
        seen: Dict[int, object] = {}
        for item in resolved:
            seen.setdefault(item.code, item)
        return tuple(seen.values())

    @staticmethod
    def _resolve_parameters(values: Optional[Sequence[object]]) -> Tuple:
        source = values if values else DEFAULT_PARAMETERS
        resolved = [resolve_parameter(item) for item in source]
        seen: Dict[int, object] = {}
        for item in resolved:
            seen.setdefault(item.code, item)
        return tuple(seen.values())

    @staticmethod
    def _parse_date(value: object, *, field_name: str) -> date:
        """Aceita ``date``/``datetime``, ISO ``aaaa-mm-dd`` e ``dd/mm/aaaa``.

        O QUALAR fala ``dd/mm/aaaa``, mas o resto do Guaraci fala ISO nos
        parâmetros de data (ver a convenção em docs/SOURCES_AND_FILTERS).
        Aceitar as duas evita que o usuário precise saber de que lado está.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            raise ValueError(f"Parameter '{field_name}' is required.")
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(
            f"Parameter '{field_name}' must be YYYY-MM-DD or DD/MM/YYYY, got {value!r}."
        )

    @staticmethod
    def _records_to_dataframe(records: Sequence[Mapping[str, object]]) -> pl.DataFrame:
        if not records:
            return pl.DataFrame(
                schema={
                    "estacao": pl.Utf8,
                    "codigo_estacao": pl.Int64,
                    "latitude": pl.Float64,
                    "longitude": pl.Float64,
                    "parametro": pl.Utf8,
                    "codigo_parametro": pl.Int64,
                    "unidade": pl.Utf8,
                    "datahora": pl.Datetime,
                    "valor": pl.Float64,
                    "validado": pl.Boolean,
                }
            )
        frame = pl.DataFrame([dict(item) for item in records])
        return frame.select(list(HOURLY_COLUMNS)).sort(
            ["parametro", "estacao", "datahora"]
        )

    def _resolve_login(self) -> str:
        candidate = self._injected_login or os.getenv(_LOGIN_ENV)
        if candidate and candidate.strip():
            return candidate.strip()
        raise ValueError(
            "CETESB QUALAR requires a login. Set the environment variable "
            f"{_LOGIN_ENV}. A free account can be created at {REGISTRATION_URL}"
        )

    def _resolve_senha(self) -> str:
        candidate = self._injected_senha or os.getenv(_SENHA_ENV)
        if candidate and candidate.strip():
            return candidate.strip()
        raise ValueError(
            "CETESB QUALAR requires a password. Set the environment variable "
            f"{_SENHA_ENV}. A free account can be created at {REGISTRATION_URL}"
        )

    def _resolve_qualar_client(
        self, *, api_base_url: Optional[str], timeout: int, pause_seconds: float
    ) -> QualarClient:
        if self._qualar_client is not None:
            return self._qualar_client
        return QualarClient(
            login=self._resolve_login(),
            password=self._resolve_senha(),
            base_url=api_base_url,
            timeout_seconds=timeout,
            pause_seconds=pause_seconds,
        )
