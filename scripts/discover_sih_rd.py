"""Discover available SIH RD files (year × UF × month) without downloading.

Usage:
    uv run python scripts/discover_sih_rd.py
"""

from __future__ import annotations

import asyncio
from collections import Counter

from pysus.api.ftp.client import FTP as PySUSFtpClient
from pysus.api.ftp.databases import SIH as PySUSFtpSIH
from pysus.api.ftp.models import File as PySUSFtpFile


async def main() -> None:
    client = PySUSFtpClient()
    await client.connect()
    try:
        dataset = PySUSFtpSIH(client=client)
        files = await dataset._fetch_content()
    finally:
        await client.close()

    rd_files = []
    for file_record in files:
        if not isinstance(file_record, PySUSFtpFile):
            continue
        group_obj = getattr(file_record, "group", None)
        group_name = str(getattr(group_obj, "name", "") or "").upper()
        if group_name != "RD":
            continue
        rd_files.append(file_record)

    by_year: Counter[int] = Counter()
    by_state: Counter[str] = Counter()
    years = set()
    states = set()
    for f in rd_files:
        year = getattr(f, "year", None)
        state = getattr(f, "state", None)
        if year is not None:
            by_year[int(year)] += 1
            years.add(int(year))
        if state is not None:
            by_state[str(state).upper()] += 1
            states.add(str(state).upper())

    print(f"Total RD files: {len(rd_files)}")
    print(f"Years span: {min(years)} - {max(years)}  ({len(years)} years)")
    print(f"States: {len(states)}  ->  {', '.join(sorted(states))}")
    total_size = 0
    for f in rd_files:
        size = getattr(f, "size", 0) or 0
        try:
            total_size += int(size)
        except (TypeError, ValueError):
            pass
    if total_size:
        gb = total_size / (1024 ** 3)
        print(f"Total compressed size: {gb:.1f} GB")
    print()
    print("Files per year (top 25):")
    for year in sorted(by_year):
        print(f"  {year}: {by_year[year]}")
    print()
    print("Files per state:")
    for state in sorted(by_state):
        print(f"  {state}: {by_state[state]}")


if __name__ == "__main__":
    asyncio.run(main())
