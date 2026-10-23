<#
Diagnostico somente leitura de Active Directory focado no usuario logado.

IMPORTANTE: ASCII puro de proposito. O PowerShell 5.1 interpreta .ps1 sem BOM
usando a codificacao ANSI do sistema; um caractere nao-ASCII em um comentario
pode encerrar uma string mais cedo e derrubar o parser. O arquivo tambem e
mantido pequeno porque o runner entrega o script por -EncodedCommand.

Objetivo (nenhuma credencial e solicitada, nenhum privilegio elevado e exigido):
  1. consultar a conta do usuario atual usando o contexto de seguranca do
     proprio tecnico (Get-ADUser -Identity $env:USERNAME);
  2. verificar a confianca do computador com o dominio
     (Test-ComputerSecureChannel -Verbose).

Nenhum comando de alteracao e executado. Senhas, hashes e credenciais nao sao
coletados nem retornados.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Get-Text {
    param($Value)

    if ($null -eq $Value) { return '' }
    try { return [string]$Value } catch { return '' }
}

function ConvertTo-IsoDate {
    param($Value)

    if ($null -eq $Value) { return '' }
    try { return ([datetime]$Value).ToString('yyyy-MM-ddTHH:mm:ss') } catch { return '' }
}

$data = [ordered]@{}

# --- ad.account -------------------------------------------------------------
# A consulta usa o usuario atual, sem pedir senha nem credencial de
# administrador. Se o modulo ActiveDirectory (RSAT) nao estiver disponivel, a
# conta fica indisponivel e o procedimento reporta isso como inconclusivo.
$account = [ordered]@{
    username                 = Get-Text $env:USERNAME
    user_domain              = Get-Text $env:USERDOMAIN
    available                = $false
    enabled                  = $null
    locked_out               = $null
    password_expired         = $null
    account_expiration_date  = ''
    last_logon_date          = ''
    error                    = ''
}

if (-not $account['username']) {
    $account['error'] = 'A variavel de ambiente USERNAME nao esta definida.'
} else {
    try {
        Import-Module ActiveDirectory -ErrorAction Stop
        $adUser = Get-ADUser -Identity $env:USERNAME -Properties Enabled, LockedOut, PasswordExpired, AccountExpirationDate, LastLogonDate -ErrorAction Stop
        $account['available'] = $true
        try { $account['enabled'] = [bool]$adUser.Enabled } catch { }
        try { $account['locked_out'] = [bool]$adUser.LockedOut } catch { }
        try { $account['password_expired'] = [bool]$adUser.PasswordExpired } catch { }
        try { $account['account_expiration_date'] = ConvertTo-IsoDate $adUser.AccountExpirationDate } catch { }
        try { $account['last_logon_date'] = ConvertTo-IsoDate $adUser.LastLogonDate } catch { }
    } catch {
        $account['error'] = Get-Text $_.Exception.Message
    }
}

$data['ad.account'] = $account

# --- ad.domain_trust --------------------------------------------------------
# Test-ComputerSecureChannel retorna True quando o canal seguro com o dominio
# esta intacto e False quando a confianca foi quebrada. O reparo nao e feito
# aqui: ele exige privilegio de administrador e fica a cargo do tecnico.
$trust = [ordered]@{
    checked = $false
    trust_ok = $null
    domain = Get-Text $env:USERDNSDOMAIN
    error = ''
}

try {
    $trustOk = Test-ComputerSecureChannel -Verbose -ErrorAction Stop 4>$null
    if ($null -eq $trustOk) {
        $trust['error'] = 'O comando Test-ComputerSecureChannel nao retornou um resultado booleano.'
    } else {
        $trust['checked'] = $true
        $trust['trust_ok'] = [bool]$trustOk
    }
} catch {
    $trust['error'] = Get-Text $_.Exception.Message
}

$data['ad.domain_trust'] = $trust

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 6 -Compress
