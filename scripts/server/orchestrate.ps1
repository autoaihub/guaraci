<#
.SYNOPSIS
  Guaraci bronze orchestrator — scheduled-task entrypoint (Windows console/server).

.DESCRIPTION
  Thin wrapper around `guaraci orchestrate`. Point Task Scheduler at this; it
  handles the lock, the log and the run. Tunable via environment variables or
  parameters:

    -BronzeRoot   where the bronze tree + _ledger.csv live   (or $env:GUARACI_BRONZE_ROOT)
    -Mode         update | backfill                          (default: update)
    -PythonBin    python entrypoint                          (default: python)
    -ExtraArgs    extra args for the subcommand, e.g. "-s sih -s sim"

.EXAMPLE
  # One-off first full extraction:
  ./orchestrate.ps1 -BronzeRoot D:\bronze -Mode backfill

.EXAMPLE
  # Register a daily 03:00 incremental run:
  #   schtasks /create /tn GuaraciOrchestrate /sc daily /st 03:00 ^
  #     /tr "pwsh -File C:\guaraci\scripts\server\orchestrate.ps1 -BronzeRoot D:\bronze"
#>
[CmdletBinding()]
param(
  [string]$BronzeRoot = $env:GUARACI_BRONZE_ROOT,
  [ValidateSet("update", "backfill")][string]$Mode = ($env:GUARACI_ORCH_MODE ? $env:GUARACI_ORCH_MODE : "update"),
  [string]$PythonBin = ($env:GUARACI_PYTHON ? $env:GUARACI_PYTHON : "python"),
  [string]$ExtraArgs = $env:GUARACI_ORCH_ARGS
)
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BronzeRoot)) {
  throw "Set -BronzeRoot or `$env:GUARACI_BRONZE_ROOT to the bronze output root."
}

$logDir = Join-Path $BronzeRoot "_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd")
$logFile = Join-Path $logDir "orchestrate-$stamp.log"
$lockDir = Join-Path $logDir ".orchestrate.lock"

# Atomic lock: creating the directory fails if another run holds it.
try { New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop | Out-Null }
catch {
  Add-Content $logFile "[$((Get-Date).ToUniversalTime().ToString('o'))] another run holds $lockDir; skipping"
  exit 0
}

try {
  Add-Content $logFile "[$((Get-Date).ToUniversalTime().ToString('o'))] orchestrate $Mode start (root=$BronzeRoot)"
  $env:GUARACI_BRONZE_ROOT = $BronzeRoot
  $argList = @("-m", "guaraci.cli.main", "orchestrate", $Mode)
  if (-not [string]::IsNullOrWhiteSpace($ExtraArgs)) { $argList += $ExtraArgs.Split(" ") }

  & $PythonBin @argList *>> $logFile
  $status = $LASTEXITCODE
  Add-Content $logFile "[$((Get-Date).ToUniversalTime().ToString('o'))] orchestrate $Mode done (exit=$status)"
  exit $status
}
finally {
  Remove-Item -Recurse -Force $lockDir -ErrorAction SilentlyContinue
}
