<#
.SYNOPSIS
    Verificacao ponta a ponta do DeskGuard.

.DESCRIPTION
    Executa, em ordem:
      1. a suite de testes com cobertura;
      2. o diagnostico do ambiente (deskguard doctor);
      3. execucoes reais de diagnostico (somente leitura);
      4. execucoes em modo demonstracao;
      5. as verificacoes de seguranca e de fluxo da API local;
      6. a camada desktop (janela nativa);
      7. o executavel empacotado, se ele ja existir.

    Nenhuma etapa altera o sistema. Todos os comandos usam apenas leitura.

    A etapa 7 e informativa: se o executavel ainda nao foi gerado, ela e
    apenas pulada. Para gerar, use scripts\build.ps1.

    Observacao: este arquivo e mantido em ASCII puro. O PowerShell 5.1 le
    arquivos .ps1 sem BOM usando a codificacao ANSI do sistema, e aspas
    "inteligentes" viram delimitadores de string.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
#>
[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [int]$Port = 8766,
    [switch]$SkipTests,
    [switch]$SkipPackaging
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Write-Step {
    param([string]$Title)
    Write-Host ""
    Write-Host "=============================================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "=============================================================" -ForegroundColor Cyan
}

$failures = 0
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if ($Condition) {
        Write-Host "  [OK]   $Message" -ForegroundColor Green
    } else {
        Write-Host "  [FALHA] $Message" -ForegroundColor Red
        $script:failures++
    }
}

function Write-Skip {
    param([string]$Message)
    Write-Host "  [SKIP] $Message" -ForegroundColor Yellow
}

if (-not (Test-Path $Python)) {
    Write-Error "Python nao encontrado em '$Python'. Crie o ambiente virtual primeiro."
    Pop-Location
    exit 1
}

# ---------------------------------------------------------------- 1. testes
if (-not $SkipTests) {
    Write-Step "1. Suite de testes"
    & $Python -m pytest -q --cov=deskguard --cov-report=term
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Suite de testes falhou." -ForegroundColor Red
        $failures++
    }
}

# ------------------------------------------------------------ 2. ambiente
Write-Step "2. Diagnostico do ambiente"
& $Python -m deskguard doctor

# ------------------------------------------------------- 3. execucao real
Write-Step "3. Execucoes reais (somente leitura)"
foreach ($procedure in @("system.overview", "network.configuration", "network.connectivity", "printers.status", "services.status")) {
    & $Python -m deskguard run $procedure
    $liveExit = $LASTEXITCODE
    Assert-True ($liveExit -eq 0) "Execucao real de '$procedure' terminou com codigo $liveExit"
}

# ---------------------------------------------------- 4. modo demonstracao
Write-Step "4. Execucoes em modo demonstracao"
foreach ($procedure in @("system.overview", "network.configuration", "network.connectivity", "printers.status", "services.status")) {
    & $Python -m deskguard run $procedure --mode demo
    Assert-True ($LASTEXITCODE -eq 0) "Execucao demo de '$procedure' terminou com codigo $LASTEXITCODE"
}

