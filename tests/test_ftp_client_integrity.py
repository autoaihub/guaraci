"""Integrity/atomicity tests for DatasusFtpClient downloads (no network)."""

from pathlib import Path

import pytest

from guaraci.datasus.ftp.client import DatasusFtpClient, TruncatedDownloadError


class _FakeFtp:
    """Minimal stand-in for ftplib.FTP driving _download_sync offline."""

    def __init__(self, payload: bytes, reported_size: int):
        self._payload = payload
        self._reported_size = reported_size

    def voidcmd(self, cmd: str) -> None:
        pass

    def size(self, path: str) -> int:
        return self._reported_size

    def retrbinary(self, cmd: str, callback) -> None:
        for offset in range(0, len(self._payload), 4):
            callback(self._payload[offset : offset + 4])


def _client_with(fake: _FakeFtp) -> DatasusFtpClient:
    client = DatasusFtpClient()
    client._ftp = fake  # type: ignore[assignment]
    return client


def test_download_complete_promotes_part_to_dest(tmp_path: Path):
    payload = b"0123456789ABCDEF"
    client = _client_with(_FakeFtp(payload, reported_size=len(payload)))
    dest = tmp_path / "OK.dbc"

    client._download_sync("/dissemin/OK.dbc", dest, progress=None)

    assert dest.read_bytes() == payload
    assert not dest.with_name("OK.dbc.part").exists()


def test_truncated_download_raises_and_leaves_no_files(tmp_path: Path):
    payload = b"0123456789"
    client = _client_with(_FakeFtp(payload, reported_size=len(payload) + 5))
    dest = tmp_path / "TRUNC.dbc"

    with pytest.raises(TruncatedDownloadError, match="10 of 15 bytes"):
        client._download_sync("/dissemin/TRUNC.dbc", dest, progress=None)

    assert not dest.exists()
    assert not dest.with_name("TRUNC.dbc.part").exists()


def test_unknown_size_accepts_any_length(tmp_path: Path):
    payload = b"0123456789"
    client = _client_with(_FakeFtp(payload, reported_size=0))
    dest = tmp_path / "NOSIZE.dbc"

    client._download_sync("/dissemin/NOSIZE.dbc", dest, progress=None)

    assert dest.read_bytes() == payload


def test_truncation_is_retryable_oserror():
    assert issubclass(TruncatedDownloadError, OSError)
