param(
  [string]$ContainerName = "guaraci-desktop"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker CLI não encontrado."
  exit 1
}

$existing = docker ps -a --filter "name=^/${ContainerName}$" --format "{{.ID}}"
if ([string]::IsNullOrWhiteSpace($existing)) {
  Write-Host "[guaraci] Container '$ContainerName' não existe."
  exit 0
}

Write-Host "[guaraci] Parando e removendo '$ContainerName'..."
docker rm -f $ContainerName | Out-Null
Write-Host "[guaraci] Container removido."
