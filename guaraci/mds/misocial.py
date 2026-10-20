"""MI Social (Matriz de Informação Social, MDS/SAGI) pela API Solr.

A SAGI publica os agregados municipais mensais do Bolsa Família, do Cadastro
Único, do BPC, do SUAS e das condicionalidades num Solr exposto em
``aplicacoes.mds.gov.br/sagi/servicos/misocial/`` (sem cadastro nem chave). O
VIS DATA 3 é só a interface sobre essa mesma base. O host novo,
``aplicacoes.cidadania.gov.br``, responde 302, por isso o padrão é o antigo.

Verificado ao vivo em 2026-10-20: um documento por município (código IBGE de 6
dígitos) e mês, de 200301 a 202612, 5.571 municípios por mês. Os meses que ainda
não saíram já existem como documentos com quase tudo zerado (202612 traz
``bpc_ben_i=0``), e cada sistema publica num ritmo (em 202609 o BPC ainda vinha
zerado). Por isso o mês sem nenhum valor diferente de zero nos campos pedidos
sai do CSV e entra no aviso, e meses posteriores ao mês corrente nem são pedidos.

Transporte: um POST por mês com ``fq=anomes_s:AAAAMM``, ``fl`` com a lista
congelada de :mod:`guaraci.mds.campos` e ``wt=csv``. O POST é obrigatório, pois a
lista inteira passa de 50 mil caracteres e o GET dá 414. ``fl=*`` também não
serve: devolve o esquema dinâmico inteiro e, no CSV, linhas quebradas. O custo
cresce com o número de campos: o mês com todos os grupos leva cerca de 50 s e
15 MB, e só o grupo ``bpc`` cabe num ano inteiro em 8 s. O HEAD não traz
``Last-Modified`` nem ``Content-Length``, então não há "não baixar de novo".

Saída: um CSV UTF-8 com os campos de identificação e os campos de dado dos
grupos pedidos, nomes como o Solr publica e valores como texto, do jeito que
vieram. Campo ausente no mês fica vazio.
"""

from __future__ import annotations

import csv
import http.client
import io
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.arquivos.http_files import transport_error
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)
from guaraci.datasus.frames import write_sqlite
from guaraci.mds.campos import CAMPOS_CHAVE, GRUPOS, VERIFICADO_EM

__all__ = [
    "BASE_URL",
    "DATASET",
    "MIN_YEAR",
    "ANO_PADRAO",
    "MisocialClient",
    "MisocialClientError",
    "MisocialDataSource",
    "campos_dos_grupos",
]

BASE_URL = "https://aplicacoes.mds.gov.br/sagi/servicos/misocial/"
DATASET = "mds_misocial"
MIN_YEAR = 2003
#: Último ano completo publicado em 2026-10-20. Vira o padrão de ``start_year``.
ANO_PADRAO = 2025
#: Linhas por página. Um mês tem 5.571 municípios, então cabe numa página; a
#: paginação por ``start`` fica para o caso de o MDS passar a publicar mais.
PAGE_ROWS = 10000

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")
_ZEROS = frozenset({"", "0", "0.0", "0,0"})
#: Janela, em meses antes do corrente, em que mês com poucos campos é avisado.
_RECENT_MONTHS = 3


class MisocialClientError(ApiClientError):
    """Falha ao consultar o Solr do MI Social."""


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


def campos_dos_grupos(grupos: Optional[Sequence[str]] = None) -> Tuple[str, ...]:
    """Campos de dado dos grupos pedidos, na ordem de ``GRUPOS`` (todos se vazio)."""
    pedidos = [str(g).strip().lower() for g in (grupos or []) if str(g).strip()]
    desconhecidos = [g for g in pedidos if g not in GRUPOS]
    if desconhecidos:
        raise ValueError(
            f"Grupo(s) desconhecido(s) {desconhecidos}. Use um de {list(GRUPOS)}."
        )
    escolhidos = set(pedidos) or set(GRUPOS)
    return tuple(campo for nome, campos in GRUPOS.items() if nome in escolhidos for campo in campos)


