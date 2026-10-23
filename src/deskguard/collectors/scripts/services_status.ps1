<#
Coleta do estado dos servicos essenciais do Windows via PowerShell.

IMPORTANTE: este arquivo e mantido em ASCII puro de proposito. O PowerShell
5.1 interpreta arquivos .ps1 sem BOM usando a codificacao ANSI do sistema e
reconhece aspas "inteligentes" (U+201C/U+201D) como delimitadores de string.
Um caractere nao-ASCII dentro de um docstring pode, portanto, encerrar a
string mais cedo e derrubar o parser.

Objetivo: responder as perguntas mais comuns de Service Desk sobre servicos:
"o Spooler esta parado", "por que o endpoint nao resolve nomes", "o Windows
Update esta desativado" e "qual servico depende do WMI".

Servicos monitorados (grupo essencial):
  Spooler    - fila de impressao (Print Spooler)
  Dnscache   - cliente DNS
  DHCP       - cliente DHCP
  WlanSvc    - configuracao automatica de rede sem fio (WLAN AutoConfig)
  wuauserv   - Windows Update

Servicos auxiliares (include_supporting = true):
  BITS       - transferencias em segundo plano
  winmgmt    - instrumentacao de gerenciamento do Windows (WMI)
  RpcSs      - chamada remota de procedimento (RPC)
  DcomLaunch - inicializador de processos DCOM
  DPS        - politica de diagnostico

Escopo de dados coletados (somente leitura):
  * nome, nome de exibicao, estado atual e tipo de inicializacao;
  * caminho do executavel do servico, sem argumentos de linha de comando;
  * codigo de saida do ultimo encerramento;
  * servicos dos quais depende e servicos que dependem dele.

Acoes explicitamente NAO executadas (todas alteram o sistema):
  * Start-Service, Stop-Service, Restart-Service, Set-Service;
  * sc.exe config, sc.exe start, sc.exe stop;
  * alteracoes no registro ou em arquivos de configuracao de servico.

Dados NAO coletados: conta de execucao do servico, configuracao interna,
credenciais, conteudo dos arquivos de log e qualquer dado de usuario.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$data = [ordered]@{}

# --- Parametros (recebidos por arquivo JSON, nunca pela linha de comando) ---
$includeSupporting = $true
$payloadPath = $env:DESKGUARD_PAYLOAD_PATH
if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try {
        $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($payload.PSObject.Properties.Name -contains 'include_supporting') {
            $includeSupporting = [bool]$payload.include_supporting
        }
    } catch { }
}

$essentialServices = @('Spooler', 'Dnscache', 'DHCP', 'WlanSvc', 'wuauserv')
$supportingServices = @('BITS', 'winmgmt', 'RpcSs', 'DcomLaunch', 'DPS')

$monitored = @($essentialServices)
if ($includeSupporting) {
    $monitored += $supportingServices
}

# Traducao dos valores do Windows para o vocabulario do DeskGuard.
$startModeMap = @{
    'Auto'      = 'Automatic'
    'Manual'    = 'Manual'
    'Disabled'  = 'Disabled'
    'Automatic' = 'Automatic'
}

$stateMap = @{
    'Running'       = 'Running'
    'Stopped'       = 'Stopped'
    'Start Pending' = 'Pending'
    'Stop Pending'  = 'Pending'
    'Paused'        = 'Paused'
}

function Get-ServiceExecutable {
    <#
    Extrai apenas o caminho do executavel, descartando argumentos de linha
    de comando que o WMI por vezes acrescenta.
    #>
    param([string]$RawPath)

    $path = [string]$RawPath
    try {
        $index = $path.IndexOf('.exe', [System.StringComparison]::OrdinalIgnoreCase)
        if ($index -ge 0) {
            $path = $path.Substring(0, $index + 4)
        }
    } catch { }
    return $path
}

function ConvertTo-NameList {
    <#
    Converte uma colecao de controladores de servico em uma lista de nomes,
    ignorando entradas vazias.
    #>
    param($Items)

    $names = @()
    if ($null -eq $Items) { return $names }
    foreach ($item in @($Items)) {
        if ($null -eq $item) { continue }
        $name = ''
        try { $name = [string]$item.Name } catch { }
        if (-not $name) { continue }
        $names += $name
    }
    return $names
}

