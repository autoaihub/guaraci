"""OpenDataSUS datasource for MVP dataset ingestion and export."""

from __future__ import annotations

import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional
from urllib.parse import quote

import polars as pl

from guaraci.core.contracts import DownloadManifest
from guaraci.core.datasource import DataSource
from guaraci.opendatasus.client import OpenDataSUSClient, OpenDataSUSClientError
from guaraci.opendatasus.utils.swagger_catalog import (
    DemasPniEndpoint,
    load_local_get_params_catalog,
    load_local_pni_catalog,
)


@dataclass(frozen=True)
class OpenDataSUSDatasetSpec:
    """Dataset-level metadata used for query generation."""

    package_id: str
    preferred_resource_terms: tuple[str, ...]
    date_column: str
    uf_column: str
    demas_strategy: str = "pni_yearly"
    demas_static_path: Optional[str] = None
    ckan_supported: bool = True
    # Alguns endpoints DEMAS expoem uma coluna de data inutilizavel como filtro
    # (ver srag_demas). Nesses casos o refinamento local start_date/end_date
    # descartaria quase tudo em silencio, entao ele e recusado na entrada.
    date_filter_supported: bool = True
    date_filter_note: Optional[str] = None
    # Preenchido quando o dataset e grande o bastante para bater no teto de
    # max_pages x batch_size numa execucao normal. Vira aviso de pre-voo.
    large_dataset_note: Optional[str] = None
    # Fonte de arquivos em lote que entrega os mesmos dados sem paginar. Quando
    # existe, subir max_pages e o conselho errado (ver srag_demas).
    bulk_alternative: Optional[str] = None


@dataclass(frozen=True)
class DemasEndpointPlan:
    """Resolved DEMAS endpoint details for one download run."""

    path: str
    label: str
    uf_params: tuple[str, ...]
    query_params: Dict[str, object] = field(default_factory=dict)


