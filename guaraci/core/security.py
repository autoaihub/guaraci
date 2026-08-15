"""
Guaraci Security Guards
=======================

Input guardrails shared by API, jobs, and CLI layers.

Two protections live here:

- ``ensure_allowed_crawl_url``: server-side fetch targets supplied by the user
  (``results_url``) must point to an allow-listed domain, preventing SSRF.
  Defaults to ``gov.br``; extend via ``GUARACI_CRAWL_URL_ALLOWLIST``
  (comma-separated host suffixes).
- ``ensure_allowed_output_dir``: when ``GUARACI_OUTPUT_ROOT`` is set (the
  desktop launcher sets it to the downloads mount), user-supplied output
  directories must resolve inside that root, preventing writes or folder-open
  commands on arbitrary paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

DEFAULT_CRAWL_HOST_SUFFIXES: Tuple[str, ...] = ("gov.br",)

OUTPUT_ROOT_ENV = "GUARACI_OUTPUT_ROOT"
CRAWL_ALLOWLIST_ENV = "GUARACI_CRAWL_URL_ALLOWLIST"


def _allowed_crawl_host_suffixes() -> Tuple[str, ...]:
    raw = os.getenv(CRAWL_ALLOWLIST_ENV, "")
    extra = tuple(
        item.strip().lower().lstrip(".")
        for item in raw.split(",")
        if item.strip()
    )
    return DEFAULT_CRAWL_HOST_SUFFIXES + extra


def ensure_allowed_crawl_url(url: object) -> None:
    """Reject crawl/fetch URLs outside the allow-listed domains.

    Accepts ``None``/empty (source default URL is used instead).
    """
    if url is None or str(url).strip() == "":
        return
    parsed = urlparse(str(url))
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid results_url scheme '{parsed.scheme or '(none)'}'. "
            "Only http/https URLs are accepted."
        )
    host = (parsed.hostname or "").lower()
    suffixes = _allowed_crawl_host_suffixes()
    for suffix in suffixes:
        if host == suffix or host.endswith(f".{suffix}"):
            return
    raise ValueError(
        f"results_url host '{host}' is not in the allowed domains "
        f"({', '.join(suffixes)}). Set {CRAWL_ALLOWLIST_ENV} to extend the list."
    )


def allowed_output_root() -> Optional[Path]:
    raw = os.getenv(OUTPUT_ROOT_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def ensure_allowed_output_dir(path: object) -> None:
    """Reject output directories outside ``GUARACI_OUTPUT_ROOT`` when it is set.

    When the env var is unset (local library/CLI use) any path is accepted,
    preserving current behavior for non-served deployments.
    """
    if path is None or str(path).strip() == "":
        return
    root = allowed_output_root()
    if root is None:
        return
    resolved = Path(str(path)).expanduser().resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(
            f"output_dir '{resolved}' is outside the allowed output root "
            f"'{root}' ({OUTPUT_ROOT_ENV})."
        )