class MisocialClient:
    DEFAULT_TIMEOUT = 300
    USER_AGENT = "Mozilla/5.0 (compatible; guaraci/" + __version__ + ")"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def select_csv(
        self, *, fq: str, fields: Sequence[str], start: int = 0, rows: int = PAGE_ROWS
    ) -> str:
        """Uma página do ``select`` em CSV, como texto UTF-8."""
        body = urlencode({
            "q": "*:*", "fq": fq, "fl": ",".join(fields), "sort": "codigo_ibge asc",
            "start": str(start), "rows": str(rows), "wt": "csv",
        }).encode("ascii")
        what = f"{self.base_url} ({fq}, start={start})"

        def send() -> str:
            request = Request(self.base_url, data=body, headers={
                "User-Agent": self.USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            })
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
            except HTTPError as exc:
                category, retryable = classify_http_status(exc.code)
                raise MisocialClientError(
                    f"Request failed ({exc.code}) for '{what}'.",
                    category=category, retryable=retryable,
                    hint="Confira se o Solr do MI Social segue no ar em aplicacoes.mds.gov.br/sagi.",
                ) from exc
            except URLError as exc:
                category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
                raise MisocialClientError(
                    f"Could not reach '{what}': {exc.reason}",
                    category=category, retryable=True,
                    hint="Verifique acesso à internet, DNS e regras de proxy.",
                ) from exc
            except (OSError, http.client.HTTPException) as exc:
                error = transport_error(exc, what, self.timeout_seconds, MisocialClientError)
                if error is None:
                    raise
                raise error from exc
            text = raw.decode("utf-8-sig", errors="replace")
            if text.lstrip().startswith("<"):
                raise MisocialClientError(
                    f"O Solr devolveu HTML em vez de CSV para '{what}'.",
                    category="parse", retryable=True,
                    hint="O proxy da SAGI pode estar em manutenção; tente de novo mais tarde.",
                )
            return text

        return request_with_retry(send, max_attempts=self.max_attempts)


