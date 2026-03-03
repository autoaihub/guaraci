param(
  [string]$Image = "guaraci",
  [string]$ContainerName = "guaraci-desktop",
  [int]$HostPort = 8002,
  [string]$ProjectDir = (Get-Location).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $scriptDir "start-guaraci.ps1"
$statusScript = Join-Path $scriptDir "status-guaraci.ps1"
$stopScript = Join-Path $scriptDir "stop-guaraci.ps1"

function Show-Menu {
  Clear-Host
  Write-Host "==============================="
  Write-Host " Guaraci Desktop Launcher"
  Write-Host "==============================="
  Write-Host "Container: $ContainerName"
  Write-Host "Porta    : $HostPort"
  Write-Host "Projeto  : $ProjectDir"
  Write-Host ""
  Write-Host "1) Iniciar API/UI"
  Write-Host "2) Iniciar API/UI (rebuild)"
  Write-Host "3) Status"
  Write-Host "4) Abrir UI no navegador"
  Write-Host "5) Ver logs do container"
  Write-Host "6) Parar container"
  Write-Host "0) Sair"
  Write-Host ""
}

function Invoke-Start([bool]$WithRebuild) {
  if ($WithRebuild) {
    & $startScript -Image $Image -ContainerName $ContainerName -HostPort $HostPort -ProjectDir $ProjectDir -Rebuild
  }
  else {
    & $startScript -Image $Image -ContainerName $ContainerName -HostPort $HostPort -ProjectDir $ProjectDir
  }
}

function Invoke-Status {
  & $statusScript -ContainerName $ContainerName -HostPort $HostPort
}

function Invoke-Stop {
  & $stopScript -ContainerName $ContainerName
}

function Open-UI {
  $uiUrl = "http://localhost:$HostPort/"
  try {
    Start-Process $uiUrl | Out-Null
    Write-Host "[guaraci] UI aberta em $uiUrl"
  }
  catch {
    Write-Warning "Não foi possível abrir o navegador automaticamente. Abra manualmente: $uiUrl"
  }
}

function Show-Logs {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[guaraci] Docker CLI não encontrado."
    return
  }
  Write-Host "[guaraci] CTRL+C para sair dos logs."
  docker logs -f $ContainerName
}

while ($true) {
  Show-Menu
  $choice = Read-Host "Escolha uma opção"
  switch ($choice) {
    "1" { Invoke-Start $false; Read-Host "Pressione ENTER para continuar" | Out-Null }
    "2" { Invoke-Start $true; Read-Host "Pressione ENTER para continuar" | Out-Null }
    "3" { Invoke-Status; Read-Host "Pressione ENTER para continuar" | Out-Null }
    "4" { Open-UI; Read-Host "Pressione ENTER para continuar" | Out-Null }
    "5" { Show-Logs; Read-Host "Pressione ENTER para continuar" | Out-Null }
    "6" { Invoke-Stop; Read-Host "Pressione ENTER para continuar" | Out-Null }
    "0" { break }
    default { Write-Host "Opção inválida."; Start-Sleep -Milliseconds 800 }
  }
}
