"""Download dos resultados: links assinados, ZIP em fluxo e listagem segura."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import time
import zipfile
from pathlib import Path
from typing import Dict, Iterator, List, Optional

CHUNK = 1024 * 1024


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class LinkSigner:
    """Assina (job, usuário, arquivo, validade) com HMAC-SHA256."""

    def __init__(self, secret: str):
        self._key = hashlib.sha256(("guaraci-download:" + secret).encode("utf-8")).digest()

    def sign(self, job_id: str, user_id: int, name: str, expires: int) -> str:
        message = f"{job_id}|{user_id}|{name}|{expires}".encode("utf-8")
        return _b64(hmac.new(self._key, message, hashlib.sha256).digest())

    def verify(self, job_id: str, user_id: int, name: str, expires: int, signature: str) -> bool:
        if expires < int(time.time()):
            return False
        expected = self.sign(job_id, user_id, name, expires)
        return hmac.compare_digest(expected, signature or "")


def list_files(folder: Optional[Path]) -> List[Dict[str, object]]:
    """Arquivos do resultado, com caminho relativo. Ignora pastas ocultas (cache)."""
    if folder is None or not folder.is_dir():
        return []
    root = folder.resolve()
    items: List[Dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        items.append({"name": relative.as_posix(), "bytes": path.stat().st_size})
    return items


def resolve_file(folder: Optional[Path], name: str) -> Optional[Path]:
    """Resolve ``name`` dentro de ``folder`` sem permitir sair dela."""
    if folder is None or not name:
        return None
    root = folder.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    relative = candidate.relative_to(root)
    if any(part.startswith(".") for part in relative.parts):
        return None
    return candidate


class _Sink(io.RawIOBase):
    """Destino não pesquisável do ZipFile: acumula bytes para o gerador."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._position = 0

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # type: ignore[override]
        self._buffer.extend(data)
        self._position += len(data)
        return len(data)

    def tell(self) -> int:
        return self._position

    def drain(self) -> bytes:
        data = bytes(self._buffer)
        self._buffer.clear()
        return data


def stream_zip(folder: Path, files: List[Dict[str, object]]) -> Iterator[bytes]:
    """Gera o ZIP aos pedaços, sem montar o arquivo inteiro em disco ou memória."""
    sink = _Sink()
    root = folder.resolve()
    with zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for item in files:
            name = str(item["name"])
            source = resolve_file(root, name)
            if source is None:
                continue
            info = zipfile.ZipInfo.from_file(source, arcname=name)
            info.compress_type = zipfile.ZIP_DEFLATED
            with source.open("rb") as handle, archive.open(info, mode="w", force_zip64=True) as entry:
                while True:
                    chunk = handle.read(CHUNK)
                    if not chunk:
                        break
                    entry.write(chunk)
                    data = sink.drain()
                    if data:
                        yield data
            data = sink.drain()
            if data:
                yield data
    data = sink.drain()
    if data:
        yield data