class MisocialDataSource(DataSource):
    """Um POST por mês no Solr, todos os municípios, campos dos grupos pedidos."""

    DATASET = DATASET
    DEFAULT_TIMEOUT = MisocialClient.DEFAULT_TIMEOUT

    def __init__(
        self, output_path: Optional[str] = None, *, client: Optional[MisocialClient] = None
    ) -> None:
        super().__init__(name=self.DATASET, output_path=output_path)
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Use download(); the export is read with polars.scan_*.")

    def _fetch_month(
        self, client: MisocialClient, anomes: str, fields: Sequence[str]
    ) -> List[Dict[str, str]]:
        """Todas as linhas do mês, paginando por ``start`` até vir página incompleta."""
        rows: List[Dict[str, str]] = []
        start = 0
        while True:
            text = client.select_csv(
                fq=f"anomes_s:{anomes}", fields=fields, start=start, rows=PAGE_ROWS
            )
            reader = csv.reader(io.StringIO(text, newline=""))
            header = next(reader, None)
            if not header:
                break
            header = [name.strip() for name in header]
            unknown = [name for name in header if name not in fields]
            if unknown:
                raise MisocialClientError(
                    f"O Solr devolveu colunas fora da lista pedida em {anomes}: {unknown[:3]}",
                    category="parse", retryable=False,
                )
            page = [dict(zip(header, values)) for values in reader if values]
            rows.extend(page)
            if len(page) < PAGE_ROWS:
                break
            start += PAGE_ROWS
        return rows

    def download(
        self,
        *,
        start_year: int = ANO_PADRAO,
        end_year: Optional[int] = None,
        grupos: Optional[Sequence[str]] = None,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        today: Optional[date] = None,
    ) -> Dict[str, object]:
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if first < MIN_YEAR or last < first:
            raise ValueError(
                f"Invalid year range {first}-{last}; {self.DATASET} starts in {MIN_YEAR}."
            )
        data_fields = campos_dos_grupos(grupos)
        fields = (*CAMPOS_CHAVE, *data_fields)
        fmt = _normalize_format(output_format) or "csv"
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or MisocialClient(
            base_url=(base_url or BASE_URL).strip(), timeout_seconds=timeout
        )
        today = today or date.today()
        current = today.year * 100 + today.month

        months = [
            f"{year}{month:02d}" for year in range(first, last + 1) for month in range(1, 13)
            if year * 100 + month <= current
        ]
        future = (last - first + 1) * 12 - len(months)
        if progress_callback is not None:
            progress_callback(
                {"event": "download_start", "source": self.name, "documents_total": len(months)}
            )

        csv_path = base_dir / f"{self.name}.csv"
        downloaded = failed = rows_written = 0
        failures: List[str] = []
        empty: List[str] = []
        filled_by_month: Dict[str, int] = {}
        with open(csv_path, "w", encoding="utf-8", newline="") as sink:
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(fields)
            for done, anomes in enumerate(months, start=1):
                try:
                    rows = self._fetch_month(client, anomes, fields)
                except ApiClientError as exc:
                    failed += 1
                    failures.append(f"{anomes}: {getattr(exc, 'message', exc)}")
                    continue
                # Mês sem nenhum valor de dado é documento-esqueleto de mês ainda
                # não publicado: fica fora para não parecer zero de verdade.
                filled = sum(
                    1 for name in data_fields
                    if any((row.get(name) or "").strip() not in _ZEROS for row in rows)
                )
                if not filled:
                    empty.append(anomes)
                else:
                    filled_by_month[anomes] = filled
                    downloaded += 1
                    for row in rows:
                        writer.writerow([row.get(name, "") for name in fields])
                        rows_written += 1
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name,
                        "documents_total": len(months), "files_completed": done,
                        "file_path": f"misocial {anomes}",
                    })

        exported = [str(csv_path)]
        if downloaded == 0:
            csv_path.unlink(missing_ok=True)
            exported = []
        elif fmt != "csv":
            frame = pl.scan_csv(csv_path, infer_schema=False)
            if fmt == "parquet":
                dest = base_dir / f"{self.name}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(
                    frame, db_path=base_dir / f"{self.name}.sqlite", table=self.name
                )
                if written is None:
                    raise ValueError("MI Social export has no rows to write to sqlite.")
                dest = written
            csv_path.unlink(missing_ok=True)
            exported = [str(dest)]

        warnings: List[str] = []
        if failures:
            warnings.append(
                f"{failed} mês(es) falharam (primeiros: {'; '.join(failures[:3])})."
            )
        if empty:
            warnings.append(
                f"Mês(es) sem nenhum valor nos campos pedidos, tratados como ainda não "
                f"publicados e deixados de fora: {', '.join(empty)}."
            )
        # Cada sistema fecha o mês num ritmo, e o mês recém-aberto costuma trazer
        # só alguns campos (em 202609 o BPC vinha com 3 de 29). O aviso vale só
        # para os últimos meses antes de hoje: no meio da série, mês "magro" é a
        # periodicidade do campo (a saúde das condicionalidades é semestral, a
        # educação bimestral) e não carga pendente. O mês fica no CSV, pois o
        # corte certo depende do campo que se vai usar.
        best = max(filled_by_month.values(), default=0)
        recent = (today.year * 12 + today.month) - _RECENT_MONTHS
        partial = [
            f"{anomes} ({count} de {best})" for anomes, count in filled_by_month.items()
            if count * 2 < best and int(anomes[:4]) * 12 + int(anomes[4:]) > recent
        ]
        if partial:
            warnings.append(
                "Mês(es) com menos da metade dos campos preenchidos do melhor mês do "
                "recorte, provavelmente ainda em carga; zeros ali podem não ser zero "
                f"de verdade: {', '.join(partial)}."
            )
        if future:
            warnings.append(
                f"{future} mês(es) posteriores a {current} não foram pedidos."
            )
        return {
            "documents_found": len(months),
            "downloaded_count": downloaded,
            "skipped_count": len(empty),
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": client.base_url,
            "output_format": fmt,
            "exported_files": exported,
            "rows": rows_written,
            "columns": len(fields),
            "fields_verified_at": VERIFICADO_EM,
            "empty_months": empty,
            "partial_months": [item.split(" ")[0] for item in partial],
            "export_warning": " ".join(warnings) or None,
        }
