"""Top-level orchestration: sweep sources, plan units, materialise, record.

``Orchestrator.backfill`` runs the full history ("sair tudo"); ``update`` runs
the incremental delta driven by the ledger. Both resolve every registered
source to a :class:`SourceProfile`, plan its units, materialise them through the
right runner path, and append one ledger row per unit. NASA/unknown sources are
reported as skipped (they need a lat/lon and are collected on demand).

The service, the FTP records provider and the clock are all injectable, so the
whole sweep is exercised in tests without a network or a real event loop.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from guaraci.orchestrator.cadence import SourceProfile, profile_for
from guaraci.orchestrator.ledger import Ledger, LedgerRow
from guaraci.orchestrator.model import FetchUnit
from guaraci.orchestrator.planner import (
    default_ftp_records,
    plan_backfill,
    plan_update,
)
from guaraci.orchestrator.runner import run_ftp_batch, run_via_service

Clock = Callable[[], str]
ProgressHook = Callable[[SourceProfile, List[LedgerRow]], None]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunReport:
    """Outcome of a backfill/update sweep."""

    run_id: str
    mode: str
    dry_run: bool = False
    totals: Counter = field(default_factory=Counter)
    by_source: Dict[str, Counter] = field(default_factory=dict)
    skipped_sources: List[Dict[str, str]] = field(default_factory=list)
    source_errors: List[Dict[str, str]] = field(default_factory=list)
    rows: List[LedgerRow] = field(default_factory=list)

    def record(self, source: str, rows: Sequence[LedgerRow]) -> None:
        counter = self.by_source.setdefault(source, Counter())
        for row in rows:
            counter[row.status] += 1
            self.totals[row.status] += 1
        self.rows.extend(rows)

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "totals": dict(self.totals),
            "sources": {s: dict(c) for s, c in self.by_source.items()},
            "skipped_sources": self.skipped_sources,
            "source_errors": self.source_errors,
        }


class Orchestrator:
    """Coordinates planning + materialisation + ledger for the bronze sweep."""

    def __init__(
        self,
        bronze_root: Path,
        *,
        service: Any = None,
        ledger: Optional[Ledger] = None,
        records_provider: Callable[..., List[object]] = default_ftp_records,
        clock: Clock = _utc_now_iso,
        tiers: Sequence[str] = ("raw", "refined"),
        ftp_client_factory: Optional[Callable[[], Any]] = None,
        dbc_reader: Optional[Callable[[Path], Any]] = None,
    ) -> None:
        self.bronze_root = Path(bronze_root)
        self._service = service
        self.ledger = ledger or Ledger(self.bronze_root / "_ledger.csv")
        self.records_provider = records_provider
        self.clock = clock
        self.tiers = tuple(tiers)
        self.ftp_client_factory = ftp_client_factory
        self.dbc_reader = dbc_reader

    @property
    def service(self) -> Any:
        if self._service is None:
            from guaraci.services.downloads import DownloadService

            self._service = DownloadService()
        return self._service

    # -- source resolution ----------------------------------------------------
    def profiles(self, sources: Optional[Sequence[str]] = None) -> List[SourceProfile]:
        descriptors = self.service.list_sources()
        resolved = [profile_for(d.source, d.mode) for d in descriptors]
        if sources:
            wanted = {s.strip().lower() for s in sources}
            resolved = [p for p in resolved if p.source in wanted]
        return resolved

    # -- sweeps ---------------------------------------------------------------
    def backfill(
        self,
        sources: Optional[Sequence[str]] = None,
        *,
        dry_run: bool = False,
        current_year: Optional[int] = None,
        progress: Optional[ProgressHook] = None,
    ) -> RunReport:
        return self._sweep(
            "backfill",
            sources,
            dry_run=dry_run,
            current_year=current_year,
            progress=progress,
            plan=lambda profile: plan_backfill(
                profile,
                current_year=current_year,
                records_provider=self.records_provider,
            ),
        )

    def update(
        self,
        sources: Optional[Sequence[str]] = None,
        *,
        dry_run: bool = False,
        current_year: Optional[int] = None,
        progress: Optional[ProgressHook] = None,
    ) -> RunReport:
        return self._sweep(
            "update",
            sources,
            dry_run=dry_run,
            current_year=current_year,
            progress=progress,
            plan=lambda profile: plan_update(
                profile,
                self.ledger,
                current_year=current_year,
                records_provider=self.records_provider,
            ),
        )

    # -- internals ------------------------------------------------------------
    def _sweep(
        self,
        mode: str,
        sources: Optional[Sequence[str]],
        *,
        dry_run: bool,
        current_year: Optional[int],
        progress: Optional[ProgressHook],
        plan: Callable[[SourceProfile], List[FetchUnit]],
    ) -> RunReport:
        run_id = self._new_run_id(mode)
        report = RunReport(run_id=run_id, mode=mode, dry_run=dry_run)

        for profile in self.profiles(sources):
            if not profile.auto:
                report.skipped_sources.append(
                    {"source": profile.source, "reason": profile.note}
                )
                continue
            try:
                units = plan(profile)
            except Exception as exc:  # noqa: BLE001 — one bad source must not kill the sweep
                report.source_errors.append({"source": profile.source, "error": str(exc)})
                continue
            if not units:
                continue
            rows = self._materialise(profile, units, run_id=run_id, dry_run=dry_run)
            report.record(profile.source, rows)
            if progress is not None:
                progress(profile, rows)

        return report

    def _materialise(
        self,
        profile: SourceProfile,
        units: Sequence[FetchUnit],
        *,
        run_id: str,
        dry_run: bool,
    ) -> List[LedgerRow]:
        ts = self.clock()
        # Append incremental: cada linha vai ao ledger assim que existe, para
        # que um crash no meio do sweep não perca o rastro do que já foi feito.
        on_row = None if dry_run else self.ledger.append
        if profile.kind.is_ftp():
            rows = run_ftp_batch(
                units,
                bronze_root=self.bronze_root,
                run_id=run_id,
                ts=ts,
                ledger=self.ledger,
                dry_run=dry_run,
                tiers=self.tiers,
                client_factory=self.ftp_client_factory,
                dbc_reader=self.dbc_reader,
                on_row=on_row,
            )
        else:
            rows = []
            for unit in units:
                row = run_via_service(
                    unit,
                    service=self.service,
                    bronze_root=self.bronze_root,
                    run_id=run_id,
                    ts=ts,
                    dry_run=dry_run,
                )
                rows.append(row)
                if on_row is not None:
                    on_row(row)
        return rows

    def _new_run_id(self, mode: str) -> str:
        # 20 dígitos preservam subsegundos do timestamp ISO — dois runs no
        # mesmo segundo não colidem mais no run_id.
        digits = re.sub(r"[^0-9]", "", self.clock())[:20] or "0"
        return f"{mode}_{digits}"
