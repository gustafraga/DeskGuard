<#
Coleta defensiva de configuracoes de seguranca do Windows via PowerShell.

IMPORTANTE: ASCII puro de proposito. O PowerShell 5.1 interpreta .ps1 sem BOM
usando a codificacao ANSI do sistema e reconhece aspas "inteligentes"
(U+201C/U+201D) como delimitadores de string; um caractere nao-ASCII em um
docstring encerra a string mais cedo e derruba o parser. O arquivo tambem e
mantido pequeno: o runner entrega o script por -EncodedCommand e a linha de
comando do Windows tem limite de tamanho.

Objetivo (somente leitura, nada e alterado):
  1. Windows Firewall - estado dos perfis Dominio, Privado e Publico;
  2. protecao antivirus - motor ativo, idade das assinaturas e tempo desde
     a ultima verificacao;
  3. configuracoes basicas - UAC, bloqueio de tela, acesso remoto,
     criptografia de disco e conta de convidado (Guest).

Nenhum comando que altere o sistema e executado; a lista de comandos
proibidos e verificada automaticamente pelos testes do projeto.

Dados NAO coletados: credenciais, chaves Winlogon, conteudo de arquivos,
lista de contas de usuario (a consulta e restrita a conta Guest), historico
de eventos e qualquer dado pessoal.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$data = [ordered]@{}

function Get-RegistryValue {
    # Le um valor de registro sem falhar quando a propriedade nao existe.
    param([string]$Path, [string]$Name)

    try {
        $item = Get-ItemProperty -Path $Path -ErrorAction Stop
        if ($null -eq $item) { return $null }
        if (-not $item.PSObject.Properties.Name.Contains($Name)) { return $null }
        return $item.$Name
    } catch { return $null }
}

function Get-RegistryInt {
    param([string]$Path, [string]$Name)

    $value = Get-RegistryValue -Path $Path -Name $Name
    if ($null -eq $value) { return $null }
    try { return [int]$value } catch { return $null }
}

function Get-RegistryBool {
    param([string]$Path, [string]$Name)

    $value = Get-RegistryInt -Path $Path -Name $Name
    if ($null -eq $value) { return $null }
    return ($value -eq 1)
}

function Get-Text {
    param($Value)

    if ($null -eq $Value) { return '' }
    try { return [string]$Value } catch { return '' }
}

# --- security.firewall ------------------------------------------------------
# O Windows Firewall e lido pelo modulo NetSecurity, no armazenamento local.
$firewallProfiles = @()
$firewallAvailable = $false
$firewallError = ''
$firewallModuleError = ''

try {
    foreach ($profile in @(Get-NetFirewallProfile -ErrorAction Stop)) {
        $name = Get-Text $profile.Name
        if (-not $name) { continue }

        $enabled = 'Unknown'
        try {
            if ($null -eq $profile.Enabled) { $enabled = 'Unknown' }
            elseif ([bool]$profile.Enabled) { $enabled = 'True' }
            else { $enabled = 'False' }
        } catch { $enabled = 'Unknown' }

        $firewallProfiles += [ordered]@{
            name                    = $name
            enabled                 = $enabled
            default_inbound_action  = Get-Text $profile.DefaultInboundAction
            default_outbound_action = Get-Text $profile.DefaultOutboundAction
            allow_inbound_rules     = Get-Text $profile.AllowInboundRules
        }
    }
    if ($firewallProfiles.Count -gt 0) { $firewallAvailable = $true }
    else { $firewallError = 'Nenhum perfil de firewall foi retornado pelo Windows.' }
} catch {
    $firewallModuleError = Get-Text $_.Exception.Message
    $firewallError = 'O modulo de firewall do Windows nao esta disponivel neste endpoint.'
}

$data['security.firewall'] = [ordered]@{
    available    = $firewallAvailable
    count        = $firewallProfiles.Count
    profiles     = $firewallProfiles
    error        = $firewallError
    module_error = $firewallModuleError
}

