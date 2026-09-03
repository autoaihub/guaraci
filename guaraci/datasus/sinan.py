"""
Guaraci DATASUS SINAN Integration
================================

Enhanced module for downloading, processing, and exporting SINAN data via PySUS 2.x.
Includes error handling and performance optimizations.
"""

import os
import asyncio
import sqlite3
import datetime
from typing import Optional, Literal, List, Dict, Any, Callable, Sequence
from pathlib import Path
from collections import defaultdict

import polars as pl
from tqdm import tqdm
from loguru import logger

from guaraci.core.datasource import DataSource
from guaraci.datasus.backend import (
    BACKEND_FTP as _BACKEND_FTP,
    get_datasus_backend as _get_datasus_backend,
)
from guaraci.utils.mapping import UF_DICT

try:
    import pysus
    from pysus.api.client import PySUS
    PYSUS_AVAILABLE = True
except ImportError as exc:
    import logging
    logging.getLogger(__name__).warning(f"PySUS não está disponível ou falhou ao importar: {exc}")
    PYSUS_AVAILABLE = False


class SinanDataSource(DataSource):
    """Enhanced SINAN data source with error handling (PySUS 2.x)."""

    NEGLECTED_DISEASES = ['ANIM', 'CHAG', 'CHIK', 'DENG', 'ESQU', 'HANS', 'LEIV', 'LTAN', 'RAIV']
    
    DISEASE_NAMES = {
        'ANIM': 'Acidentes por Animais Peçonhentos',
        'CHAG': 'Doença de Chagas',
        'CHIK': 'Chikungunya',
        'DENG': 'Dengue',
        'ESQU': 'Esquistossomose',
        'HANS': 'Hanseníase',
        'LEIV': 'Leishmaniose Visceral',
        'LTAN': 'Leishmaniose Tegumentar',
        'RAIV': 'Raiva Humana'
    }

    def __init__(self, output_path: Optional[str] = None):
        super().__init__(name="sinan", output_path=output_path)
        self.data: Dict[str, List[Any]] = defaultdict(list)
        
        if not PYSUS_AVAILABLE:
            logger.warning(
                "PySUS is not installed. SINAN functionality will be limited. "
                "Install with: pip install 'guaraci[datasus]'"
            )
        
    @property
    def sinan(self):
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for SINAN functionality.")
        return True

    def download(
        self,
        start_year: int,
        end_year: int,
        diseases: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        backend = _get_datasus_backend()

        if diseases is None:
            diseases = self.NEGLECTED_DISEASES.copy()

        current_year = datetime.datetime.now().year
        if end_year > current_year:
            logger.warning(f"End year {end_year} is in the future; adjusted to {current_year}")
            end_year = current_year
        elif end_year == current_year:
            logger.info(
                f"Collecting current year ({current_year}); SINAN data may be partial "
                f"due to DATASUS publication lag"
            )

        if start_year > end_year:
            raise ValueError(f"Start year ({start_year}) cannot be greater than end year ({end_year})")

        years = list(range(start_year, end_year + 1))

        logger.info(f"Starting SINAN download: {start_year}-{end_year} (backend={backend})")
        logger.info(f"Diseases: {', '.join([f'{d} ({self.DISEASE_NAMES.get(d, d)})' for d in diseases])}")

        if backend == _BACKEND_FTP:
            return self._download_via_ftp(
                years=years,
                diseases=diseases,
                progress_callback=progress_callback,
            )

        return self._download_via_pysus(
            years=years,
            diseases=diseases,
            progress_callback=progress_callback,
        )

    def _download_via_pysus(
        self,
        *,
        years: List[int],
        diseases: List[str],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        if not PYSUS_AVAILABLE:
            raise ImportError("PySUS is required for the 'pysus' backend.")

        async def _fetch():
            successful = 0
            failed_downloads = []

            async with PySUS() as client:
                files_to_download = []
                for g in diseases:
                    for y in years:
                        try:
                            res = await client.query(dataset="sinan", group=g, year=y)
                            if res:
                                files_to_download.extend(res)
                        except Exception as exc:
                            logger.error(f"Failed to query SINAN {g} {y}: {exc}")
                
                total_files = len(files_to_download)
                if total_files == 0:
                    logger.warning("No files found for the specified criteria")
                    return {"successful_downloads": 0, "failed_downloads": [], "total_files": 0}
                    
                logger.info(f"Found {total_files} files to download")
                if progress_callback:
                    progress_callback(0, total_files)

                completed_downloads = 0
                for file_record in files_to_download:
                    try:
                        g_name = file_record.group.name if hasattr(file_record, "group") and file_record.group else "UNKNOWN"
                    except Exception:
                        g_name = "UNKNOWN"

                    try:
                        downloaded = await client.download(file_record)
                        self.data[g_name].append(str(downloaded.path))
                        successful += 1
                    except Exception as exc:
                        logger.error(f"Failed to download {file_record}: {exc}")
                        failed_downloads.append((g_name, str(file_record)))
                    finally:
                        completed_downloads += 1
                        if progress_callback:
                            progress_callback(completed_downloads, total_files)

                return {
                    "successful_downloads": successful,
                    "failed_downloads": failed_downloads,
                    "total_files": total_files,
                }

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
                
            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(_fetch())
            else:
                return asyncio.run(_fetch())
        except Exception as exc:
            logger.error(f"SINAN download process failed: {exc}")
            raise

    def _download_via_ftp(
        self,
        *,
        years: List[int],
        diseases: List[str],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        """Direct FTP backend (phase 3 of PLANO_DATASUS_FTP_DIRETO)."""
        from guaraci.datasus.ftp import sinan_backend as ftp_sinan

        cache_dir = self._ftp_cache_dir()
        try:
            result = ftp_sinan.download_sinan(
                years=years,
                diseases=diseases,
                cache_dir=cache_dir,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.error(f"SINAN FTP download process failed: {exc}")
            raise

        paths_by_group: Dict[str, List[str]] = result.pop("paths_by_group", {})
        for disease, paths in paths_by_group.items():
            self.data[disease].extend(paths)
        return result

    def _ftp_cache_dir(self) -> Path:
        """Where the FTP backend stores .dbc downloads and the .parquet output.

        Honours ``GUARACI_FTP_CACHE_DIR`` when set so tests and users can
        point the cache at a tmp directory without touching the user-facing
        export folder.
        """
        explicit = os.environ.get("GUARACI_FTP_CACHE_DIR")
        path = Path(explicit) if explicit else Path(self.output_path) / ".cache_ftp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def scan_dataframe(self, disease: str) -> pl.LazyFrame:
        """Plano lazy sobre os parquets baixados de ``disease``.

        Nada é lido aqui: o consumidor decide se materializa
        (:meth:`load_dataframe`) ou se escreve em streaming
        (:meth:`export`). É esse segundo caminho que permite exportar
        vários anos de uma doença sem exigir todos eles na memória ao mesmo
        tempo.
        """
        if disease not in self.data:
            raise ValueError(f"Disease {disease} not found. Run download() first.")

        parquet_sets = [str(path) for path in self.data[disease]]
        if not parquet_sets:
            logger.warning(f"No data found for {disease}")
            return pl.LazyFrame()

        logger.info(f"Planning {len(parquet_sets)} parquet files for {disease}")

        try:
            # Os arquivos anuais do SINAN não têm o mesmo conjunto de colunas
            # (o formulário muda entre anos), e a divergência é nos dois
            # sentidos: um ano pode ter colunas que o outro não tem. Um scan
            # único exigiria schema comum, então cada arquivo entra como seu
            # próprio plano e o `diagonal_relaxed` faz a união, preservando a
            # semântica do antigo concat(how="diagonal") sem sair do lazy.
            plans = [pl.scan_parquet(path) for path in parquet_sets]
            lf = plans[0] if len(plans) == 1 else pl.concat(plans, how="diagonal_relaxed")
        except Exception as exc:
            logger.warning(
                f"Lazy scan unavailable for {disease} ({exc}); falling back to eager concat"
            )
            return self._eager_concat(disease, parquet_sets).lazy()

        uf_columns = self._uf_columns(lf.collect_schema().names())
        if uf_columns:
            lf = lf.with_columns([self._uf_mapping_expr(col) for col in uf_columns])
        return lf

    def _eager_concat(self, disease: str, parquet_sets: Sequence[str]) -> pl.DataFrame:
        """Caminho de reserva: lê cada parquet e concatena em memória.

        Mantido para os casos em que o scan lazy não reconcilia os schemas.
        Exige todos os anos residentes ao mesmo tempo, então é usado apenas
        como fallback.
        """
        combined_dfs = []
        with tqdm(total=len(parquet_sets), desc=f"Loading {disease}", unit="file") as pbar:
            for filepath in parquet_sets:
                try:
                    df = pl.read_parquet(filepath)
                    combined_dfs.append(self._apply_uf_mapping(df))
                except Exception as e:
                    logger.error(f"Failed to process parquet file {filepath}: {e}")
                finally:
                    pbar.update(1)

        if not combined_dfs:
            logger.warning(f"No valid data found for {disease}")
            return pl.DataFrame()
        return pl.concat(combined_dfs, how="diagonal")

    def _load_as_polars(self, disease: str) -> pl.DataFrame:
        combined = self.scan_dataframe(disease).collect()
        if combined.height == 0:
            logger.warning(f"No valid data found for {disease}")
            return combined
        logger.info(
            f"✅ {disease}: {len(combined)} records loaded, {len(combined.columns)} columns"
        )
        return combined

    # Códigos IBGE ("35") e siglas ("SP") resolvem para a mesma sigla; o
    # mapa cobre as duas grafias de uma vez para o `replace_strict` abaixo.
    _UF_LOOKUP: Dict[str, str] = {
        **{str(code): sigla for code, sigla in UF_DICT.items()},
        **{sigla: sigla for sigla in UF_DICT.values()},
    }

    @classmethod
    def _uf_mapping_expr(cls, col: str) -> pl.Expr:
        """Expressão que normaliza uma coluna de UF para a sigla.

        Substitui o antigo ``map_elements`` com callback Python, que fazia
        ``import pandas`` e ``pd.isna`` uma vez por linha: em milhões de
        registros isso dominava o tempo de processamento. Valores não
        reconhecidos (incluindo os sentinelas ``0``/``NAN``/``NULL``) viram
        nulo, como antes.
        """
        normalized = (
            pl.col(col)
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_uppercase()
        )
        # "35.0" chega assim quando a coluna foi lida como float; o corte da
        # parte decimal reproduz o antigo int(float(valor)).
        normalized = normalized.str.replace(r"\.0+$", "")
        return (
            normalized.replace_strict(cls._UF_LOOKUP, default=None)
            .cast(pl.Utf8)
            .alias(col)
        )

    @staticmethod
    def _uf_columns(columns: Sequence[str]) -> List[str]:
        return [col for col in columns if "UF" in col.upper()]

    def _apply_uf_mapping(self, df: pl.DataFrame) -> pl.DataFrame:
        for col in self._uf_columns(df.columns):
            try:
                df = df.with_columns([self._uf_mapping_expr(col)])
            except Exception as e:
                logger.warning(f"Failed to apply UF mapping to column {col}: {e}")
        return df

    def load_dataframe(self, disease: str) -> pl.DataFrame:
        return self._load_as_polars(disease)

    @staticmethod
    def _columns_of(df: Any) -> List[str]:
        """Nomes das colunas de um DataFrame ou LazyFrame."""
        if isinstance(df, pl.LazyFrame):
            return df.collect_schema().names()
        return list(df.columns)

    def filter(
        self,
        df: Optional[pl.DataFrame] = None,
        uf: Optional[str] = None,
        municipio: Optional[str] = None,
        sexo: Optional[str] = None,
        faixa_etaria: Optional[str] = None,
        evolucao: Optional[str] = None,
        classificacao: Optional[str] = None,
        ano: Optional[int] = None,
    ) -> pl.DataFrame:
        if df is None:
            raise ValueError("É necessário fornecer um DataFrame para filtragem.")

        conditions: List[pl.Expr] = []
        available = self._columns_of(df)

        def resolve_column(options: List[str]) -> Optional[str]:
            for candidate in options:
                if candidate in available:
                    return candidate
            return None

        uf_col = resolve_column(["UF", "SG_UF", "SG_UF_NOT"])
        if uf and uf_col:
            conditions.append(pl.col(uf_col) == uf)

        municipio_col = resolve_column(["ID_MN_RESI", "ID_MUNICIP"])
        if municipio and municipio_col:
            conditions.append(
                pl.col(municipio_col).cast(pl.Utf8).str.contains(municipio, literal=True, strict=False)
            )

        sexo_col = resolve_column(["CS_SEXO"])
        if sexo and sexo_col:
            conditions.append(pl.col(sexo_col) == sexo)

        faixa_col = resolve_column(["NU_IDADE_N"])
        if faixa_etaria and faixa_col:
            conditions.append(pl.col(faixa_col) == faixa_etaria)

        evolucao_col = resolve_column(["CS_EVOLU", "EVOLUCAO"])
        if evolucao and evolucao_col:
            conditions.append(pl.col(evolucao_col) == evolucao)

        classificacao_col = resolve_column(["CLASSI_FIN", "CLASSIFICAC"])
        if classificacao and classificacao_col:
            conditions.append(pl.col(classificacao_col) == classificacao)

        ano_col = resolve_column(["NU_ANO", "ANO", "ANO_NOT"])
        if ano and ano_col:
            conditions.append(pl.col(ano_col) == ano)

        if not conditions:
            return df

        combined = conditions[0]
        for condition in conditions[1:]:
            combined = combined & condition

        return df.filter(combined)

    def summary(self, df: pl.DataFrame, by: str = "UF", metric: Literal["count", "mean", "sum"] = "count") -> pl.DataFrame:
        if by not in df.columns:
            raise ValueError(f"A coluna '{by}' não existe no DataFrame.")
        if metric == "count":
            return df.group_by(by).len().sort(by)
        elif metric == "mean":
            return df.group_by(by).mean().sort(by)
        elif metric == "sum":
            return df.group_by(by).sum().sort(by)
        else:
            raise ValueError("metric deve ser 'count', 'mean' ou 'sum'.")

    def export(
        self,
        df: pl.DataFrame | pl.LazyFrame,
        format: Literal["csv", "sqlite", "parquet"] = "csv",
        name: str = "output",
    ) -> Optional[Path]:
        """Escreve o conjunto no formato pedido.

        Aceita tanto um ``DataFrame`` já materializado quanto um
        ``LazyFrame``. No segundo caso, ``csv`` e ``parquet`` são escritos em
        streaming (``sink_*``), de modo que o pico de memória não acompanha o
        tamanho do conjunto. ``sqlite`` não tem escrita incremental
        equivalente aqui e materializa o plano antes de gravar.
        """
        if df is None:
            logger.warning(f"Nenhum dado disponível para exportar: {name}")
            return None

        is_lazy = isinstance(df, pl.LazyFrame)
        if not is_lazy and len(df) == 0:
            logger.warning(f"Nenhum dado disponível para exportar: {name}")
            return None

        output_dir = Path(self.output_path)
        final_stem = name
        columns = self._columns_of(df)

        if "_" in name:
            partes = name.split("_")
            if len(partes) >= 3 and partes[-2].isdigit() and partes[-1].isdigit():
                start_year, end_year = int(partes[-2]), int(partes[-1])
                if "NU_ANO" in columns:
                    if is_lazy:
                        raw_years = (
                            df.select(pl.col("NU_ANO").unique())
                            .collect()
                            .to_series()
                            .to_list()
                        )
                    else:
                        raw_years = df["NU_ANO"].unique().to_list()
                    present_years = {
                        int(str(value).strip())
                        for value in raw_years
                        if str(value).strip().isdigit()
                    }
                    expected_years = set(range(start_year, end_year + 1))
                    if not expected_years.issubset(present_years):
                        final_stem = f"{name}_partial"
                        logger.warning(
                            f"O intervalo declarado ({start_year}-{end_year}) não corresponde aos dados reais ({sorted(present_years) or raw_years}). "
                            f"O arquivo foi salvo como '{final_stem}.{format}'."
                        )

        final_path = output_dir / f"{final_stem}.{format}"

        if format == "csv":
            if is_lazy:
                df.sink_csv(final_path)
            else:
                df.write_csv(final_path)
        elif format == "parquet":
            if is_lazy:
                df.sink_parquet(final_path)
            else:
                df.write_parquet(final_path)
        elif format == "sqlite":
            frame = df.collect() if is_lazy else df
            if len(frame) == 0:
                logger.warning(f"Nenhum dado disponível para exportar: {name}")
                return None
            db_path = output_dir / f"{final_stem}.db"
            con = sqlite3.connect(db_path)
            frame.to_pandas().to_sql(name=final_stem, con=con, if_exists="replace", index=False)
            con.close()
        else:
            raise ValueError("Formato inválido. Escolha entre 'csv', 'sqlite' ou 'parquet'.")

        logger.info(f"Exported dataset -> {final_path}")
        return final_path

    def export_per_year(self, disease: str, format: str = "csv"):
        if disease not in self.data or not self.data[disease]:
            logger.warning(f"Nenhum arquivo disponível para {disease}.")
            return

        paths = []
        for p in self.data[disease]:
            if isinstance(p, (str, Path)) and os.path.exists(p):
                paths.append(str(p))

        if not paths:
            logger.warning(f"Nenhum caminho de arquivo válido encontrado para {disease}.")
            return

        successful_years = sorted({Path(p).stem[-4:] for p in paths if Path(p).stem[-4:].isdigit()})

        if not successful_years:
            logger.warning(f"Nenhum ano válido encontrado para {disease}.")
            return

        for year in successful_years:
            try:
                df = self.load_dataframe(disease)
                if "NU_ANO" in df.columns:
                    df = df.filter(pl.col("NU_ANO") == int(year))

                output_name = f"{disease}_{year}"
                exported_path = self.export(df, format=format, name=output_name)
                if exported_path:
                    logger.info(f"Exported {disease} {year} -> {exported_path.name} ({len(df)} registros)")
                else:
                    logger.warning(f"Export skipped for {disease} {year}: no data")

            except Exception as e:
                logger.error(f"Failed to export {disease} {year}: {e}")

    def describe_fields(self, disease: str) -> list[str]:
        df = self.load_dataframe(disease)
        return df.columns
