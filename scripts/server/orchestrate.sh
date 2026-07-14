#!/usr/bin/env bash
# Guaraci bronze orchestrator — cron entrypoint (Linux server, e.g. the Sabiá host).
#
# Thin wrapper around `guaraci orchestrate`. Point cron at this; it does the
# rest (lock, log, run). Everything below is tunable via environment variables.
#
#   GUARACI_BRONZE_ROOT   where the bronze tree + _ledger.csv live   (required)
#   GUARACI_PYTHON        python entrypoint     (default: python)
#   GUARACI_ORCH_MODE     update | backfill     (default: update)
#   GUARACI_ORCH_ARGS     extra args passed to the subcommand (e.g. "-s sih -s sim")
#
# Example crontab (daily 03:00; first run once by hand with MODE=backfill):
#   0 3 * * *  GUARACI_BRONZE_ROOT=/data/bronze /opt/guaraci/scripts/server/orchestrate.sh
set -euo pipefail

BRONZE_ROOT="${GUARACI_BRONZE_ROOT:?set GUARACI_BRONZE_ROOT to the bronze output root}"
PYTHON_BIN="${GUARACI_PYTHON:-python}"
MODE="${GUARACI_ORCH_MODE:-update}"
EXTRA_ARGS="${GUARACI_ORCH_ARGS:-}"

mkdir -p "${BRONZE_ROOT}/_logs"
LOG_FILE="${BRONZE_ROOT}/_logs/orchestrate-$(date -u +%Y%m%d).log"
LOCK_DIR="${BRONZE_ROOT}/_logs/.orchestrate.lock"

# Atomic lock: a stale lock from a crashed run must be cleared by hand — better
# a skipped run than two sweeps writing the same ledger concurrently.
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "[$(date -u +%FT%TZ)] another orchestrate run holds ${LOCK_DIR}; skipping" >>"${LOG_FILE}"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

echo "[$(date -u +%FT%TZ)] orchestrate ${MODE} start (root=${BRONZE_ROOT})" >>"${LOG_FILE}"
export GUARACI_BRONZE_ROOT="${BRONZE_ROOT}"

set +e
# shellcheck disable=SC2086
"${PYTHON_BIN}" -m guaraci.cli.main orchestrate "${MODE}" ${EXTRA_ARGS} >>"${LOG_FILE}" 2>&1
STATUS=$?
set -e

echo "[$(date -u +%FT%TZ)] orchestrate ${MODE} done (exit=${STATUS})" >>"${LOG_FILE}"
exit "${STATUS}"