# --- security.antivirus -----------------------------------------------------
# Fontes complementares:
#   * Get-MpComputerStatus - estado detalhado do Microsoft Defender;
#   * SecurityCenter2      - produtos antivirus registrados no Windows,
#                             inclusive antivirus de terceiros.
$defender = [ordered]@{
    available                = $false
    antivirus_enabled        = $null
    realtime_protection      = $null
    antispyware_enabled      = $null
    behavior_monitor_enabled = $null
    signature_version        = ''
    signature_age_days       = $null
    signature_last_updated   = ''
    quick_scan_age_days      = $null
    full_scan_age_days       = $null
    error                    = ''
}

try {
    $status = Get-MpComputerStatus -ErrorAction Stop
    $defender['available'] = $true
    try { $defender['antivirus_enabled'] = [bool]$status.AntivirusEnabled } catch { }
    try { $defender['realtime_protection'] = [bool]$status.RealTimeProtectionEnabled } catch { }
    try { $defender['antispyware_enabled'] = [bool]$status.AntispywareEnabled } catch { }
    try { $defender['behavior_monitor_enabled'] = [bool]$status.BehaviorMonitorEnabled } catch { }
    try { $defender['signature_version'] = Get-Text $status.AntivirusSignatureVersion } catch { }
    try { $defender['signature_age_days'] = [int]$status.AntivirusSignatureAge } catch { }
    try { $defender['quick_scan_age_days'] = [int]$status.QuickScanAge } catch { }
    try { $defender['full_scan_age_days'] = [int]$status.FullScanAge } catch { }
    try {
        $stamp = $status.AntivirusSignatureLastUpdated
        if ($null -ne $stamp) {
            $defender['signature_last_updated'] = ([datetime]$stamp).ToString('yyyy-MM-ddTHH:mm:ss')
        }
    } catch { }
} catch {
    # O Defender pode nao estar instalado (antivirus de terceiro) ou o
    # servico pode estar parado. Nao e falha: a fonte seguinte responde.
    $defender['error'] = Get-Text $_.Exception.Message
}

$products = @()
$productsError = ''
try {
    $registered = @(Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop)
    foreach ($item in $registered) {
        $name = Get-Text $item.displayName
        if (-not $name) { continue }
        $stamp = ''
        try {
            if ($null -ne $item.timestamp) {
                $stamp = ([datetime]$item.timestamp).ToString('yyyy-MM-ddTHH:mm:ss')
            }
        } catch { }
        # O WMI entrega productState como decimal; a forma hexadecimal e
        # emitida junto para que a decodificacao nao dependa da notacao.
        $stateHex = ''
        try { $stateHex = '0x{0:X6}' -f [int]$item.productState } catch { }
        $products += [ordered]@{
            name             = $name
            product_state    = Get-Text $item.productState
            product_state_hex = $stateHex
            registered_at    = $stamp
        }
    }
} catch {
    $productsError = Get-Text $_.Exception.Message
}

$antivirusAvailable = ($defender['available'] -or $products.Count -gt 0)
$antivirusError = ''
if (-not $antivirusAvailable) {
    $antivirusError = 'Nenhuma informacao de protecao antivirus pode ser obtida neste endpoint.'
}

$data['security.antivirus'] = [ordered]@{
    available      = $antivirusAvailable
    defender       = $defender
    products       = $products
    product_count  = $products.Count
    error          = $antivirusError
    products_error = $productsError
}

# --- security.settings ------------------------------------------------------
$uacPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
$enableLua = Get-RegistryInt -Path $uacPath -Name 'EnableLUA'
$uac = [ordered]@{
    available                = ($null -ne $enableLua)
    enabled                  = $null
    consent_prompt_behavior  = $null
    prompt_on_secure_desktop = $null
    error                    = ''
}
if ($null -ne $enableLua) {
    $uac['enabled'] = ($enableLua -eq 1)
    $uac['consent_prompt_behavior'] = Get-RegistryInt -Path $uacPath -Name 'ConsentPromptBehaviorAdmin'
    $uac['prompt_on_secure_desktop'] = Get-RegistryBool -Path $uacPath -Name 'PromptOnSecureDesktop'
} else {
    $uac['error'] = 'A chave de politica do UAC nao pode ser lida neste endpoint.'
}

