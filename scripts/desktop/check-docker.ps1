# Diagnóstico independente do Guaraci: confere se o Docker Desktop está pronto
# ANTES de rodar "docker build" ou "docker run". Rode isto primeiro se algo falhar —
# assim dá para saber se o problema é o Docker ou o Guaraci.
#
# Uso:  .\scripts\desktop\check-docker.ps1
# Sai com código 0 se tudo estiver OK, 1 caso contrário.

Set-StrictMode -Version Latest

function Write-Status([bool]$Ok, [string]$Label, [string]$Detail = "") {
  if ($Ok) {
    Write-Host "[OK]    $Label" -ForegroundColor Green
  }
  else {
    Write-Host "[FALHA] $Label" -ForegroundColor Red
  }
  if ($Detail) {
    Write-Host "        $Detail" -ForegroundColor DarkGray
  }
}

$allOk = $true

if (Get-Command docker -ErrorAction SilentlyContinue) {
  Write-Status $true "Docker CLI instalado"
}
else {
  Write-Status $false "Docker CLI instalado" "Baixe o Docker Desktop: https://www.docker.com/products/docker-desktop/"
  $allOk = $false
}

if ($allOk) {
  docker info *>$null
  if ($LASTEXITCODE -eq 0) {
    Write-Status $true "Docker Desktop rodando (engine responde)"
  }
  else {
    Write-Status $false "Docker Desktop rodando (engine responde)" "Abra o Docker Desktop e espere o icone da baleia parar de 'Starting...'. Se travar: feche o Docker Desktop, rode 'wsl --shutdown' e abra de novo."
    $allOk = $false
  }
}

if ($allOk) {
  docker run --rm hello-world *>$null
  if ($LASTEXITCODE -eq 0) {
    Write-Status $true "Consegue executar containers (teste hello-world)"
  }
  else {
    Write-Status $false "Consegue executar containers (teste hello-world)" "O engine respondeu mas falhou ao rodar um container. Reinicie o Docker Desktop; se persistir, Settings > Troubleshoot > Reset to factory defaults."
    $allOk = $false
  }
}

Write-Host ""
if ($allOk) {
  Write-Host "Docker esta pronto. Pode seguir com 'docker build -t guaraci .'" -ForegroundColor Green
  exit 0
}
else {
  Write-Host "Docker NAO esta pronto - resolva os itens [FALHA] acima antes de continuar." -ForegroundColor Red
  Write-Host "Se o Guaraci der erro depois disso, o problema ja nao e mais o Docker." -ForegroundColor Red
  exit 1
}
