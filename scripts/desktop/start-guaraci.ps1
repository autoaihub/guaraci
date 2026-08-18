param(
  [string]$Image = "guaraci",
  [string]$ContainerName = "guaraci-desktop",
  [int]$HostPort = 8002,
  # A API não tem autenticação: por padrão publica apenas em loopback.
  # Use -BindAddress 0.0.0.0 para expor na rede local de forma explícita.
  [string]$BindAddress = "127.0.0.1",
  [string]$ProjectDir = (Get-Location).Path,
  [switch]$Rebuild,
  [switch]$AccessLog
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Error $Message
  exit 1
}

$checkDockerScript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "check-docker.ps1"
& $checkDockerScript
if ($LASTEXITCODE -ne 0) {
  Fail "Docker nao esta pronto (veja o diagnostico acima). Resolva e rode novamente."
}

$projectPath = (Resolve-Path $ProjectDir).Path
$desktopPath = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($desktopPath) -or -not (Test-Path $desktopPath)) {
  $desktopPath = $projectPath
}
$hostDownloadsPath = Join-Path $desktopPath "Guaraci Downloads"
New-Item -ItemType Directory -Path $hostDownloadsPath -Force | Out-Null
$imageId = ""

if (-not $Rebuild) {
  try {
    $imageId = docker image inspect $Image --format "{{.Id}}" 2>$null
  }
  catch {
    $imageId = ""
  }
}

if ($Rebuild -or [string]::IsNullOrWhiteSpace($imageId)) {
  Write-Host "[guaraci] Build da imagem '$Image'..."
  docker build -t $Image $projectPath
  if ($LASTEXITCODE -ne 0) {
    Fail "Falha no build da imagem Docker."
  }
}

$existing = docker ps -a --filter "name=^/${ContainerName}$" --format "{{.ID}}|{{.Status}}"
$alreadyRunning = $false

if (-not [string]::IsNullOrWhiteSpace($existing)) {
  $parts = $existing.Split("|")
  if ($parts.Length -ge 2 -and $parts[1].StartsWith("Up")) {
    $alreadyRunning = $true
    Write-Host "[guaraci] Container '$ContainerName' já está ativo."
  }
  else {
    Write-Host "[guaraci] Removendo container anterior '$ContainerName'..."
    docker rm -f $ContainerName | Out-Null
  }
}

if (-not $alreadyRunning) {
  Write-Host "[guaraci] Iniciando API em http://localhost:$HostPort ..."
  $uvicornArgs = @("uvicorn", "guaraci.api.main:app", "--host", "0.0.0.0", "--port", "8000")
  if (-not $AccessLog) {
    $uvicornArgs += "--no-access-log"
  }
  docker run -d `
    --name $ContainerName `
    -p "$BindAddress`:$HostPort`:8000" `
    -v "${projectPath}:/app" `
    -v "${hostDownloadsPath}:/downloads" `
    -e "GUARACI_HOST_APP_ROOT=${projectPath}" `
    -e "GUARACI_CONTAINER_APP_ROOT=/app" `
    -e "GUARACI_HOST_DOWNLOADS_ROOT=${hostDownloadsPath}" `
    -e "GUARACI_CONTAINER_DOWNLOADS_ROOT=/downloads" `
    -e "GUARACI_DEFAULT_DOWNLOAD_ROOT=/downloads" `
    -e "GUARACI_DEFAULT_OUTPUT_ROOT=/downloads" `
    -e "GUARACI_OUTPUT_ROOT=/downloads" `
    $Image `
    @uvicornArgs | Out-Null

  if ($LASTEXITCODE -ne 0) {
    Fail "Não foi possível iniciar o container '$ContainerName'."
  }
}

$healthUrl = "http://localhost:$HostPort/health"
$maxAttempts = 45
$ready = $false

for ($i = 1; $i -le $maxAttempts; $i++) {
  try {
    $resp = Invoke-RestMethod -Method Get -Uri $healthUrl -TimeoutSec 2
    if ($resp.status -eq "ok") {
      $ready = $true
      break
    }
  }
  catch {
    Start-Sleep -Milliseconds 500
  }
}

if (-not $ready) {
  Fail "API não respondeu em $healthUrl dentro do tempo esperado."
}

$uiUrl = "http://localhost:$HostPort/"
Write-Host "[guaraci] API pronta em $uiUrl"
Write-Host "[guaraci] Consulte seus downloads em: $hostDownloadsPath"
Write-Host "[guaraci] Container: $ContainerName"
Write-Host "[guaraci] Para parar: .\\scripts\\desktop\\stop-guaraci.ps1"

try {
  Start-Process $uiUrl | Out-Null
}
catch {
  Write-Warning "Não foi possível abrir o navegador automaticamente. Abra manualmente: $uiUrl"
}