$desktopPath = 'HKCU:\Control Panel\Desktop'
$screenActive = Get-RegistryInt -Path $desktopPath -Name 'ScreenSaveActive'
$screenLock = [ordered]@{
    available          = ($null -ne $screenActive)
    screensaver_active = $null
    timeout_seconds    = $null
    password_protected = $null
    error              = ''
}
if ($null -ne $screenActive) {
    $screenLock['screensaver_active'] = ($screenActive -eq 1)
    $screenLock['timeout_seconds'] = Get-RegistryInt -Path $desktopPath -Name 'ScreenSaveTimeOut'
    $screenLock['password_protected'] = Get-RegistryBool -Path $desktopPath -Name 'ScreenSaverIsSecure'
} else {
    $screenLock['error'] = 'A configuracao de bloqueio de tela nao pode ser lida neste endpoint.'
}

$rdpPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
$denyConnections = Get-RegistryInt -Path $rdpPath -Name 'fDenyTSConnections'
$remoteDesktop = [ordered]@{
    available = ($null -ne $denyConnections)
    enabled   = $null
    error     = ''
}
if ($null -ne $denyConnections) {
    $remoteDesktop['enabled'] = ($denyConnections -eq 0)
} else {
    $remoteDesktop['error'] = 'A configuracao de acesso remoto nao pode ser lida neste endpoint.'
}

$encryption = [ordered]@{
    available         = $false
    system_volume     = ''
    protection_status = ''
    volume_status     = ''
    error             = ''
}

# A leitura do BitLocker exige privilegio elevado e consome varios segundos
# quando a chamada falha; por isso so e tentada quando o processo e elevado.
$isElevated = $false
try {
    $principal = New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent())
    $isElevated = $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { $isElevated = $false }

if (-not $isElevated) {
    $encryption['error'] = 'A leitura do estado do BitLocker exige privilegio elevado.'
} else {
    try {
        foreach ($volume in @(Get-BitLockerVolume -ErrorAction Stop)) {
            $letter = Get-Text $volume.MountPoint
            if (-not $letter) { continue }
            if (-not $encryption['system_volume']) {
                $encryption['available'] = $true
                $encryption['system_volume'] = $letter
                $encryption['protection_status'] = Get-Text $volume.ProtectionStatus
                $encryption['volume_status'] = Get-Text $volume.VolumeStatus
            }
        }
        if (-not $encryption['available']) {
            $encryption['error'] = 'Nenhum volume com informacao de criptografia foi retornado.'
        }
    } catch {
        $encryption['error'] = Get-Text $_.Exception.Message
    }
}

$guest = [ordered]@{
    available = $false
    present   = $false
    disabled  = $null
    error     = ''
}
try {
    $account = @(Get-CimInstance -ClassName Win32_UserAccount -Filter "Name='Guest' AND LocalAccount=True" -ErrorAction Stop)
    $guest['available'] = $true
    if ($account.Count -gt 0) {
        $guest['present'] = $true
        try { $guest['disabled'] = [bool]$account[0].Disabled } catch { }
    }
} catch {
    $guest['error'] = Get-Text $_.Exception.Message
}

$settingsAvailable = (
    $uac['available'] -or $screenLock['available'] -or
    $remoteDesktop['available'] -or $encryption['available'] -or
    $guest['available']
)

$data['security.settings'] = [ordered]@{
    available      = $settingsAvailable
    uac            = $uac
    screen_lock    = $screenLock
    remote_desktop = $remoteDesktop
    encryption     = $encryption
    guest_account  = $guest
    error          = ''
}

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 8 -Compress
