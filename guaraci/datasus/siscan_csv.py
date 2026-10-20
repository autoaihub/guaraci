"""SISCAN atual em CSV, publicado no FTP do DATASUS (``SISCAN/SISCAN/``).

O SISCAN substituiu o SISCOLO e o SISMAMA (fonte ``siscan``, DBC até 2015). O
DATASUS publica o sistema novo em CSV ``;`` com cabeçalho entre aspas, um arquivo
por tabela e ano (``SISCAN_<TABELA>_<AAAA>.csv``), de 2013 a 2025. São dez
tabelas: citopatológico e histopatológico de colo e de mama e mamografia, cada uma
por exame e na versão ``_PACNT`` (por paciente, com ``CO_PACIENTE`` pseudônimo e
idade em anos). Não há nome, CPF nem CNS.

O conjunto passa de 53 GB e a citologia de colo tem até 2,1 GB por ano, por isso
``tabelas`` e ``anos`` são obrigatórios. O transporte é FTP, mas o resto (pular o
que não mudou, transcodificar linha a linha, exportar csv/parquet/sqlite em fluxo)
é o mesmo dos arquivos de URL fixa: a fonte reaproveita ``HttpFileDataSource`` e
troca só o cliente.
"""

from __future__ import annotations

import ftplib
import socket
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from guaraci.arquivos.http_files import (
    HttpFile,
    HttpFileClientError,
    HttpFileDataSource,
    HttpResource,
    RemoteFile,
    transport_error,
)
from guaraci.core.datasource import DataSource
from guaraci.core.http import request_with_retry

__all__ = [
    "SISCAN_CSV",
    "SISCAN_CSV_ANOS",
    "SISCAN_CSV_KEY",
    "SISCAN_CSV_TABELAS",
    "FtpFileClient",
    "SiscanCsvDataSource",
]

SISCAN_CSV_KEY = "siscan_csv"
_BASE = "ftp://ftp.datasus.gov.br/dissemin/publicos/SISCAN/SISCAN/"

# Listagem do FTP em 2026-10-20: 130 arquivos, 13 anos por tabela.
SISCAN_CSV_TABELAS: Dict[str, str] = {
    "CITO_COLO": "Citopatológico do colo do útero (por exame)",
    "CITO_COLO_PACNT": "Citopatológico do colo do útero (por paciente)",
    "CITO_MAMA": "Citopatológico de mama (por exame)",
    "CITO_MAMA_PACNT": "Citopatológico de mama (por paciente)",
    "HISTO_COLO": "Histopatológico do colo do útero (por exame)",
    "HISTO_COLO_PACNT": "Histopatológico do colo do útero (por paciente)",
    "HISTO_MAMA": "Histopatológico de mama (por exame)",
    "HISTO_MAMA_PACNT": "Histopatológico de mama (por paciente)",
    "MAMOGRAFIA": "Mamografia (por exame)",
    "MAMOGRAFIA_PACNT": "Mamografia (por paciente)",
}
SISCAN_CSV_ANOS = tuple(range(2013, 2026))

SISCAN_CSV = HttpFile(
    SISCAN_CSV_KEY,
    "SISCAN - Exames de rastreamento do câncer de colo e de mama (CSV)",
    "Microdados do SISCAN (2013-2025): citopatológico e histopatológico de colo e de "
    "mama e mamografia, por exame ou por paciente, com UF e município de residência, "
    "competência, raça/cor e faixa etária. Um CSV por tabela e ano no FTP do DATASUS; "
    "a citologia de colo e a mamografia vão de 0,5 a 2,1 GB por ano, as demais "
    "tabelas ficam abaixo de 13 MB.",
    tuple(
        HttpResource(f"{tabela}_{ano}", f"{_BASE}SISCAN_{tabela}_{ano}.csv", f"{titulo} {ano}")
        for tabela, titulo in SISCAN_CSV_TABELAS.items()
        for ano in SISCAN_CSV_ANOS
    ),
    separator=";",
    encoding="auto",
    selector="tabela_ano",
)


