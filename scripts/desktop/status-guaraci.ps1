param(
  [string]$ContainerName = "guaraci-desktop",
  [int]$HostPort = 8002
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker CLI não encontrado."
  exit 1
}

$rows = docker ps -a --filter "name=^/${ContainerName}$" --format "{{.Names}}|{{.Status}}|{{.Ports}}"
if ([string]::IsNullOrWhiteSpace($rows)) {
  Write-Host "[guaraci] Nenhum container encontrado com nome '$ContainerName'."
  exit 0
}

$parts = $rows.Split("|")
Write-Host "Container : $($parts[0])"
Write-Host "Status    : $($parts[1])"
if ($parts.Length -ge 3) {
  Write-Host "Ports     : $($parts[2])"
}

$healthUrl = "http://localhost:$HostPort/health"
try {
  $resp = Invoke-RestMethod -Method Get -Uri $healthUrl -TimeoutSec 2
  Write-Host "Health    : $($resp.status) (version=$($resp.version))"
}
catch {
  Write-Host "Health    : indisponível em $healthUrl"
}
