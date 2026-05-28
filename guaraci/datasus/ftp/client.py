"""Thin async wrapper over :mod:`ftplib` for ``ftp.datasus.gov.br``.

Design choices (see ``docs/PLANO_DATASUS_FTP_DIRETO.md``):

- Stdlib-only transport: ``asyncio.to_thread(ftplib)`` instead of ``aioftp``.
  The smoke test in ``scripts/discover_sih_rd.py`` already proves ``ftplib``
  is enough for DATASUS; adding ``aioftp`` mixes protocol validation with
  new-dependency validation.
- ``NLST`` + explicit ``SIZE`` instead of ``LIST`` parsing — historically
  more reliable on the DATASUS server.
- Retries with exponential backoff at the operation level, with an
  in-process ``asyncio.Lock`` so concurrent callers on the same client are
  serialised (a single ``ftplib.FTP`` instance is not thread-safe). For
  real parallelism use a pool of clients.
"""

from __future__ import annotations

import asyncio
import ftplib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FtpEntry:
    """A single entry returned by ``NLST``.

    ``size`` is :data:`None` unless explicitly fetched via
    :meth:`DatasusFtpClient.size` — ``NLST`` itself does not return sizes.
    """

    name: str
    size: Optional[int] = None


_TRANSIENT_FTP_ERRORS: tuple[type[BaseException], ...] = (
    ftplib.error_temp,
    ftplib.error_proto,
    EOFError,
    OSError,
)


class DatasusFtpClient:
    """Async, retryable wrapper around an anonymous FTP session.

    The client is single-connection: methods are serialised by an internal
    lock. For parallel downloads instantiate multiple clients (each owns
    its own underlying ``ftplib.FTP``).
    """

    HOST: str = "ftp.datasus.gov.br"
    DEFAULT_TIMEOUT: float = 60.0
    DEFAULT_RETRIES: int = 3
    DEFAULT_BACKOFF_BASE: float = 1.5

    def __init__(
        self,
        host: str = HOST,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
    ) -> None:
        self.host = host
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff_base = float(backoff_base)
        self._ftp: ftplib.FTP | None = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._ftp is not None

    async def connect(self) -> None:
        await asyncio.to_thread(self._connect_sync)

    async def close(self) -> None:
        if self._ftp is None:
            return
        ftp, self._ftp = self._ftp, None
        await asyncio.to_thread(self._safe_quit, ftp)

    async def list_dir(self, path: str) -> list[FtpEntry]:
        names = await self._run_with_retry(self._list_sync, path)
        return [FtpEntry(name=name) for name in names]

    async def size(self, path: str) -> int:
        return await self._run_with_retry(self._size_sync, path)

    async def download(
        self,
        path: str,
        dest: Path | str,
        *,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        dest_path = Path(dest)
        await self._run_with_retry(self._download_sync, path, dest_path, progress)
        return dest_path

    async def __aenter__(self) -> "DatasusFtpClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    def _connect_sync(self) -> None:
        ftp = ftplib.FTP(self.host, timeout=self.timeout)
        ftp.login()
        ftp.set_pasv(True)
        self._ftp = ftp
        logger.debug("Connected to %s", self.host)

    def _reconnect_sync(self) -> None:
        if self._ftp is not None:
            self._safe_quit(self._ftp)
            self._ftp = None
        self._connect_sync()

    @staticmethod
    def _safe_quit(ftp: ftplib.FTP) -> None:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass

    def _require(self) -> ftplib.FTP:
        if self._ftp is None:
            raise RuntimeError(
                "DatasusFtpClient is not connected; call connect() first "
                "or use it as an async context manager."
            )
        return self._ftp

    def _list_sync(self, path: str) -> list[str]:
        ftp = self._require()
        raw = ftp.nlst(path)
        return [_basename(name) for name in raw]

    def _size_sync(self, path: str) -> int:
        ftp = self._require()
        ftp.voidcmd("TYPE I")
        size = ftp.size(path)
        return int(size or 0)

    def _download_sync(
        self,
        path: str,
        dest: Path,
        progress: Optional[Callable[[int, int], None]],
    ) -> None:
        ftp = self._require()
        ftp.voidcmd("TYPE I")
        try:
            total = int(ftp.size(path) or 0)
        except ftplib.error_perm:
            total = 0

        dest.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        with dest.open("wb") as fh:
            def _write(chunk: bytes) -> None:
                nonlocal bytes_written
                fh.write(chunk)
                bytes_written += len(chunk)
                if progress is not None:
                    progress(bytes_written, total)

            ftp.retrbinary(f"RETR {path}", _write)

    async def _run_with_retry(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            last_exc: BaseException | None = None
            for attempt in range(1, self.retries + 1):
                try:
                    return await asyncio.to_thread(fn, *args, **kwargs)
                except _TRANSIENT_FTP_ERRORS as exc:
                    last_exc = exc
                    if attempt < self.retries:
                        logger.warning(
                            "FTP attempt %d/%d failed (%s); reconnecting and retrying",
                            attempt,
                            self.retries,
                            exc,
                        )
                        await asyncio.to_thread(self._reconnect_sync)
                        await asyncio.sleep(self.backoff_base * (2 ** (attempt - 1)))
                    else:
                        logger.error("FTP operation failed after %d attempts: %s", self.retries, exc)
            assert last_exc is not None
            raise last_exc


def _basename(name: str) -> str:
    """Strip any directory prefix that some FTP servers prepend to NLST entries."""
    name = name.strip()
    # NLST may return either bare names or full paths depending on server config.
    if "/" in name:
        return name.rsplit("/", 1)[-1]
    return name


# Silence the "unused import" linter without exporting `time` publicly.
_ = time