class FtpFileClient:
    """Cliente de arquivo único por FTP anônimo, com a interface do ``HttpFileClient``.

    Cada chamada abre a própria sessão: o download de um arquivo de 2 GB leva
    minutos, e uma sessão ociosa entre o ``SIZE`` e o ``RETR`` costuma cair no
    servidor do DATASUS.
    """

    DEFAULT_TIMEOUT = 600

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
        ftp_factory: Callable[..., ftplib.FTP] = ftplib.FTP,
    ) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts
        self._ftp_factory = ftp_factory

    def _session(self, host: str) -> ftplib.FTP:
        ftp = self._ftp_factory(host, timeout=self.timeout_seconds)
        ftp.login()
        ftp.set_pasv(True)
        ftp.voidcmd("TYPE I")
        return ftp

    def _error(self, exc: BaseException, url: str) -> Optional[HttpFileClientError]:
        if isinstance(exc, ftplib.error_perm):
            # 550: arquivo inexistente; não adianta repetir.
            return HttpFileClientError(
                f"FTP refused '{url}': {exc}",
                category="configuration",
                retryable=False,
                hint="Confira se a tabela e o ano existem no FTP do DATASUS.",
            )
        if isinstance(exc, (ftplib.error_temp, ftplib.error_proto, ftplib.error_reply, EOFError)):
            return HttpFileClientError(
                f"FTP transfer of '{url}' failed: {exc!r}",
                category="connectivity",
                retryable=True,
                hint="O FTP do DATASUS oscila; tente de novo.",
            )
        if isinstance(exc, (OSError, socket.timeout)):
            return transport_error(exc, url, self.timeout_seconds)
        return None

    def head(self, url: str) -> RemoteFile:
        parts = urlsplit(url)

        def send() -> RemoteFile:
            try:
                with self._session(parts.hostname or "") as ftp:
                    size = ftp.size(parts.path)
                    try:
                        modified = ftp.sendcmd(f"MDTM {parts.path}").split()[-1]
                    except ftplib.error_perm:
                        modified = None
                return RemoteFile(url=url, size=int(size) if size else None, last_modified=modified)
            except Exception as exc:
                error = self._error(exc, url)
                if error is None:
                    raise
                raise error from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(
        self,
        url: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa em fluxo para ``destination``, passando por um ``.part``."""
        parts = urlsplit(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def send() -> int:
            written = 0
            try:
                with self._session(parts.hostname or "") as ftp, open(partial, "wb") as sink:
                    try:
                        expected = int(ftp.size(parts.path) or 0)
                    except ftplib.error_perm:
                        expected = 0

                    def write(block: bytes) -> None:
                        nonlocal written
                        sink.write(block)
                        written += len(block)
                        if progress_callback is not None:
                            progress_callback(written)

                    ftp.retrbinary(f"RETR {parts.path}", write, blocksize=chunk_size)
            except Exception as exc:
                error = self._error(exc, url)
                if error is None:
                    raise
                raise error from exc
            if expected and written != expected:
                raise HttpFileClientError(
                    f"Download of '{url}' was truncated: {written} of {expected} bytes.",
                    category="incomplete",
                    retryable=True,
                    hint="O servidor encerrou a conexão antes do fim; tente de novo.",
                )
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written


def _as_list(value: object) -> List[object]:
    if value is None:
        return []
    if isinstance(value, (str, int)):
        return [value]
    return list(value)  # type: ignore[arg-type]


class SiscanCsvDataSource(HttpFileDataSource):
    """SISCAN em CSV: recorte obrigatório por tabela e ano, transporte FTP."""

    DATASET = SISCAN_CSV_KEY
    DEFAULT_TIMEOUT = FtpFileClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        client: Optional[object] = None,
    ) -> None:
        # O spec não entra em ``HTTP_FILES``: lá ele viraria também uma fonte HTTP.
        DataSource.__init__(self, name=SISCAN_CSV_KEY, output_path=output_path)
        self.spec = SISCAN_CSV
        self._client = client
        self._tabelas: List[str] = []

    def _select(
        self,
        indicadores: Optional[Sequence[str]],
        anos: Optional[Sequence[object]] = None,
        meses: Optional[Sequence[object]] = None,
    ) -> List[HttpResource]:
        """Cruza ``tabelas`` e ``anos``, os dois obrigatórios (o conjunto passa de 53 GB)."""
        if not self._tabelas or not anos:
            raise ValueError(
                f"'{self.name}' tem 130 arquivos e mais de 53 GB; informe 'tabelas' e "
                "'anos' para escolher o que baixar."
            )
        unknown = [t for t in self._tabelas if t not in SISCAN_CSV_TABELAS]
        if unknown:
            raise ValueError(f"Unknown tabelas {unknown}. Known: {list(SISCAN_CSV_TABELAS)}")
        try:
            wanted_years = [int(a) for a in anos]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'anos' devem ser números: {exc}") from exc
        unknown_years = sorted(set(wanted_years) - set(SISCAN_CSV_ANOS))
        if unknown_years:
            raise ValueError(f"Unknown anos {unknown_years}. Known: {list(SISCAN_CSV_ANOS)}")
        by_code = {r.code: r for r in self.spec.resources}
        return [
            by_code[f"{tabela}_{ano}"]
            for tabela in dict.fromkeys(self._tabelas)
            for ano in dict.fromkeys(wanted_years)
        ]

    def download(  # type: ignore[override]
        self,
        *,
        tabelas: Optional[Sequence[str]] = None,
        anos: Optional[Sequence[object]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        **kwargs: object,
    ) -> Dict[str, object]:
        self._tabelas = [str(t).strip().upper() for t in _as_list(tabelas)]
        injected = self._client is None
        if injected:
            self._client = FtpFileClient(timeout_seconds=timeout)
        try:
            return super().download(anos=_as_list(anos), timeout=timeout, **kwargs)
        finally:
            if injected:
                self._client = None