class OpenDataSUSDataSource(DataSource):
    """OpenDataSUS datasource supporting CKAN and DEMAS vaccination APIs."""

    DEFAULT_DATASET = "doses_aplicadas_pni"
    DEFAULT_MAX_PAGES = 250
    # Acima disso o modo DEMAS para de acumular linhas em memória e passa a
    # servir export/load_dataframe direto do spool em disco. O buffer existe só
    # para poupar o round-trip de disco em download pequeno, então o teto é
    # baixo de propósito: uma linha de SRAG ocupa ~8 KB como dict Python, e é
    # esse acúmulo que fazia o bloco 2019-2026 inteiro projetar ~37 GB.
    MAX_RECORDS_IN_MEMORY = 10_000
    # Lote do sink de conversão. Pequeno de propósito: é o que mantém o pico do
    # export plano em vez de proporcional ao dataset.
    SPOOL_STREAM_BATCH = 1024
    SPOOL_PARQUET_ROW_GROUP = 10_000
    # Páginas DEMAS buscadas em paralelo. Medido ao vivo em 2026-09-02 no
    # endpoint de SRAG: 1 conexão rende ~200 linhas/s, 8 rendem ~1.200 e 16-24
    # estabilizam em ~1.400; com 32 o servidor piora (~1.000). O default fica no
    # joelho da curva, longe do ponto em que a API pública começa a sofrer.
    DEFAULT_CONCURRENCY = 8
    MAX_CONCURRENCY = 16
    # Blocos do endpoint DEMAS de SRAG. Cada bloco e um endpoint unico: pedir
    # start_year=2024 seleciona o bloco 2019-2026 inteiro, sem recorte remoto.
    SRAG_BLOCKS: tuple[tuple[int, int, str], ...] = (
        (2009, 2012, "2009-2012"),
        (2013, 2018, "2013-2018"),
        (2019, 2026, "2019-2026"),
    )
    LOCAL_SWAGGER_PATH = Path(__file__).resolve().parent / "utils" / "swagger.json"
    DATASET_SPECS: Dict[str, OpenDataSUSDatasetSpec] = {
        "doses_aplicadas_pni": OpenDataSUSDatasetSpec(
            package_id="covid-19-vacinacao",
            preferred_resource_terms=("vacinacao", "vacina", "covid"),
            date_column="data_vacina",
            uf_column="uf_estabelecimento",
        ),
        "zikavirus": OpenDataSUSDatasetSpec(
            package_id="arboviroses-zikavirus",
            preferred_resource_terms=("zikavirus", "zika", "arboviroses"),
            date_column="dt_notific",
            uf_column="sg_uf_not",
            demas_strategy="static",
            demas_static_path="/arboviroses/zikavirus",
            ckan_supported=False,
        ),
        "dengue": OpenDataSUSDatasetSpec(
            package_id="arboviroses-dengue",
            preferred_resource_terms=("dengue", "arboviroses"),
            date_column="dt_notific",
            uf_column="sg_uf_not",
            demas_strategy="static",
            demas_static_path="/arboviroses/dengue",
            ckan_supported=False,
        ),
        "chikungunya": OpenDataSUSDatasetSpec(
            package_id="arboviroses-chikungunya",
            preferred_resource_terms=("chikungunya", "arboviroses"),
            date_column="dt_notific",
            uf_column="sg_uf_not",
            demas_strategy="static",
            demas_static_path="/arboviroses/chikungunya",
            ckan_supported=False,
        ),
        "sindrome_gripal_leve": OpenDataSUSDatasetSpec(
            package_id="notificacoes-de-sindrome-gripal-leve",
            preferred_resource_terms=("gripe", "sindrome gripal", "leve"),
            date_column="dt_notific", # Padrão para vigilância
            uf_column="uf",
            demas_strategy="yearly_suffix",
            demas_static_path="/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve",
            ckan_supported=False,
        ),
        "srag_demas": OpenDataSUSDatasetSpec(
            package_id="srag-demas",
            preferred_resource_terms=("srag", "hospitalizacao", "respiratoria"),
            date_column="dt_notific",
            uf_column="sg_uf",
            demas_strategy="block_ranges",
            demas_static_path="/vigilancia-e-meio-ambiente/srag",
            ckan_supported=False,
            date_filter_supported=False,
            bulk_alternative="srag_arquivos",
            large_dataset_note=(
                "Medido ao vivo em 2026-09-02: o bloco 2019-2026 tem ~4.445.000 linhas e a "
                "API entrega no maximo 1000 por request. Esgotar o bloco leva ~1,6h na "
                "concorrencia padrao (770 linhas/s) e ~6h sem paralelismo. Os MESMOS dados "
                "saem em parquet pela fonte 'srag_arquivos': ~347 MB para 2019-2026 inteiro, "
                "em minutos, e la a coluna DT_NOTIFIC e uma data real, nao o marcador de "
                "temporada."
            ),
            date_filter_note=(
                "O endpoint DEMAS srag-2019-2026 nao devolve dt_notific como data real: "
                "a coluna vem colapsada no marcador de temporada (verificado ao vivo em "
                "2026-09-02 — 997 das 1000 linhas da primeira pagina com dt_notific="
                "2018-12-30, e a pagina em offset 1.000.000 inteira com 2019-12-29 "
                "enquanto dt_sin_pri da mesma linha e 2020-11-18). Recortar por data "
                "nessa coluna descartaria quase todos os registros sem aviso. Para "
                "recorte por ano use a fonte 'srag_arquivos', que baixa os arquivos "
                "completos do portal. O refinamento por 'uf' continua valido (sg_uf e "
                "preenchido normalmente)."
            ),
        ),
        "febre_amarela": OpenDataSUSDatasetSpec(
            package_id="arboviroses-febre-amarela",
            preferred_resource_terms=("febre", "amarela", "arboviroses", "humanos"),
            date_column="dt_is",
            uf_column="uf_lpi",
            demas_strategy="static",
            demas_static_path="/arboviroses/febre-amarela-humanos-primatas-nao-humanos",
            ckan_supported=False,
        ),
        "mpox": OpenDataSUSDatasetSpec(
            package_id="mpox",
            preferred_resource_terms=("mpox", "variola"),
            date_column="dt_notific",
            uf_column="sg_uf_not",
            demas_strategy="static",
            demas_static_path="/vigilancia-e-meio-ambiente/mpox",
            ckan_supported=False,
        ),
        "esavi": OpenDataSUSDatasetSpec(
            package_id="esavi",
            preferred_resource_terms=("esavi", "eventos adversos"),
            date_column="data_notificacao",
            uf_column="nome_estado",
            demas_strategy="static",
            demas_static_path="/vacinacao/esavi",
            ckan_supported=False,
        ),
    }

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[OpenDataSUSClient] = None,
    ) -> None:
        super().__init__(name="opendatasus", output_path=output_path)
        self._client = client
        self._data_by_dataset: Dict[str, List[Dict[str, object]]] = {}
        self._spool_by_dataset: Dict[str, Path] = {}
        self._latest_dataset: Optional[str] = None
        self._demas_catalog = load_local_pni_catalog(self.LOCAL_SWAGGER_PATH)
        self._demas_get_params_by_path = load_local_get_params_catalog(self.LOCAL_SWAGGER_PATH)

    @classmethod
    def check_unsupported_refinements(
        cls,
        *,
        dataset: Optional[str] = None,
        start_date: object = None,
        end_date: object = None,
        **_ignored: object,
    ) -> None:
        """Recusa refinamentos que a fonte nao consegue honrar.

        Roda na validacao de parametros (antes de criar o job) e de novo dentro
        de download(), para que chamadas diretas a datasource nao escapem.
        """
        spec = cls.DATASET_SPECS.get((dataset or "").strip().lower())
        if spec is None or spec.date_filter_supported:
            return
        has_start = start_date is not None and str(start_date).strip() != ""
        has_end = end_date is not None and str(end_date).strip() != ""
        if not (has_start or has_end):
            return
        note = spec.date_filter_note or (
            "The date column exposed by this endpoint is not usable as a filter."
        )
        raise ValueError(
            "Refinamento por data nao e suportado para o dataset "
            f"'{(dataset or '').strip().lower()}'. {note}"
        )

    # Sonda de truncamento: quantos endpoints checar e por quanto tempo. Um
    # request no offset do teto responde em ~0,4-1,0s e diz, com certeza, se
    # existe dado alem do que esta execucao vai baixar.
    TRUNCATION_PROBE_ENDPOINTS = 3
    TRUNCATION_PROBE_TIMEOUT_SECONDS = 20

    def preflight_warnings(
        self,
        *,
        dataset: Optional[str] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        batch_size: object = 1000,
        max_pages: object = None,
        api_base_url: Optional[str] = None,
        **api_params: object,
    ) -> List[str]:
        """Avisos conhecidos ANTES de disparar o download.

        A API DEMAS nao expoe contagem total, entao um truncamento so apareceria
        no fim de um download longo — tarde demais para o usuario desistir. Em
        vez de adivinhar pelo nome da fonte, aqui a gente pergunta: um unico
        request no offset do teto revela se existe dado alem dele.
        """

        warnings: List[str] = []
        dataset_key = (dataset or "").strip().lower()
        spec = self.DATASET_SPECS.get(dataset_key) or self._try_build_generic_spec(dataset_key)
        if spec is None:
            return warnings

        page_size = min(max(1, int(batch_size or 1000)), 1000)
        pages = min(max(1, int(max_pages or self.DEFAULT_MAX_PAGES)), 200000)
        row_cap = page_size * pages
        row_cap_label = f"{row_cap:,}".replace(",", ".")

        if self._probe_demas_truncation(
            spec=spec,
            dataset=dataset_key,
            start_year=start_year,
            end_year=end_year,
            row_cap=row_cap,
            api_base_url=api_base_url,
            api_params=api_params,
        ):
            remedy = (
                f"Use a fonte '{spec.bulk_alternative}', que baixa os arquivos completos "
                "sem paginar."
                if spec.bulk_alternative
                else "Aumente max_pages para levar o download ate o fim (ele escreve em "
                "disco por pagina e retoma se cair) ou reduza a janela consultada."
            )
            note = f" {spec.large_dataset_note}" if spec.large_dataset_note else ""
            warnings.append(
                f"ESTA EXECUCAO VAI TRUNCAR: a fonte tem mais que o teto de {row_cap_label} "
                f"linhas por endpoint (max_pages={pages} x batch_size={page_size}), "
                f"verificado agora na propria API. O download para no teto e o arquivo sai "
                f"incompleto, sem erro. {remedy}{note}"
            )

        if spec.demas_strategy == "block_ranges" and start_year and end_year:
            covered = [
                block
                for block in self.SRAG_BLOCKS
                if max(int(start_year), block[0]) <= min(int(end_year), block[1])
            ]
            widened = [
                block
                for block in covered
                if block[0] < int(start_year) or block[1] > int(end_year)
            ]
            if widened:
                labels = ", ".join(block[2] for block in covered)
                warnings.append(
                    f"O endpoint DEMAS e segmentado em blocos fixos ({labels}), nao por ano: "
                    f"a janela pedida ({start_year}-{end_year}) vai baixar o bloco inteiro, "
                    "e nao ha filtro remoto de ano para reduzir isso."
                )

        return warnings

    def _probe_demas_truncation(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        dataset: str,
        start_year: Optional[int],
        end_year: Optional[int],
        row_cap: int,
        api_base_url: Optional[str],
        api_params: Mapping[str, object],
    ) -> bool:
        """Existe dado alem do teto desta execucao?

        Um request por endpoint, com ``offset`` no teto e ``limit=1``: se vier
        linha, o download vai truncar — certeza, nao suspeita. Qualquer falha
        aqui devolve False, porque pre-voo nunca pode impedir o download.
        """
        try:
            # Cliente proprio, com timeout curto e sem retry: um disparo nao pode
            # ficar preso em pre-voo se a API estiver lenta ou fora do ar.
            if api_base_url and api_base_url.strip():
                client = OpenDataSUSClient(
                    base_url=api_base_url,
                    timeout_seconds=self.TRUNCATION_PROBE_TIMEOUT_SECONDS,
                    max_attempts=1,
                )
            elif self._client is not None:
                client = self._client
            else:
                client = OpenDataSUSClient(
                    timeout_seconds=self.TRUNCATION_PROBE_TIMEOUT_SECONDS,
                    max_attempts=1,
                )
            if client.mode != "demas":
                return False
            normalized = self._normalize_demas_api_params(dict(api_params))
            start, end = self._normalize_year_window(start_year=start_year, end_year=end_year)
            endpoints = self._resolve_demas_endpoints(
                spec=spec,
                dataset=dataset,
                start_year=start,
                end_year=end,
                api_params=normalized,
            )[: self.TRUNCATION_PROBE_ENDPOINTS]
        except Exception:  # noqa: BLE001
            return False

        if not endpoints:
            return False

        def probe(endpoint_spec: DemasEndpointPlan) -> bool:
            params = dict(endpoint_spec.query_params)
            params.update({"limit": 1, "offset": row_cap})
            try:
                payload = client.demas_get(endpoint_spec.path, params=params)
            except Exception:  # noqa: BLE001
                return False
            return bool(self._extract_demas_rows(payload))

        try:
            if len(endpoints) == 1:
                return probe(endpoints[0])
            with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
                return any(pool.map(probe, endpoints))
        except Exception:  # noqa: BLE001
            return False

    def download(
        self,
        dataset: str,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        uf: Optional[str] = None,
        batch_size: int = 1000,
        output_format: Optional[str] = None,
        resource_id: Optional[str] = None,
        api_base_url: Optional[str] = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        concurrency: int = DEFAULT_CONCURRENCY,
        keep_raw: bool = False,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
        **api_params: object,
    ) -> Dict[str, object]:
        """Download records from one configured OpenDataSUS dataset."""

        dataset_key = dataset.strip().lower()
        spec = self.DATASET_SPECS.get(dataset_key)
        demas_api_params = self._normalize_demas_api_params(api_params)

        # ------------------------------------------------------------------
        # Generic fallback: if the dataset is not in DATASET_SPECS, try to
        # resolve it as a DEMAS static-path endpoint from the Swagger catalog.
        # This enables the ~75 auto-registered sources to work without manual
        # OpenDataSUSDatasetSpec declarations.
        # ------------------------------------------------------------------
        if spec is None:
            generic_spec = self._try_build_generic_spec(dataset_key)
            if generic_spec is None:
                supported = ", ".join(sorted(self.DATASET_SPECS))
                raise ValueError(
                    f"Unsupported OpenDataSUS dataset '{dataset}'. "
                    f"No matching Swagger path found. Known specs: {supported}"
                )
            spec = generic_spec

        start_year_value, end_year_value = self._normalize_year_window(
            start_year=start_year,
            end_year=end_year,
        )
        range_start = date(start_year_value, 1, 1)
        range_end = date(end_year_value, 12, 31)
        start = self._parse_optional_iso_date(start_date, field_name="start_date")
        end = self._parse_optional_iso_date(end_date, field_name="end_date")
        if start is not None and end is not None and start > end:
            raise ValueError("Parameter 'start_date' cannot be after 'end_date'.")
        if start is not None and (start < range_start or start > range_end):
            raise ValueError(
                "Parameter 'start_date' must be within the selected start_year/end_year range."
            )
        if end is not None and (end < range_start or end > range_end):
            raise ValueError(
                "Parameter 'end_date' must be within the selected start_year/end_year range."
            )

        self.check_unsupported_refinements(
            dataset=dataset_key,
            start_date=start,
            end_date=end,
        )

        uf_clean = self._normalize_uf(uf)
        fetch_batch_size = max(1, int(batch_size))
        max_pages_value = max(1, int(max_pages))
        requested_format = self._normalize_output_format(output_format)
        keep_raw_value = bool(keep_raw)
        effective_start = start or range_start
        effective_end = end or range_end
        client = self._resolve_client(api_base_url=api_base_url)

        if client.mode == "demas":
            return self._download_from_demas(
                spec=spec,
                dataset=dataset_key,
                start_year=start_year_value,
                end_year=end_year_value,
                effective_start=effective_start,
                effective_end=effective_end,
                start=start,
                end=end,
                uf=uf_clean,
                batch_size=fetch_batch_size,
                max_pages=max_pages_value,
                concurrency=concurrency,
                requested_format=requested_format,
                resource_id=resource_id,
                keep_raw=keep_raw_value,
                api_params=demas_api_params,
                client=client,
                progress_callback=progress_callback,
            )

        if not spec.ckan_supported:
            raise OpenDataSUSClientError(
                "This dataset is currently available only through DEMAS API mode. "
                "Use api_base_url='https://apidadosabertos.saude.gov.br'."
            )

        selected_resource_id = self._resolve_resource_id(
            client=client,
            spec=spec,
            resource_id=resource_id,
        )

        where_clauses = self._build_where_clauses(
            spec=spec,
            start=effective_start,
            end=effective_end,
            uf=uf_clean,
        )

        total_records = self._count_records(
            client=client,
            resource_id=selected_resource_id,
            where_clauses=where_clauses,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": dataset_key,
                    "documents_total": total_records,
                }
            )

        records: List[Dict[str, object]] = []
        if total_records > 0:
            for offset in range(0, total_records, fetch_batch_size):
                chunk = self._fetch_records(
                    client=client,
                    resource_id=selected_resource_id,
                    date_column=spec.date_column,
                    where_clauses=where_clauses,
                    limit=fetch_batch_size,
                    offset=offset,
                )
                records.extend(chunk)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "file_progress",
                            "source": dataset_key,
                            "documents_total": total_records,
                            "document_index": min(len(records), total_records),
                            "files_completed": min(len(records), total_records),
                        }
                    )

        self._data_by_dataset[dataset_key] = records
        self._latest_dataset = dataset_key

        artifact_stem = self._build_artifact_stem(
            dataset=dataset_key,
            start=effective_start,
            end=effective_end,
            uf=uf_clean,
        )
        raw_path: Optional[Path] = None
        if keep_raw_value:
            raw_path = self._write_raw_snapshot(
                stem=artifact_stem,
                records=records,
            )
        exported_files: List[str] = []
        warnings: List[str] = []
        if requested_format:
            if records:
                try:
                    dataframe = self._records_to_dataframe(records)
                    export_path = self.export(
                        dataframe,
                        format=requested_format,
                        name=artifact_stem,
                    )
                    exported_files.append(str(export_path))
                except Exception as exc:
                    warnings.append(
                        self._build_export_failure_warning(
                            exc=exc,
                            keep_raw=keep_raw_value,
                        )
                    )
            else:
                warnings.append(
                    "No records returned by OpenDataSUS query; export file was not generated. "
                    "Consider widening the date window or removing optional refinements such as UF."
                )
        elif not keep_raw_value:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is empty). "
                "Set output_format or enable keep_raw."
            )

        manifest_path = self._write_manifest(
            dataset=dataset_key,
            resource_id=selected_resource_id,
            start_year=start_year_value,
            end_year=end_year_value,
            start=start,
            end=end,
            effective_start=effective_start,
            effective_end=effective_end,
            uf=uf_clean,
            total_records=total_records,
            records_downloaded=len(records),
            raw_path=raw_path,
            keep_raw=keep_raw_value,
            output_format=requested_format,
            exported_files=exported_files,
            api_base_url=client.base_url,
            warnings=warnings,
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": dataset_key,
                    "documents_total": total_records,
                    "downloaded_count": len(records),
                    "failed_count": 0,
                    "skipped_count": max(total_records - len(records), 0),
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": total_records,
            "downloaded_count": len(records),
            "skipped_count": max(total_records - len(records), 0),
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "dataset": dataset_key,
            "resource_id": selected_resource_id,
            "start_year": start_year_value,
            "end_year": end_year_value,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "query_start_date": effective_start.isoformat(),
            "query_end_date": effective_end.isoformat(),
            "uf": uf_clean,
            "api_base_url": client.base_url,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw_value,
            "output_format": requested_format,
            "exported_files": exported_files,
            "truncated": False,
            "warnings": list(warnings),
        }
        export_warning = self._combine_warnings(warnings)
        if export_warning:
            payload["export_warning"] = export_warning
        return payload

    def load_dataframe(self, dataset: Optional[str] = None) -> pl.DataFrame:
        """Load downloaded OpenDataSUS records into Polars."""

        selected = (dataset or self._latest_dataset or "").strip().lower()
        if not selected:
            raise ValueError("No OpenDataSUS dataset loaded yet. Run download() first.")
        records = self._data_by_dataset.get(selected)
        if records is None:
            raise ValueError(
                f"Dataset '{selected}' not available in memory. Run download() for this dataset first."
            )
        if not records:
            # Download grande: o buffer em memória foi descartado durante a
            # coleta e o spool em disco é quem tem a série completa.
            spool_path = self._spool_by_dataset.get(selected)
            if spool_path is not None and spool_path.exists():
                return self._read_spool_dataframe(spool_path)
            return pl.DataFrame()
        return pl.DataFrame(records)

    def export(self, df: pl.DataFrame, format: str, name: str) -> Path:  # noqa: A003
        """Export a Polars DataFrame to CSV, Parquet or SQLite."""

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
            table_name = "opendatasus_records"
            with sqlite3.connect(path) as connection:
                df.to_pandas().to_sql(table_name, connection, if_exists="replace", index=False)
            return path

        raise ValueError(
            f"Unsupported OpenDataSUS export format '{format}'. Allowed: csv, parquet, sqlite"
        )

    def _resolve_client(self, api_base_url: Optional[str]) -> OpenDataSUSClient:
        if api_base_url and api_base_url.strip():
            return OpenDataSUSClient(base_url=api_base_url)
        if self._client is not None:
            return self._client
        return OpenDataSUSClient()

    def _resolve_resource_id(
        self,
        *,
        client: OpenDataSUSClient,
        spec: OpenDataSUSDatasetSpec,
        resource_id: Optional[str],
    ) -> str:
        if resource_id and resource_id.strip():
            return resource_id.strip()

        try:
            package_payload = client.package_show(spec.package_id)
        except OpenDataSUSClientError as exc:
            raise self._annotate_client_error(
                exc,
                context=(
                    "OpenDataSUS CKAN metadata lookup failed while resolving "
                    f"package '{spec.package_id}'"
                ),
            ) from exc
        resources = package_payload.get("resources")
        if not isinstance(resources, list):
            raise OpenDataSUSClientError(
                "OpenDataSUS package metadata did not return a resources list."
            )

        preferred = [item.lower() for item in spec.preferred_resource_terms]
        fallback_id: Optional[str] = None

        for resource in resources:
            if not isinstance(resource, Mapping):
                continue
            candidate_id = str(resource.get("id") or "").strip()
            if not candidate_id:
                continue
            if fallback_id is None:
                fallback_id = candidate_id

            if not bool(resource.get("datastore_active")):
                continue

            searchable = " ".join(
                [
                    str(resource.get("name") or ""),
                    str(resource.get("description") or ""),
                    str(resource.get("url") or ""),
                ]
            ).lower()
            if any(term in searchable for term in preferred):
                return candidate_id

        if fallback_id is not None:
            return fallback_id

        raise OpenDataSUSClientError(
            f"No resource identifier could be resolved for package '{spec.package_id}'."
        )

    def _download_from_demas(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        dataset: str,
        start_year: int,
        end_year: int,
        effective_start: date,
        effective_end: date,
        start: Optional[date],
        end: Optional[date],
        uf: Optional[str],
        batch_size: int,
        max_pages: int,
        concurrency: int,
        requested_format: Optional[str],
        resource_id: Optional[str],
        keep_raw: bool,
        client: OpenDataSUSClient,
        api_params: Mapping[str, object],
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
    ) -> Dict[str, object]:
        endpoints = self._resolve_demas_endpoints(
            spec=spec,
            dataset=dataset,
            start_year=start_year,
            end_year=end_year,
            api_params=api_params,
        )
        years = list(range(start_year, end_year + 1))
        page_size = min(max(1, int(batch_size)), 1000)
        max_pages_per_year = min(max(1, int(max_pages)), 200000)
        workers = min(max(1, int(concurrency)), self.MAX_CONCURRENCY)
        estimated_pages_total = max(1, len(endpoints) * max_pages_per_year)

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_start",
                    "source": dataset,
                    "documents_total": estimated_pages_total,
                }
            )

        # O stem sai antes do loop porque nomeia o spool: as páginas são escritas
        # em disco à medida que chegam, e o mesmo arquivo é o snapshot bruto
        # quando keep_raw=True. Acumular tudo em memória antes de escrever era um
        # teto real — 4,45M linhas de SRAG a ~8 KB por dict dariam ~36 GB.
        artifact_stem = self._build_artifact_stem(
            dataset=dataset,
            start=effective_start,
            end=effective_end,
            uf=uf,
        )
        # Spool e checkpoint são nomeados pela identidade da CONSULTA, não pelo
        # stem do artefato — este carrega timestamp, então nunca casaria entre
        # duas execuções e a retomada jamais encontraria o trabalho anterior.
        fingerprint = self._demas_fingerprint(
            dataset=dataset,
            endpoints=endpoints,
            page_size=page_size,
            uf=uf,
            start=start,
            end=end,
        )
        spool_path = self._demas_spool_path(fingerprint)
        checkpoint_path = self._demas_checkpoint_path(fingerprint)
        resumed_from = self._resume_demas_checkpoint(
            checkpoint_path=checkpoint_path,
            spool_path=spool_path,
            fingerprint=fingerprint,
        )

        records: List[Dict[str, object]] = []
        buffer_dropped = False
        pages_scanned = 0
        truncated = False
        records_written = 0
        first_endpoint_index = 0
        first_page_index = 0

        if resumed_from is not None:
            records_written = int(resumed_from["rows_written"])
            first_endpoint_index = int(resumed_from["endpoint_index"])
            first_page_index = int(resumed_from["pages_done"])
            # O que já foi para o disco não volta para a memória: a partir daqui
            # o spool é a única fonte completa dos registros.
            buffer_dropped = records_written > 0

        with spool_path.open("ab") as spool:
            for endpoint_index, endpoint_spec in enumerate(endpoints):
                if endpoint_index < first_endpoint_index:
                    continue
                uf_param_name = self._select_uf_param(endpoint_spec.uf_params)
                page_start = first_page_index if endpoint_index == first_endpoint_index else 0
                if page_start >= max_pages_per_year:
                    truncated = True
                    continue

                next_page = page_start
                reached_end = False
                while next_page < max_pages_per_year and not reached_end:
                    # As páginas de uma onda são buscadas em paralelo, mas
                    # gravadas em ordem: o spool continua sequencial e o
                    # checkpoint segue significando "as N primeiras páginas
                    # estão no disco", que é o que a retomada precisa.
                    wave = list(
                        range(next_page, min(next_page + workers, max_pages_per_year))
                    )
                    fetched_pages = self._fetch_demas_wave(
                        client=client,
                        endpoint_spec=endpoint_spec,
                        pages=wave,
                        page_size=page_size,
                        uf=uf,
                        uf_param_name=uf_param_name,
                        workers=workers,
                    )

                    for page, fetched, error in fetched_pages:
                        if error is not None:
                            # O prefixo bem-sucedido já está gravado e
                            # checkpointado; a falha sobe como sempre subiu.
                            if isinstance(error, OpenDataSUSClientError):
                                raise self._annotate_client_error(
                                    error,
                                    context=(
                                        "OpenDataSUS DEMAS request failed for dataset "
                                        f"'{dataset}' at endpoint '{endpoint_spec.path}' "
                                        f"page {page + 1}"
                                    ),
                                ) from error
                            raise error
                        if not fetched:
                            reached_end = True
                            break

                        filtered_rows = self._filter_demas_rows(
                            rows=fetched,
                            start=start,
                            end=end,
                            uf=uf,
                        )
                        for row in filtered_rows:
                            spool.write(json.dumps(row, ensure_ascii=False).encode("utf-8"))
                            spool.write(b"\n")
                        spool.flush()
                        records_written += len(filtered_rows)

                        # Buffer em memória só para downloads pequenos, onde
                        # load_dataframe()/export seguem servidos sem reler o disco.
                        if not buffer_dropped:
                            records.extend(filtered_rows)
                            if len(records) > self.MAX_RECORDS_IN_MEMORY:
                                records = []
                                buffer_dropped = True

                        pages_scanned += 1
                        next_page = page + 1
                        # Checkpoint por página: o byte do spool permite truncar
                        # um write parcial na retomada, sem duplicar nem perder.
                        self._write_demas_checkpoint(
                            checkpoint_path,
                            fingerprint=fingerprint,
                            endpoint_index=endpoint_index,
                            pages_done=next_page,
                            rows_written=records_written,
                            spool_bytes=spool.tell(),
                        )

                        if progress_callback is not None:
                            page_label = f"{endpoint_spec.label}_page_{page + 1}"
                            progress_callback(
                                {
                                    "event": "file_completed",
                                    "source": dataset,
                                    "documents_total": estimated_pages_total,
                                    "document_index": pages_scanned,
                                    "file_path": page_label,
                                }
                            )

                        if len(fetched) < page_size:
                            reached_end = True
                            break

                if not reached_end:
                    truncated = True

        # A coleta terminou: o spool vira o snapshot bruto com o nome de sempre
        # (raw/<stem>.jsonl). Um download grande também promove o arquivo mesmo
        # com keep_raw=false, porque nesse caso ele é a única cópia completa.
        raw_path: Optional[Path] = None
        data_path = spool_path
        if keep_raw or buffer_dropped:
            raw_dir = self.output_path / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            data_path = raw_dir / f"{artifact_stem}.jsonl"
            spool_path.replace(data_path)
            raw_path = data_path

        self._data_by_dataset[dataset] = records
        self._spool_by_dataset[dataset] = data_path
        self._latest_dataset = dataset

        exported_files: List[str] = []
        warnings: List[str] = []
        if requested_format:
            if records_written:
                try:
                    # Downloads grandes já descartaram o buffer: a conversão lê o
                    # spool em vez da lista de dicts.
                    export_path = (
                        self._export_spool(
                            spool_path=data_path,
                            format=requested_format,
                            name=artifact_stem,
                        )
                        if buffer_dropped
                        else self.export(
                            self._records_to_dataframe(records),
                            format=requested_format,
                            name=artifact_stem,
                        )
                    )
                    exported_files.append(str(export_path))
                except Exception as exc:
                    warnings.append(
                        self._build_export_failure_warning(
                            exc=exc,
                            keep_raw=keep_raw,
                        )
                    )
            else:
                warnings.append(
                    "No records returned by OpenDataSUS query; export file was not generated. "
                    "Consider widening the date window or removing optional refinements such as UF."
                )
        elif not keep_raw:
            warnings.append(
                "No data artifact generated (keep_raw=false and output_format is empty). "
                "Set output_format or enable keep_raw."
            )

        # O spool só é descartado depois do export, e só quando o buffer em
        # memória cobriu tudo: em download grande ele é o único artefato com a
        # série completa, então apagá-lo jogaria fora o download inteiro.
        if not keep_raw:
            if buffer_dropped:
                warnings.append(
                    f"O snapshot bruto foi mantido em '{data_path}' apesar de keep_raw=false: "
                    f"o download passou de {self.MAX_RECORDS_IN_MEMORY} linhas e foi gravado "
                    "direto em disco, entao esse arquivo e a unica copia completa dos registros."
                )
            else:
                data_path.unlink(missing_ok=True)

        # Checkpoint sobrevive só a interrupções: a corrida terminou, então a
        # próxima execução recomeça do zero em vez de servir dados velhos.
        checkpoint_path.unlink(missing_ok=True)

        if truncated:
            row_cap_label = f"{max_pages_per_year * page_size:,}".replace(",", ".")
            remedy = (
                f"Use a fonte '{spec.bulk_alternative}', que baixa os arquivos completos "
                "sem paginar; subir max_pages aqui e viavel (o download escreve em disco, "
                "busca paginas em paralelo e retoma de onde parou), mas troca minutos por "
                "horas de paginacao."
                if spec.bulk_alternative
                else "Aumente max_pages — o download escreve em disco por pagina e retoma "
                "de onde parou — ou reduza a janela consultada."
            )
            warnings.append(
                "DOWNLOAD TRUNCADO: a consulta bateu no teto de max_pages antes de esgotar "
                f"as paginas remotas, entao o resultado ({records_written} linhas) e um prefixo "
                f"da fonte, nao a fonte inteira. Teto atingido: {row_cap_label} linhas por "
                f"endpoint (max_pages={max_pages_per_year} x batch_size={page_size}). "
                f"{remedy}"
            )

        endpoint_slug = ",".join([item.path.lstrip("/") for item in endpoints]) or dataset
        resolved_resource = (
            resource_id.strip()
            if resource_id and resource_id.strip()
            else f"demas:{endpoint_slug}"
        )
        manifest_path = self._write_manifest(
            dataset=dataset,
            resource_id=resolved_resource,
            start_year=start_year,
            end_year=end_year,
            start=start,
            end=end,
            effective_start=effective_start,
            effective_end=effective_end,
            uf=uf,
            total_records=records_written,
            records_downloaded=records_written,
            raw_path=raw_path,
            keep_raw=keep_raw,
            output_format=requested_format,
            exported_files=exported_files,
            api_base_url=client.base_url,
            warnings=warnings,
            extra_metadata={
                "api_mode": "demas",
                "years": years,
                "endpoints": [item.path for item in endpoints],
                "pages_scanned": pages_scanned,
                "max_pages": max_pages_per_year,
                "batch_size": page_size,
                "concurrency": workers,
                "truncated": truncated,
                "api_params": dict(api_params),
                "endpoint_query_params": [
                    {"path": item.path, "params": dict(item.query_params)}
                    for item in endpoints
                ],
            },
        )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "download_complete",
                    "source": dataset,
                    "documents_total": estimated_pages_total,
                    "downloaded_count": records_written,
                    "pages_scanned": pages_scanned,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "output_dir": str(self.output_path),
                }
            )

        payload: Dict[str, object] = {
            "documents_found": records_written,
            "downloaded_count": records_written,
            "skipped_count": 0,
            "failed_count": 0,
            "manifest_path": str(manifest_path),
            "output_dir": str(self.output_path),
            "dataset": dataset,
            "resource_id": resolved_resource,
            "start_year": start_year,
            "end_year": end_year,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "query_start_date": effective_start.isoformat(),
            "query_end_date": effective_end.isoformat(),
            "uf": uf,
            "api_base_url": client.base_url,
            "raw_file": str(raw_path) if raw_path else None,
            "keep_raw": keep_raw,
            "output_format": requested_format,
            "exported_files": exported_files,
            "api_params": dict(api_params),
            "truncated": truncated,
            "warnings": list(warnings),
            "resumed_from_rows": int(resumed_from["rows_written"]) if resumed_from else 0,
        }
        export_warning = self._combine_warnings(warnings)
        if export_warning:
            payload["export_warning"] = export_warning
        return payload

    def _fetch_demas_wave(
        self,
        *,
        client: OpenDataSUSClient,
        endpoint_spec: DemasEndpointPlan,
        pages: List[int],
        page_size: int,
        uf: Optional[str],
        uf_param_name: Optional[str],
        workers: int,
    ) -> List[tuple]:
        """Busca um lote de páginas em paralelo, devolvendo-as EM ORDEM.

        O gargalo do modo DEMAS é o tempo de resposta por request, não a banda:
        medido em 2026-09-02 no endpoint de SRAG, uma conexão rende ~200
        linhas/s e oito rendem ~1.200. Cada item volta como
        ``(page, rows, error)`` em vez de propagar a exceção na hora, para que
        o chamador consiga gravar o prefixo que deu certo antes de falhar.
        """

        def build_params(page: int) -> Dict[str, object]:
            params: Dict[str, object] = dict(endpoint_spec.query_params)
            params.update(
                {
                    "limit": page_size,
                    # DEMAS offset conta LINHAS, não páginas (o swagger diz
                    # "Número da página", mas limit=5&offset=1 sobrepõe 4 das
                    # 5 linhas de offset=0). Avançar de 1 em 1 rebaixaria a
                    # mesma janela e cobriria page_size vezes menos dados.
                    "offset": page * page_size,
                }
            )
            if uf and uf_param_name:
                params[uf_param_name] = uf
            return params

        def fetch(page: int) -> tuple:
            try:
                payload = client.demas_get(endpoint_spec.path, params=build_params(page))
            except Exception as exc:  # noqa: BLE001 - devolvido, não engolido
                return page, [], exc
            return page, self._extract_demas_rows(payload), None

        if workers <= 1 or len(pages) == 1:
            return [fetch(page) for page in pages]

        with ThreadPoolExecutor(max_workers=min(workers, len(pages))) as pool:
            return list(pool.map(fetch, pages))

    # -- spool / retomada do modo DEMAS ---------------------------------------

    def _demas_partial_dir(self) -> Path:
        partial_dir = self.output_path / "raw" / ".partial"
        partial_dir.mkdir(parents=True, exist_ok=True)
        return partial_dir

    def _demas_spool_path(self, fingerprint: str) -> Path:
        return self._demas_partial_dir() / f"{fingerprint[:16]}.jsonl"

    def _demas_checkpoint_path(self, fingerprint: str) -> Path:
        return self._demas_partial_dir() / f"{fingerprint[:16]}.checkpoint.json"

    @staticmethod
    def _demas_fingerprint(
        *,
        dataset: str,
        endpoints: List[DemasEndpointPlan],
        page_size: int,
        uf: Optional[str],
        start: Optional[date],
        end: Optional[date],
    ) -> str:
        """Identidade da consulta, para nunca retomar em cima de outra query.

        max_pages fica de fora de propósito: reexecutar com um teto maior é
        exatamente o caso em que continuar de onde parou vale a pena.
        """
        payload = json.dumps(
            {
                "dataset": dataset,
                "endpoints": [
                    {"path": item.path, "params": dict(item.query_params)} for item in endpoints
                ],
                "page_size": page_size,
                "uf": uf,
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def _write_demas_checkpoint(
        self,
        checkpoint_path: Path,
        *,
        fingerprint: str,
        endpoint_index: int,
        pages_done: int,
        rows_written: int,
        spool_bytes: int,
    ) -> None:
        checkpoint_path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "endpoint_index": endpoint_index,
                    "pages_done": pages_done,
                    "rows_written": rows_written,
                    "spool_bytes": spool_bytes,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _resume_demas_checkpoint(
        self,
        *,
        checkpoint_path: Path,
        spool_path: Path,
        fingerprint: str,
    ) -> Optional[Dict[str, object]]:
        """Retoma um download interrompido, ou começa do zero.

        Um checkpoint só existe enquanto a corrida está incompleta (o fim da
        execução o apaga), então encontrá-lo significa que a execução anterior
        morreu no meio. O spool é truncado no byte registrado para descartar
        uma página escrita pela metade.
        """
        if not checkpoint_path.exists() or not spool_path.exists():
            # Um sem o outro é lixo de execução anterior: limpa e recomeça.
            checkpoint_path.unlink(missing_ok=True)
            spool_path.unlink(missing_ok=True)
            return None

        try:
            state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            checkpoint_path.unlink(missing_ok=True)
            spool_path.unlink(missing_ok=True)
            return None

        spool_bytes = int(state.get("spool_bytes", -1))
        if state.get("fingerprint") != fingerprint or spool_bytes < 0:
            # Outra consulta escreveu ali: não dá para reaproveitar o spool.
            checkpoint_path.unlink(missing_ok=True)
            spool_path.unlink(missing_ok=True)
            return None

        if spool_path.stat().st_size > spool_bytes:
            with spool_path.open("r+b") as handler:
                handler.truncate(spool_bytes)

        return {
            "endpoint_index": int(state.get("endpoint_index", 0)),
            "pages_done": int(state.get("pages_done", 0)),
            "rows_written": int(state.get("rows_written", 0)),
        }

    @staticmethod
    def _infer_spool_schema(spool_path: Path) -> Dict[str, pl.DataType]:
        """Deduz o schema do spool numa passada de memória constante.

        A inferência por amostra do Polars não serve aqui: colunas esparsas do
        SRAG só aparecem depois de milhares de linhas, e uma coluna vista só
        como null vira dtype Null — que estoura ("got non-null value for
        NULL-typed column") assim que um valor aparece adiante. Varrer o arquivo
        inteiro guardando apenas os tipos por coluna custa O(colunas).
        """
        kinds: Dict[str, set] = {}
        with spool_path.open(encoding="utf-8") as handler:
            for line in handler:
                if not line.strip():
                    continue
                for key, value in json.loads(line).items():
                    seen = kinds.setdefault(key, set())
                    if value is None:
                        continue
                    if isinstance(value, bool):
                        seen.add("bool")
                    elif isinstance(value, int):
                        seen.add("int")
                    elif isinstance(value, float):
                        seen.add("float")
                    else:
                        seen.add("str")

        schema: Dict[str, pl.DataType] = {}
        for key, seen in kinds.items():
            if seen == {"bool"}:
                schema[key] = pl.Boolean
            elif seen == {"int"}:
                schema[key] = pl.Int64
            elif seen and seen <= {"int", "float"}:
                schema[key] = pl.Float64
            else:
                # Inclui o caso "só null": String aceita qualquer valor futuro.
                schema[key] = pl.String
        return schema

    def _export_spool(self, *, spool_path: Path, format: str, name: str) -> Path:
        """Converte o spool sem carregar o dataset inteiro na memória.

        Medido em 2026-09-02 sobre 60.000 linhas de SRAG: ler tudo de uma vez
        custa ~9,4 KB por linha (~42 GB projetados para o bloco 2019-2026),
        enquanto o sink em lotes fica em ~0,2 KB por linha (~0,8 GB).
        """
        normalized = format.strip().lower()
        if normalized not in {"csv", "parquet"}:
            # SQLite não tem sink incremental; cai no caminho eager.
            return self.export(self._read_spool_dataframe(spool_path), format=format, name=name)

        lazy = pl.scan_ndjson(
            spool_path,
            schema=self._infer_spool_schema(spool_path),
            low_memory=True,
            batch_size=self.SPOOL_STREAM_BATCH,
        )
        if normalized == "csv":
            path = self.output_path / f"{name}.csv"
            lazy.sink_csv(path)
            return path

        path = self.output_path / f"{name}.parquet"
        lazy.sink_parquet(path, row_group_size=self.SPOOL_PARQUET_ROW_GROUP)
        return path

    @staticmethod
    def _read_spool_dataframe(spool_path: Path) -> pl.DataFrame:
        # infer_schema_length=None pelo mesmo motivo de _records_to_dataframe:
        # colunas que misturam número e texto quebram a inferência por amostra.
        return pl.read_ndjson(spool_path, infer_schema_length=None)

    def _resolve_demas_endpoints(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        dataset: str,
        start_year: int,
        end_year: int,
        api_params: Mapping[str, object],
    ) -> List[DemasEndpointPlan]:
        if spec.demas_strategy == "pni_yearly":
            by_year = {item.year: item for item in self._demas_catalog}
            selected: List[DemasEndpointPlan] = []
            for year in range(start_year, end_year + 1):
                from_catalog = by_year.get(year)
                if from_catalog is not None:
                    selected.append(
                        DemasEndpointPlan(
                            path=from_catalog.path,
                            label=f"{dataset}_year_{year}",
                            uf_params=from_catalog.uf_params,
                            query_params=self._build_endpoint_query_params(
                                from_catalog.path,
                                api_params=api_params,
                            ),
                        )
                    )
                    continue
                fallback_path = f"/vacinacao/doses-aplicadas-pni-{year}"
                selected.append(
                    DemasEndpointPlan(
                        path=fallback_path,
                        label=f"{dataset}_year_{year}",
                        uf_params=self._fallback_uf_params_for_year(year),
                        query_params=self._build_endpoint_query_params(
                            fallback_path,
                            api_params=api_params,
                        ),
                    )
                )
            return selected

        if spec.demas_strategy == "yearly_suffix":
            selected: List[DemasEndpointPlan] = []
            base_path = str(spec.demas_static_path or "").strip()
            for year in range(start_year, end_year + 1):
                path = f"{base_path}-{year}"
                params = self._demas_get_params_by_path.get(path, ())
                uf_params = tuple(
                    item for item in params if item in self._candidate_uf_param_names()
                )
                selected.append(
                    DemasEndpointPlan(
                        path=self._resolve_path_template(path, api_params=api_params),
                        label=f"{dataset}_year_{year}",
                        uf_params=uf_params,
                        query_params=self._build_endpoint_query_params(
                            path,
                            api_params=api_params,
                        ),
                    )
                )
            return selected

        if spec.demas_strategy == "block_ranges":
            # Specialized for SRAG blocks: 2009-2012, 2013-2018, 2019-2026
            blocks = self.SRAG_BLOCKS
            selected: List[DemasEndpointPlan] = []
            base_path = str(spec.demas_static_path or "").strip()
            
            # Find which blocks overlap with [start_year, end_year]
            for b_start, b_end, b_label in blocks:
                if max(start_year, b_start) <= min(end_year, b_end):
                    path = f"{base_path}-{b_label}"
                    params = self._demas_get_params_by_path.get(path, ())
                    uf_params = tuple(
                        item for item in params if item in self._candidate_uf_param_names()
                    )
                    selected.append(
                        DemasEndpointPlan(
                            path=self._resolve_path_template(path, api_params=api_params),
                            label=f"{dataset}_block_{b_label}",
                            uf_params=uf_params,
                            query_params=self._build_endpoint_query_params(
                                path,
                                api_params=api_params,
                            ),
                        )
                    )
            return selected

        path = str(spec.demas_static_path or "").strip()
        if not path.startswith("/"):
            path = f"/{path}"
        params = self._demas_get_params_by_path.get(path, ())
        uf_params = tuple(
            item for item in params if item in self._candidate_uf_param_names()
        )
        endpoint_path = self._resolve_path_template(path, api_params=api_params)
        query_params = self._build_endpoint_query_params(path, api_params=api_params)
        if "nu_ano" in params:
            if "nu_ano" in query_params:
                return [
                    DemasEndpointPlan(
                        path=endpoint_path,
                        label=dataset,
                        uf_params=uf_params,
                        query_params=query_params,
                    )
                ]
            return [
                DemasEndpointPlan(
                    path=endpoint_path,
                    label=f"{dataset}_year_{year}",
                    uf_params=uf_params,
                    query_params={**query_params, "nu_ano": year},
                )
                for year in range(start_year, end_year + 1)
            ]

        return [
            DemasEndpointPlan(
                path=endpoint_path,
                label=dataset,
                uf_params=uf_params,
                query_params=query_params,
            )
        ]

    def _build_endpoint_query_params(
        self,
        path_template: str,
        *,
        api_params: Mapping[str, object],
    ) -> Dict[str, object]:
        swagger_params = set(self._demas_get_params_by_path.get(path_template, ()))
        path_params = set(self._extract_path_param_names(path_template))
        ignored = {"limit", "offset"} | path_params
        query: Dict[str, object] = {}
        for key, value in api_params.items():
            if key in ignored:
                continue
            if swagger_params and key not in swagger_params:
                continue
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            query[key] = value
        return query

    def _resolve_path_template(
        self,
        path_template: str,
        *,
        api_params: Mapping[str, object],
    ) -> str:
        path = path_template if path_template.startswith("/") else f"/{path_template}"
        for name in self._extract_path_param_names(path):
            value = api_params.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(
                    f"Parameter '{name}' is required for OpenDataSUS endpoint '{path_template}'."
                )
            path = path.replace("{" + name + "}", quote(str(value).strip(), safe=""))
        return path

    @staticmethod
    def _extract_path_param_names(path_template: str) -> tuple[str, ...]:
        return tuple(re.findall(r"{([^{}]+)}", path_template))

    @staticmethod
    def _normalize_demas_api_params(api_params: Mapping[str, object]) -> Dict[str, object]:
        normalized: Dict[str, object] = {}
        for key, value in api_params.items():
            if value is None:
                continue
            clean_key = str(key).strip()
            if not clean_key:
                continue
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    continue
                if clean_key in OpenDataSUSDataSource._candidate_uf_param_names():
                    cleaned = cleaned.upper()
                normalized[clean_key] = cleaned
                continue
            normalized[clean_key] = value
        return normalized

    def _try_build_generic_spec(self, dataset_key: str) -> Optional[OpenDataSUSDatasetSpec]:
        """Try to build a generic spec by matching the dataset key to a Swagger path.

        The dataset key typically mirrors the API path with slashes replaced by
        underscores (e.g. ``"cnes/estabelecimentos"`` or
        ``"cnes_estabelecimentos"``).  We attempt multiple candidate paths and
        return a static-endpoint spec if one matches.
        """

        # Build candidate paths from the dataset key.
        # The registry uses the raw path as fixed_dataset (e.g. "cnes/estabelecimentos")
        # and the source name uses underscores (e.g. "cnes_estabelecimentos").
        candidates: list[str] = []

        # Candidate 1: treat the dataset key itself as the path (e.g. "cnes/estabelecimentos")
        raw_path = "/" + dataset_key.lstrip("/")
        candidates.append(raw_path)

        # Candidate 2: replace underscores with hyphens and slashes
        # e.g. "sisagua_vigilancia_parametros_basicos" -> try common patterns
        hyphenated = "/" + dataset_key.replace("_", "-")
        candidates.append(hyphenated)

        # Candidate 3: try splitting at the first underscore -> "sisagua/vigilancia-parametros-basicos"
        parts = dataset_key.split("_", 1)
        if len(parts) == 2:
            candidates.append(f"/{parts[0]}/{parts[1].replace('_', '-')}")

        # Candidate 4: try splitting at the second underscore for deeper nesting
        # e.g. "saude_indigena_siasi_modulo_saude_bucal_ficha3"
        # -> "/saude-indigena/siasi-modulo-saude-bucal-ficha3"
        parts2 = dataset_key.split("_", 2)
        if len(parts2) == 3:
            prefix = f"{parts2[0]}-{parts2[1]}"
            suffix = parts2[2].replace("_", "-")
            candidates.append(f"/{prefix}/{suffix}")

        known_paths = set(self._demas_get_params_by_path.keys())

        for candidate in candidates:
            if candidate in known_paths:
                return OpenDataSUSDatasetSpec(
                    package_id=f"generic-{dataset_key}",
                    preferred_resource_terms=(dataset_key,),
                    date_column="",    # no local date filtering for generic sources
                    uf_column="",      # UF is handled via API query params
                    demas_strategy="static",
                    demas_static_path=candidate,
                    ckan_supported=False,
                )

        return None

    @staticmethod
    def _fallback_uf_params_for_year(year: int) -> tuple[str, ...]:
        if year == 2020:
            return ("uf_estabelecimento", "uf_paciente")
        if year in {2021, 2023}:
            return ("uf_estabelecimento",)
        if year == 2022:
            return ("uf_paciente",)
        return ()

    @staticmethod
    def _select_uf_param(uf_params: tuple[str, ...]) -> Optional[str]:
        if not uf_params:
            return None
        if "uf_estabelecimento" in uf_params:
            return "uf_estabelecimento"
        if "uf_paciente" in uf_params:
            return "uf_paciente"
        if "uf" in uf_params:
            return "uf"
        return None

    @staticmethod
    def _candidate_uf_param_names() -> tuple[str, ...]:
        return (
            "uf",
            "sg_uf",
            "sg_uf_not",
            "uf_notificacao",
            "uf_residencia",
            "uf_paciente",
            "uf_estabelecimento",
        )

    @staticmethod
    def _extract_demas_rows(payload: Mapping[str, object]) -> List[Dict[str, object]]:
        for value in payload.values():
            if isinstance(value, list):
                rows: List[Dict[str, object]] = []
                for item in value:
                    if isinstance(item, Mapping):
                        rows.append({str(key): item_value for key, item_value in item.items()})
                return rows
        return []

    def _filter_demas_rows(
        self,
        *,
        rows: List[Dict[str, object]],
        start: Optional[date],
        end: Optional[date],
        uf: Optional[str],
    ) -> List[Dict[str, object]]:
        accepted: List[Dict[str, object]] = []
        for row in rows:
            if start is not None or end is not None:
                row_date = self._extract_record_date(row)
                if row_date is None:
                    continue
                if start is not None and row_date < start:
                    continue
                if end is not None and row_date > end:
                    continue

            if uf is not None:
                row_uf = self._extract_record_uf(row)
                if row_uf != uf:
                    continue

            accepted.append(row)
        return accepted

    @staticmethod
    def _extract_record_date(row: Mapping[str, object]) -> Optional[date]:
        candidates = [
            "data_vacina",
            "vacina_dataAplicacao",
            "data_aplicacao",
            "dataAplicacao",
            "dt_notific",
            "dt_sin_pri",
            "dt_invest",
            "dt_digita",
            "dt_is",
        ]
        for key in candidates:
            raw_value = row.get(key)
            if raw_value is None:
                continue
            text = str(raw_value).strip()
            if len(text) < 10:
                continue
            candidate = text[:10]
            try:
                return datetime.strptime(candidate, "%Y-%m-%d").date()
            except ValueError:
                pass
            try:
                return datetime.strptime(candidate, "%d/%m/%Y").date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_record_uf(row: Mapping[str, object]) -> Optional[str]:
        uf_fields = [
            "sigla_uf_estabelecimento",
            "uf_estabelecimento",
            "estabelecimento_uf",
            "sigla_uf_paciente",
            "uf_paciente",
            "paciente_endereco_uf",
            "sg_uf_not",
            "sg_uf",
            "sg_uf_resi",
            "uf_lpi",
        ]
        numeric_to_uf = {
            "11": "RO",
            "12": "AC",
            "13": "AM",
            "14": "RR",
            "15": "PA",
            "16": "AP",
            "17": "TO",
            "21": "MA",
            "22": "PI",
            "23": "CE",
            "24": "RN",
            "25": "PB",
            "26": "PE",
            "27": "AL",
            "28": "SE",
            "29": "BA",
            "31": "MG",
            "32": "ES",
            "33": "RJ",
            "35": "SP",
            "41": "PR",
            "42": "SC",
            "43": "RS",
            "50": "MS",
            "51": "MT",
            "52": "GO",
            "53": "DF",
        }
        for field in uf_fields:
            value = row.get(field)
            if value is None:
                continue
            cleaned = str(value).strip().upper()
            if len(cleaned) == 2 and cleaned.isalpha():
                return cleaned
            mapped = numeric_to_uf.get(cleaned)
            if mapped:
                return mapped
        return None

    @staticmethod
    def _records_to_dataframe(records: List[Dict[str, object]]) -> pl.DataFrame:
        # Scan all rows to avoid schema mismatch when columns mix numeric/text values.
        return pl.from_dicts(records, infer_schema_length=None)

    def _count_records(
        self,
        *,
        client: OpenDataSUSClient,
        resource_id: str,
        where_clauses: List[str],
    ) -> int:
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = (
            f"SELECT COUNT(*) AS total FROM {self._quote_identifier(resource_id)} "
            f"WHERE {where_sql}"
        )
        try:
            result = client.datastore_search_sql(sql)
        except OpenDataSUSClientError as exc:
            raise self._annotate_client_error(
                exc,
                context=(
                    "OpenDataSUS CKAN count query failed for "
                    f"resource '{resource_id}'"
                ),
            ) from exc
        records = result.get("records")
        if not isinstance(records, list) or not records:
            return 0
        first = records[0]
        if not isinstance(first, Mapping):
            return 0
        raw_total = first.get("total")
        try:
            return max(0, int(raw_total))
        except (TypeError, ValueError):
            return 0

    def _fetch_records(
        self,
        *,
        client: OpenDataSUSClient,
        resource_id: str,
        date_column: str,
        where_clauses: List[str],
        limit: int,
        offset: int,
    ) -> List[Dict[str, object]]:
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = (
            f"SELECT * FROM {self._quote_identifier(resource_id)} "
            f"WHERE {where_sql} "
            f"ORDER BY {self._quote_identifier(date_column)} ASC "
            f"LIMIT {max(1, int(limit))} OFFSET {max(0, int(offset))}"
        )
        try:
            result = client.datastore_search_sql(sql)
        except OpenDataSUSClientError as exc:
            raise self._annotate_client_error(
                exc,
                context=(
                    "OpenDataSUS CKAN page query failed for "
                    f"resource '{resource_id}' at offset {max(0, int(offset))}"
                ),
            ) from exc
        rows = result.get("records")
        if not isinstance(rows, list):
            return []

        normalized: List[Dict[str, object]] = []
        for item in rows:
            if isinstance(item, Mapping):
                normalized.append({str(key): value for key, value in item.items()})
        return normalized

    def _build_where_clauses(
        self,
        *,
        spec: OpenDataSUSDatasetSpec,
        start: date,
        end: date,
        uf: Optional[str],
    ) -> List[str]:
        clauses = [
            f"{self._quote_identifier(spec.date_column)} >= {self._quote_literal(start.isoformat())}",
            f"{self._quote_identifier(spec.date_column)} <= {self._quote_literal(end.isoformat())}",
        ]
        if uf:
            clauses.append(
                f"UPPER({self._quote_identifier(spec.uf_column)}) = {self._quote_literal(uf)}"
            )
        return clauses

    def _build_artifact_stem(
        self,
        *,
        dataset: str,
        start: date,
        end: date,
        uf: Optional[str],
    ) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        uf_suffix = uf or "ALL"
        safe_dataset = dataset.replace("/", "_")
        return f"{safe_dataset}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{uf_suffix}_{timestamp}"

    def _write_raw_snapshot(self, *, stem: str, records: List[Dict[str, object]]) -> Path:
        raw_dir = self.output_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        file_path = raw_dir / f"{stem}.jsonl"
        with file_path.open("w", encoding="utf-8") as handler:
            for item in records:
                handler.write(json.dumps(item, ensure_ascii=False))
                handler.write("\n")
        return file_path

    def _write_manifest(
        self,
        *,
        dataset: str,
        resource_id: str,
        start_year: int,
        end_year: int,
        start: Optional[date],
        end: Optional[date],
        effective_start: date,
        effective_end: date,
        uf: Optional[str],
        total_records: int,
        records_downloaded: int,
        raw_path: Optional[Path],
        keep_raw: bool,
        output_format: Optional[str],
        exported_files: List[str],
        api_base_url: str,
        warnings: Optional[List[str]] = None,
        extra_metadata: Optional[Mapping[str, object]] = None,
    ) -> Path:
        manifest_path = self.output_path / "manifest.json"
        
        request_filters = {
            "dataset": dataset,
            "resource_id": resource_id,
            "start_year": start_year,
            "end_year": end_year,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "query_start_date": effective_start.isoformat(),
            "query_end_date": effective_end.isoformat(),
            "uf": uf,
            "keep_raw": keep_raw,
            "output_format": output_format,
            "api_base_url": api_base_url,
        }
        
        if extra_metadata:
            request_filters.update(extra_metadata)
            
        materialized_paths = []
        if raw_path:
            materialized_paths.append(str(raw_path))

        manifest = DownloadManifest(
            source=dataset,
            filters=request_filters,
            documents_found=total_records,
            downloaded_files=[],  # tracked as bulk materialized paths
            materialized_paths=materialized_paths,
            exported_files=list(exported_files),
            warnings=list(warnings or []),
        )
        
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    @staticmethod
    def _annotate_client_error(
        exc: OpenDataSUSClientError,
        *,
        context: str,
    ) -> OpenDataSUSClientError:
        return exc.with_context(context)

    @staticmethod
    def _combine_warnings(warnings: List[str]) -> Optional[str]:
        cleaned = [item.strip() for item in warnings if str(item).strip()]
        if not cleaned:
            return None
        return " ".join(cleaned)

    @staticmethod
    def _build_export_failure_warning(
        *,
        exc: Exception,
        keep_raw: bool,
    ) -> str:
        if keep_raw:
            artifact_note = "Raw snapshot and manifest were generated."
        else:
            artifact_note = (
                "Manifest was generated, but no data artifact was preserved. "
                "Re-run with keep_raw=true to retain the raw payload."
            )
        return (
            "OpenDataSUS export failed after download. "
            f"{artifact_note} Error: {exc}"
        )

    @staticmethod
    def _parse_iso_date(value: str, *, field_name: str) -> date:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"Parameter '{field_name}' must use date format YYYY-MM-DD."
            ) from exc

    def _parse_optional_iso_date(self, value: Optional[str], *, field_name: str) -> Optional[date]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return self._parse_iso_date(cleaned, field_name=field_name)

    @staticmethod
    def _normalize_year_window(
        *,
        start_year: Optional[int],
        end_year: Optional[int],
    ) -> tuple[int, int]:
        default_year = datetime.utcnow().year - 1
        start_value = int(start_year if start_year is not None else default_year)
        end_value = int(end_year if end_year is not None else start_value)
        if start_value > end_value:
            raise ValueError("Parameter 'start_year' cannot be greater than 'end_year'.")
        if start_value < 1900:
            raise ValueError("Parameter 'start_year' must be >= 1900.")
        return start_value, end_value

    @staticmethod
    def _normalize_uf(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            return None
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("Parameter 'uf' must be a two-letter UF code (e.g., SP).")
        return cleaned

    @staticmethod
    def _normalize_output_format(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        if cleaned not in {"csv", "parquet", "sqlite"}:
            raise ValueError(
                f"Unsupported output format '{value}'. Allowed: csv, parquet, sqlite"
            )
        return cleaned

    @staticmethod
    def _quote_identifier(value: str) -> str:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
