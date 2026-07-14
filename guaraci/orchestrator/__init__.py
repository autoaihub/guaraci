"""Bronze orchestrator: sweep every Guaraci source into a browsable bronze tree.

Public surface::

    from guaraci.orchestrator import Orchestrator

    orch = Orchestrator(bronze_root="/data/bronze")
    report = orch.backfill(["sinan", "sim", "sih"])   # full history
    report = orch.update()                            # incremental delta

See :mod:`guaraci.orchestrator.model` for the value objects, ``cadence`` for the
per-source profiles, ``ledger`` for the CSV log, ``planner`` for unit
enumeration and ``runner`` for materialisation.
"""
from guaraci.orchestrator.cadence import SourceProfile, profile_for
from guaraci.orchestrator.ledger import Ledger, LedgerRow
from guaraci.orchestrator.model import Cadence, FetchUnit, Granularity, Kind
from guaraci.orchestrator.orchestrator import Orchestrator, RunReport

__all__ = [
    "Orchestrator",
    "RunReport",
    "Ledger",
    "LedgerRow",
    "SourceProfile",
    "profile_for",
    "FetchUnit",
    "Kind",
    "Granularity",
    "Cadence",
]
