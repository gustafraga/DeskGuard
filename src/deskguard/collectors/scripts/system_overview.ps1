<#
Coleta de informacoes do sistema operacional Windows via PowerShell/WMI.

IMPORTANTE: este arquivo e mantido em ASCII puro de proposito. O PowerShell
5.1 interpreta arquivos .ps1 sem BOM usando a codificacao ANSI do sistema e
reconhece aspas "inteligentes" (U+201C/U+201D) como delimitadores de string.
Um caractere nao-ASCII dentro de um docstring pode, portanto, encerrar a
string mais cedo e derrubar o parser.

Objetivo: consolidar dados de inventario uteis ao atendimento de Service Desk.

Escopo de dados coletados:
  * versao, build, edicao e data de instalacao do Windows;
  * identidade do equipamento (nome, fabricante, modelo, serie, dominio);
  * tempo de atividade do sistema (ultimo boot);
  * hardware resumido (CPU, nucleos, memoria).

Dados NAO coletados: senhas, tokens, chaves, conteudo de arquivos, dados
pessoais e documentos do usuario. A conta em uso so e incluida quando o
operador solicita explicitamente por parametro.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$data = [ordered]@{}

# --- Parâmetros (recebidos por arquivo JSON, nunca pela linha de comando) ---
$includeAccount = $false
$payloadPath = $env:DESKGUARD_PAYLOAD_PATH
if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try {
        $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -ne $payload.include_account) {
            $includeAccount = [bool]$payload.include_account
        }
    } catch {
        $includeAccount = $false
    }
}

# --- os.version -----------------------------------------------------------
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $cv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop
    $installDate = $null
    if ($os.InstallDate) { $installDate = $os.InstallDate.ToString('o') }
    $data['os.version'] = [ordered]@{
        caption         = [string]$os.Caption
        version         = [string]$os.Version
        build           = [string]$os.BuildNumber
        architecture    = [string]$os.OSArchitecture
        install_date    = $installDate
        product_name    = [string]$cv.ProductName
        display_version = [string]$cv.DisplayVersion
        update_build    = [string]$cv.UBR
        locale          = [string]$os.Locale
    }
} catch {
    $data['os.version'] = [ordered]@{ error = [string]$_.Exception.Message }
}

# --- system.identity ------------------------------------------------------
try {
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    $bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction Stop
    $partOfDomain = $false
    $domain = ''
    try {
        $partOfDomain = [bool]$cs.PartOfDomain
        if ($partOfDomain) { $domain = [string]$cs.Domain }
    } catch { }

    $identity = [ordered]@{
        computer_name  = [string]$cs.Name
        manufacturer   = [string]$cs.Manufacturer
        model          = [string]$cs.Model
        system_type    = [string]$cs.SystemType
        domain         = $domain
        part_of_domain = $partOfDomain
        serial_number  = [string]$bios.SerialNumber
    }

    if ($includeAccount) {
        $account = $null
        try {
            $account = [string]([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
        } catch { }
        $identity['account'] = $account
    }

    $data['system.identity'] = $identity
} catch {
    $data['system.identity'] = [ordered]@{ error = [string]$_.Exception.Message }
}

# --- system.uptime --------------------------------------------------------
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $boot = $os.LastBootUpTime
    $lastBoot = $null
    $uptimeHours = $null
    if ($boot) {
        $lastBoot = $boot.ToString('o')
        $uptimeHours = [math]::Round(((Get-Date) - $boot).TotalHours, 2)
    }
    $data['system.uptime'] = [ordered]@{
        last_boot       = $lastBoot
        uptime_hours    = $uptimeHours
        local_time      = (Get-Date).ToString('o')
        time_zone       = [string](Get-TimeZone).Id
    }
} catch {
    $data['system.uptime'] = [ordered]@{ error = [string]$_.Exception.Message }
}

# --- system.hardware ------------------------------------------------------
try {
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    $cpu = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
    $primary = $cpu | Select-Object -First 1
    $totalMemory = [int64]$cs.TotalPhysicalMemory
    $data['system.hardware'] = [ordered]@{
        cpu_name             = [string]$primary.Name
        physical_cores       = [int]$primary.NumberOfCores
        logical_processors   = [int]$primary.NumberOfLogicalProcessors
        max_clock_mhz        = [int]$primary.MaxClockSpeed
        total_memory_bytes   = $totalMemory
        total_memory_gb      = [math]::Round($totalMemory / 1GB, 2)
    }
} catch {
    $data['system.hardware'] = [ordered]@{ error = [string]$_.Exception.Message }
}

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 6 -Compress
