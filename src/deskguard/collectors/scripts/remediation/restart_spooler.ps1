<#
.SYNOPSIS
    DeskGuard - Auto-Remediação: Reiniciar o serviço Print Spooler.

.DESCRIPTION
    Requer confirmação explícita. Executado apenas após aprovação na interface.
    Somente leitura de estado prévio, depois reinicia o serviço.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Get-Payload {
    $path = $env:DESKGUARD_PAYLOAD_PATH
    if (-not $path) { return @{} }
    if (-not (Test-Path -LiteralPath $path)) { return @{} }
    try {
        $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
        if (-not $raw) { return @{} }
        return $raw | ConvertFrom-Json -AsHashtable
    } catch {
        return @{}
    }
}

$payload = Get-Payload
$approved = $false
if ($payload.ContainsKey("approved")) {
    $approved = [bool]$payload["approved"]
}

if (-not $approved) {
    $result = [ordered]@{
        ok = $false
        error_code = "APPROVAL_REQUIRED"
        message = "Ação requer confirmação explícita do usuário."
    }
    $result | ConvertTo-Json -Depth 4 -Compress
    exit 1
}

try {
    $serviceName = "Spooler"
    $before = Get-Service -Name $serviceName -ErrorAction Stop
    $beforeStatus = [string]$before.Status
    
    if ($beforeStatus -eq "Running") {
        Restart-Service -Name $serviceName -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
    } else {
        Start-Service -Name $serviceName -ErrorAction Stop
        Start-Sleep -Seconds 2
    }
    
    $after = Get-Service -Name $serviceName -ErrorAction Stop
    $afterStatus = [string]$after.Status
    
    $data = [ordered]@{
        service = $serviceName
        before_status = $beforeStatus
        after_status = $afterStatus
        action = "restart_or_start"
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
    }
    
    $result = [ordered]@{ ok = $true; data = $data }
    $result | ConvertTo-Json -Depth 4 -Compress
    exit 0
} catch {
    $result = [ordered]@{
        ok = $false
        error_code = "REMEDIATION_FAILED"
        message = $_.Exception.Message
    }
    $result | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