function ConvertTo-ServiceRecord {
    param(
        [string]$Name,
        [string]$DisplayName,
        [string]$Status,
        [string]$StartType,
        [string]$Path,
        $ExitCode,
        [string]$ServiceType,
        [string[]]$DependsOn,
        [string[]]$Dependents,
        [bool]$Found,
        [string]$FailureMessage
    )

    # Um array vazio chega como $null quando vinculado a um parametro tipado:
    # normalizar aqui evita que o JSON traga "null" no lugar de uma lista.
    if ($null -eq $DependsOn) { $DependsOn = @() }
    if ($null -eq $Dependents) { $Dependents = @() }

    return [ordered]@{
        name         = $Name
        display_name = $DisplayName
        status       = $Status
        start_type   = $StartType
        path         = $Path
        exit_code    = $ExitCode
        service_type = $ServiceType
        depends_on   = @($DependsOn)
        dependents   = @($Dependents)
        found        = $Found
        error        = $FailureMessage
    }
}

# --- Enriquecimento opcional via WMI -----------------------------------------
# Caminho do executavel, codigo de saida e tipo de servico. A ausencia do WMI
# nao invalida a coleta: estado e dependencias vem do Get-Service.
$enrichment = @{}
$moduleError = ''
try {
    foreach ($item in @(Get-CimInstance -ClassName Win32_Service -ErrorAction Stop)) {
        $key = [string]$item.Name
        if (-not $key) { continue }
        $enrichment[$key] = $item
    }
} catch {
    $moduleError = [string]$_.Exception.Message
}

# --- services.inventory -----------------------------------------------------
$inventoryAvailable = $false
$inventoryError = ''
$services = @()

foreach ($name in $monitored) {
    $controller = $null
    try {
        $controller = Get-Service -Name $name -ErrorAction Stop
    } catch {
        $services += ConvertTo-ServiceRecord -Name $name -Status 'Unknown' -StartType 'Unknown' `
            -DependsOn @() -Dependents @() -Found $false `
            -FailureMessage 'Servico nao encontrado neste endpoint.'
        continue
    }

    $rawStatus = ''
    try { $rawStatus = [string]$controller.Status } catch { }
    $status = 'Unknown'
    if ($stateMap.ContainsKey($rawStatus)) { $status = $stateMap[$rawStatus] }

    $rawStart = ''
    try { $rawStart = [string]$controller.StartType } catch { }
    $startType = 'Unknown'
    if ($startModeMap.ContainsKey($rawStart)) { $startType = $startModeMap[$rawStart] }

    $dependsOn = @()
    $dependentsOf = @()
    try { $dependsOn = ConvertTo-NameList -Items $controller.ServicesDependedOn } catch { $dependsOn = @() }
    try { $dependentsOf = ConvertTo-NameList -Items $controller.DependentServices } catch { $dependentsOf = @() }

    $displayName = ''
    try { $displayName = [string]$controller.DisplayName } catch { }

    $path = ''
    $exitCode = $null
    $serviceType = ''
    if ($enrichment.ContainsKey($name)) {
        $extra = $enrichment[$name]
        try { $path = Get-ServiceExecutable -RawPath ([string]$extra.PathName) } catch { }
        try { $exitCode = [int]$extra.ExitCode } catch { }
        try { $serviceType = [string]$extra.ServiceType } catch { }
        if (-not $displayName) {
            try { $displayName = [string]$extra.DisplayName } catch { }
        }
    }

    $services += ConvertTo-ServiceRecord -Name $name -DisplayName $displayName `
        -Status $status -StartType $startType -Path $path -ExitCode $exitCode `
        -ServiceType $serviceType -DependsOn $dependsOn -Dependents $dependentsOf `
        -Found $true -FailureMessage ''
}

$inventoryAvailable = ($services.Count -gt 0)
if (-not $inventoryAvailable) {
    $inventoryError = 'Nenhum servico monitorado pode ser consultado neste endpoint.'
}

$data['services.inventory'] = [ordered]@{
    available    = $inventoryAvailable
    count        = $services.Count
    services     = $services
    error        = $inventoryError
    module_error = $moduleError
}

# --- services.dependencies --------------------------------------------------
$dependencyRows = @()
foreach ($service in $services) {
    $dependencyRows += [ordered]@{
        name       = [string]$service.name
        depends_on = @($service.depends_on)
        dependents = @($service.dependents)
    }
}

$data['services.dependencies'] = [ordered]@{
    available    = $inventoryAvailable
    count        = $dependencyRows.Count
    dependencies = $dependencyRows
    error        = $inventoryError
}

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 8 -Compress
