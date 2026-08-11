"""
Fill in the Guaraci data dictionary (guaraci/data/field_dictionary.json +
docs/DATA_DICTIONARY.md) for sources that are still `filters_only`.

Two phases, always in this order, never mixed:

  1) Collection (hits the network, writes only reports/source_validation.json —
     never touches the versioned files):

       .venv/Scripts/python.exe scripts/sample_sources.py --limit 5      # smoke test
       .venv/Scripts/python.exe scripts/sample_sources.py                # full batch

  2) Promotion (no network — merges the report into the versioned files):

       .venv/Scripts/python.exe scripts/sample_sources.py --promote-from-report

Sources already resolved (status ok/empty/error/needs_credential) in the
existing field_dictionary.json are preserved and never re-sampled unless
--force or --only is used. The 22 sources originally covered by hand (DATASUS
FTP systems + a handful of "vitrine" OpenDataSUS sources + NASA) and the 2
sources that need a seed ID from another source's sample are out of scope for
this script — see guaraci/services/dictionary_sampling.py for why.

This is a long/verbose live job against external government APIs (per the
Vogel Stack, operação §5.1, run it with a persisted log).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))  # allow `python scripts/sample_sources.py` without an editable install

from guaraci.services.dictionary_io import atomic_write_json, load_field_dictionary, render_data_dictionary_md
from guaraci.services.dictionary_sampling import (
    RateLimited,
    classify_source,
    sample_generic_demas,
    sample_govbr_single_document,
    schema_of,
)
from guaraci.services.downloads import DownloadService
from guaraci.snis import SinisaDataSource, SnisDataSource

REPO_ROOT = _REPO_ROOT
REPORTS_DIR = REPO_ROOT / "reports"
REPORT_JSON = REPORTS_DIR / "source_validation.json"
FIELD_DICT_JSON = REPO_ROOT / "guaraci" / "data" / "field_dictionary.json"
DATA_DICT_MD = REPO_ROOT / "docs" / "DATA_DICTIONARY.md"

GOVBR_CLASSES = {"snis": SnisDataSource, "sinisa": SinisaDataSource}
RESOLVED_STATUSES = {"ok", "empty", "error", "needs_credential"}
CIRCUIT_BREAKER_LIMIT = 3


def log(msg: str) -> None:
    print(msg, flush=True)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", type=str, default=None, help="comma-separated source keys to (re)process")
    parser.add_argument("--limit", type=int, default=None, help="process at most N pending sources")
    parser.add_argument("--force", action="store_true", help="re-sample sources even if already resolved")
    parser.add_argument("--sleep", type=float, default=1.5, help="seconds between network calls (default 1.5)")
    parser.add_argument(
        "--promote-from-report",
        action="store_true",
        help="no network: merge an existing reports/source_validation.json into the versioned files",
    )
    return parser.parse_args(argv)


def write_report(results: Dict[str, Any]) -> None:
    REPORT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def promote(existing: Dict[str, Any]) -> Dict[str, Any]:
    if not REPORT_JSON.exists():
        raise SystemExit(f"{REPORT_JSON} not found — run a collection pass first (no --promote-from-report).")
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    merged = dict(existing)
    merged.update(report)
    return merged


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    REPORTS_DIR.mkdir(exist_ok=True)
    existing = load_field_dictionary(FIELD_DICT_JSON)

    if args.promote_from_report:
        merged = promote(existing)
        atomic_write_json(FIELD_DICT_JSON, merged)
        DATA_DICT_MD.write_text(render_data_dictionary_md(merged), encoding="utf-8")
        log(f"Promoted {REPORT_JSON} -> {FIELD_DICT_JSON}, {DATA_DICT_MD}")
        return 0

    svc = DownloadService()
    all_sources = [d.source for d in svc.list_sources()]
    known = set(all_sources)

    results: Dict[str, Any] = {s: dict(existing.get(s, {})) for s in all_sources}

    # 1) Filters for every source: instant, no network, always refreshed.
    log(f"[schema] {len(all_sources)} sources")
    for source in all_sources:
        results[source]["filters"] = schema_of(svc, source)
    write_report(results)

    # 2) Pick targets.
    if args.only:
        targets = [s.strip() for s in args.only.split(",") if s.strip()]
        unknown = [s for s in targets if s not in known]
        if unknown:
            raise SystemExit(f"Unknown source(s) in --only: {', '.join(unknown)}")
    else:
        targets = [
            s for s in all_sources
            if args.force or results[s].get("status") not in RESOLVED_STATUSES
        ]
        targets = [s for s in targets if classify_source(s) in ("demas_generic", "govbr")]
        if args.limit is not None:
            targets = targets[: args.limit]

    preview = ", ".join(targets[:20]) + (", ..." if len(targets) > 20 else "")
    log(f"[targets] {len(targets)} source(s): {preview}")

    # 3) Sample each target. One bad source never aborts the batch; three
    #    consecutive rate-limit signals do (circuit breaker).
    consecutive_rate_limits = 0
    for i, source in enumerate(targets, start=1):
        category = classify_source(source)
        log(f"[{i}/{len(targets)}] {source} ({category})")

        if category not in ("demas_generic", "govbr"):
            log(f"   -> skipped (category={category}, out of scope for this script)")
            continue

        try:
            if category == "govbr":
                outcome = sample_govbr_single_document(GOVBR_CLASSES[source], source)
            else:
                outcome = sample_generic_demas(svc, source)
            consecutive_rate_limits = 0
        except RateLimited as exc:
            consecutive_rate_limits += 1
            log(f"   -> rate limited ({consecutive_rate_limits}/{CIRCUIT_BREAKER_LIMIT}): {exc}")
            if consecutive_rate_limits >= CIRCUIT_BREAKER_LIMIT:
                log("Circuit breaker tripped (3 consecutive rate limits) — stopping this batch.")
                break
            continue

        results[source].update(outcome)
        log(f"   -> {outcome.get('status')}")
        write_report(results)
        if args.sleep:
            time.sleep(args.sleep)

    write_report(results)
    log(f"\n[collection done] wrote {REPORT_JSON}. Run with --promote-from-report to update the versioned files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
