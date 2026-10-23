<#
.SYNOPSIS
    Empacota o DeskGuard em executavel com PyInstaller.

.DESCRIPTION
    Gera um executavel autocontido em .\dist\DeskGuard\DeskGuard.exe.

    O executavel congelado carrega a aplicacao Python, os scripts
    PowerShell versionados e a interface web (modelo, CSS e JavaScript).

    Nenhuma etapa altera o sistema do operador.

.PARAMETER Python
    Interpretador Python do ambiente virtual. Padrao: .\.venv\Scripts\python.exe

.PARAMETER OneFolder
    Gera uma pasta com o executavel e suas dependencias, em vez de um unico
    arquivo .exe. Inicializa mais rapido, por nao extrair o conteudo a cada
    execucao.

.PARAMETER SkipInstall
    Nao instala o PyInstaller; assume que ele ja esta no ambiente virtual.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -OneFolder
#>
[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [switch]$OneFolder,
    [switch]$SkipInstall
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

if (-not (Test-Path $Python)) {
    Write-Error "Python nao encontrado em '$Python'. Crie o ambiente virtual primeiro."
    Pop-Location
    exit 1
}

# ------------------------------------------------------------ 1. dependencias
Write-Step "1. PyInstaller"
if (-not $SkipInstall) {
    & $Python -m pip install --disable-pip-version-check "pyinstaller>=6.0"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Falha ao instalar o PyInstaller." -ForegroundColor Red
        Pop-Location
        exit 1
    }
}

& $Python -c "import PyInstaller; print('  pyinstaller', PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  PyInstaller indisponivel no ambiente virtual." -ForegroundColor Red
    Pop-Location
    exit 1
}

# ------------------------------------------------------------------ 2. build
Write-Step "2. Empacotamento"
if ($OneFolder) {
    $env:DESKGUARD_BUILD_MODE = "onefolder"
    Write-Host "  Modo: pasta (DeskGuard.exe + dependencias)"
} else {
    $env:DESKGUARD_BUILD_MODE = "onefile"
    Write-Host "  Modo: executavel unico (DeskGuard.exe)"
}

& $Python -m PyInstaller --noconfirm --clean --distpath ".\dist" --workpath ".\build\pyinstaller" ".\packaging\deskguard.spec"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  O empacotamento falhou." -ForegroundColor Red
    Pop-Location
    exit 1
}

# --------------------------------------------------------------- 3. resultado
Write-Step "3. Resultado"
if ($OneFolder) {
    $exe = Join-Path $root "dist\DeskGuard\DeskGuard.exe"
} else {
    $exe = Join-Path $root "dist\DeskGuard.exe"
}
if (-not (Test-Path $exe)) {
    Write-Host "  Executavel nao encontrado em $exe" -ForegroundColor Red
    Pop-Location
    exit 1
}

$size = [math]::Round((Get-Item $exe).Length / 1MB, 2)
Write-Host "  Executavel: $exe ($size MB)"

Write-Host ""
Write-Host "  Verificacao rapida:"
& $exe --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "  O executavel nao respondeu ao --version." -ForegroundColor Red
    Pop-Location
    exit 1
}

& $exe list
if ($LASTEXITCODE -ne 0) {
    Write-Host "  O executavel nao listou o catalogo." -ForegroundColor Red
    Pop-Location
    exit 1
}

Write-Host ""
Write-Host "  Empacotamento concluido." -ForegroundColor Green

Pop-Location
exit 0