# --------------------------------------------------------------- 5. API
Write-Step "5. API local"
$process = $null
try {
    $process = Start-Process -FilePath $Python `
        -ArgumentList "-m", "deskguard", "serve", "--port", $Port `
        -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 6

    $base = "http://127.0.0.1:$Port"
    $health = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 10
    Write-Host "  health: $($health.status) | version $($health.version) | procedures $($health.procedures)"
    Assert-True ($health.status -eq "ok") "Endpoint /api/health respondeu"
    Assert-True ($health.procedures -ge 5) "Catalogo expoe $($health.procedures) procedimentos"

    $page = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 10
    Assert-True ($page.StatusCode -eq 200) "Interface web respondeu na raiz"

    $token = [regex]::Match($page.Content, 'name="deskguard-csrf" content="([^"]+)"').Groups[1].Value
    Assert-True (-not [string]::IsNullOrWhiteSpace($token)) "Token anti-CSRF presente na pagina"

    try {
        Invoke-RestMethod -Uri "$base/api/executions" -Method Post `
            -ContentType "application/json" -Body '{"procedure_id":"system.overview"}' `
            -TimeoutSec 10 | Out-Null
        Assert-True $false "Requisicao sem token anti-CSRF deveria ser recusada"
    } catch {
        Assert-True ($_.Exception.Response.StatusCode.value__ -eq 403) "Requisicao sem token anti-CSRF foi recusada com 403"
    }

    try {
        Invoke-RestMethod -Uri "$base/api/health" -Headers @{ Host = "atacante.example.com" } `
            -TimeoutSec 10 | Out-Null
        Assert-True $false "Host nao local deveria ser recusado"
    } catch {
        Assert-True ($_.Exception.Response.StatusCode.value__ -eq 403) "Host nao local foi recusado com 403"
    }

    $settings = Invoke-RestMethod -Uri "$base/api/settings" -TimeoutSec 10
    Assert-True ($null -ne $settings.allowlist) "Configuracao efetiva expoe a lista de autorizados"
    Write-Host "  allowlist: path=$($settings.allowlist.path) targets=$($settings.allowlist.targets.Count)"

    # Destino fora da lista de autorizados deve ser recusado com 422.
    try {
        Invoke-RestMethod -Uri "$base/api/executions" -Method Post `
            -Headers @{ "X-DeskGuard-CSRF" = $token } `
            -ContentType "application/json" `
            -Body '{"procedure_id":"network.connectivity","params":{"targets":["203.0.113.10"]}}' `
            -TimeoutSec 10 | Out-Null
        Assert-True $false "Destino fora da lista deveria ser recusado com 422"
    } catch {
        Assert-True ($_.Exception.Response.StatusCode.value__ -eq 422) "Destino fora da lista foi recusado com 422"
    }

    $run = Invoke-RestMethod -Uri "$base/api/executions" -Method Post `
        -Headers @{ "X-DeskGuard-CSRF" = $token } `
        -ContentType "application/json" `
        -Body '{"procedure_id":"system.overview","params":{}}' -TimeoutSec 10
    Assert-True (-not [string]::IsNullOrWhiteSpace($run.execution_id)) "Execucao aceita pela API"

    $executionId = $run.execution_id
    for ($i = 0; $i -lt 60; $i++) {
        $execution = Invoke-RestMethod -Uri "$base/api/executions/$executionId" -TimeoutSec 10
        if ($execution.status -ne "queued" -and $execution.status -ne "running") { break }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "  execucao: status=$($execution.status) outcome=$($execution.outcome) duracao=$($execution.duration_ms)ms"
    Assert-True ($execution.status -eq "completed") "Execucao concluida pela API"
    Assert-True ($execution.steps.Count -gt 0) "Execucao registrou $($execution.steps.Count) verificacoes"

    $report = Invoke-RestMethod -Uri "$base/api/executions/$executionId/report" -TimeoutSec 10
    Assert-True ($report.markdown.Length -gt 500) "Relatorio gerado ($($report.markdown.Length) caracteres)"
    Assert-True ($report.markdown.Contains($executionId)) "Relatorio contem o identificador da execucao"

    $export = Invoke-WebRequest -Uri "$base/api/executions/$executionId/report/export" -Method Post `
        -Headers @{ "X-DeskGuard-CSRF" = $token } `
        -ContentType "application/json" -Body '{"format":"markdown"}' `
        -UseBasicParsing -TimeoutSec 10
    Assert-True ($export.StatusCode -eq 200) "Exportacao do relatorio respondeu 200"
    Write-Host "  content-type: $($export.Headers['Content-Type'])"

    $dashboard = Invoke-RestMethod -Uri "$base/api/dashboard" -TimeoutSec 10
    Write-Host "  painel: total_executions=$($dashboard.total_executions) confirmados=$($dashboard.confirmed_issues)"
    Assert-True ($dashboard.total_executions -ge 1) "Painel calculou indicadores a partir do banco"

    $audit = Invoke-RestMethod -Uri "$base/api/audit?limit=5" -TimeoutSec 10
    Assert-True ($audit.count -ge 1) "Trilha de auditoria registrou eventos"
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
}

# ------------------------------------------------------- 6. camada desktop
Write-Step "6. Camada desktop (janela nativa)"
& $Python -m deskguard desktop --help | Out-Null
Assert-True ($LASTEXITCODE -eq 0) "Comando 'deskguard desktop' esta disponivel"

$desktopJson = & $Python -c "import json; from deskguard.desktop import desktop_availability, is_frozen; print(json.dumps({'available': desktop_availability()['available'], 'frozen': is_frozen(), 'detail': desktop_availability()}, ensure_ascii=False))"
if ($LASTEXITCODE -ne 0) {
    Assert-True $false "Nao foi possível consultar a disponibilidade da camada desktop"
} else {
    $desktop = $desktopJson | ConvertFrom-Json
    Write-Host "  desktop: available=$($desktop.available) frozen=$($desktop.frozen)"
    if ($desktop.available) {
        Write-Host "  backend: $($desktop.detail.backend) | pywebview $($desktop.detail.pywebview_version)"
    } else {
        Write-Host "  motivo: $($desktop.detail.reason)"
        Write-Host "  orientacao: $($desktop.detail.hint)"
    }
    Assert-True ($null -ne $desktop.detail) "Camada desktop respondeu com diagnostico"
    if (-not $desktop.available) {
        Assert-True (-not [string]::IsNullOrWhiteSpace($desktop.detail.reason)) "Falha da camada desktop tem motivo declarado"
        Assert-True (-not [string]::IsNullOrWhiteSpace($desktop.detail.hint)) "Falha da camada desktop tem orientacao declarada"
    }
}

# ------------------------------------------- 7. executavel empacotado
Write-Step "7. Executavel empacotado"
$exe = Join-Path $root "dist\DeskGuard.exe"
if ($SkipPackaging) {
    Write-Skip "Verificacao do executavel pulada (-SkipPackaging)."
}
elseif (-not (Test-Path $exe)) {
    Write-Skip "dist\DeskGuard.exe nao encontrado. Gere com: powershell -File .\scripts\build.ps1"
}
else {
    $version = & $exe --version
    Assert-True ($LASTEXITCODE -eq 0) "Executavel respondeu ao --version ($version)"

    $catalog = & $exe list
    Assert-True ($LASTEXITCODE -eq 0) "Executavel listou o catalogo"
    Assert-True (($catalog -join "`n") -match "system\.overview") "Catalogo do executavel contem system.overview"
    Assert-True (($catalog -join "`n") -match "printers\.status") "Catalogo do executavel contem printers.status"
    Assert-True (($catalog -join "`n") -match "services\.status") "Catalogo do executavel contem services.status"

    $exeDoctor = (& $exe doctor) -join "`n" | ConvertFrom-Json
    Assert-True ($exeDoctor.procedures -ge 5) "Executavel expoe $($exeDoctor.procedures) procedimentos"
    Assert-True ($exeDoctor.powershell_available) "Executavel encontrou o PowerShell"

    $sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 2)
    Write-Host "  executavel: $exe ($sizeMb MB)"
}

# ------------------------------------------------------------- resultado
Write-Step "Resultado"
if ($failures -eq 0) {
    Write-Host "  Todas as verificacoes passaram." -ForegroundColor Green
} else {
    Write-Host "  $failures verificacao(oes) falharam." -ForegroundColor Red
}

Pop-Location
exit $failures
