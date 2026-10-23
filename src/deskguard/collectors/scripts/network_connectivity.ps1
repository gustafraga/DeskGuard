<#
Coleta de conectividade de rede (DNS, ICMP e TCP) via PowerShell.

IMPORTANTE: ASCII puro de proposito. O PowerShell 5.1 interpreta .ps1 sem BOM
usando a codificacao ANSI do sistema e reconhece aspas "inteligentes"
(U+201C/U+201D) como delimitadores de string; um caractere nao-ASCII em um
docstring encerra a string mais cedo e derruba o parser. O arquivo tambem e
mantido pequeno: o runner entrega o script por -EncodedCommand e a linha de
comando do Windows tem limite de tamanho.

Barreira de seguranca mais sensivel do DeskGuard: so emite pacotes para
destinos autorizados, lidos DENTRO do script.

Regras:
  * a lista de autorizados e relida do arquivo allowlist_path do payload; se
    nao existir ou for invalido, nenhum destino externo e sondado;
  * destinos fora da lista sao descartados e registrados em rejected_targets
    (nao ha sondagem silenciosa);
  * alem dos autorizados, so localhost e o gateway padrao do proprio endpoint
    sao permitidos, lidos da tabela de rotas local;
  * por destino: resolucao DNS, ICMP e TCP nas portas autorizadas, de forma
    independente;
  * sondagens via .NET (System.Net.Dns, System.Net.NetworkInformation.Ping,
    System.Net.Sockets.TcpClient), com limite de tempo. Nada e gravado.

Dados NAO coletados: conteudo de trafego, credenciais, cabecalhos de pacotes,
historico de navegacao e qualquer dado de usuario.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# --- Parametros (recebidos por arquivo JSON, nunca pela linha de comando) ---
$allowlistPath = ''
$requestedTargets = @()
$timeoutMs = 3000
$payloadPath = $env:DESKGUARD_PAYLOAD_PATH
if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try {
        $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($payload.PSObject.Properties.Name -contains 'allowlist_path') {
            $allowlistPath = [string]$payload.allowlist_path
        }
        if ($payload.PSObject.Properties.Name -contains 'timeout_ms') {
            $timeoutMs = [int]$payload.timeout_ms
        }
        if ($timeoutMs -lt 500) { $timeoutMs = 500 }
        if ($timeoutMs -gt 10000) { $timeoutMs = 10000 }
        if ($payload.PSObject.Properties.Name -contains 'targets') {
            $requestedTargets = @($payload.targets)
        }
    } catch {
        $requestedTargets = @()
    }
}

function Test-HostName {
    param([string]$Name)
    if (-not $Name) { return $false }
    if ($Name.Length -gt 253) { return $false }
    return [bool]($Name -match '^[A-Za-z0-9]([A-Za-z0-9._-]{0,251}[A-Za-z0-9])?$')
}

function Test-IpLiteral {
    param([string]$Name)
    if ($Name -notmatch '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$') { return $false }
    foreach ($part in $Matches[1..4]) {
        if ([int]$part -lt 0 -or [int]$part -gt 255) { return $false }
    }
    return $true
}

function Get-TargetPorts {
    param($Entry)
    if ($null -eq $Entry) { return @(80, 443) }
    if ($Entry -is [string]) { return @(80, 443) }
    if ($Entry.PSObject.Properties.Name -contains 'ports') {
        $ports = @()
        foreach ($port in @($Entry.ports)) {
            try { $ports += [int]$port } catch { }
        }
        if ($ports.Count -gt 0) { return $ports }
    }
    return @(80, 443)
}

function Get-TargetPing {
    param($Entry)
    if ($null -eq $Entry) { return $true }
    if ($Entry -is [string]) { return $true }
    if ($Entry.PSObject.Properties.Name -contains 'ping') { return [bool]$Entry.ping }
    return $true
}

function Get-TargetDescription {
    param($Entry)
    if ($null -eq $Entry) { return '' }
    if ($Entry -is [string]) { return '' }
    if ($Entry.PSObject.Properties.Name -contains 'description') { return [string]$Entry.description }
    return ''
}

# --- Lista de destinos autorizados (relida dentro do script) ----------------
$authorized = @{}
$allowlistAvailable = $false
if ($allowlistPath -and (Test-Path -LiteralPath $allowlistPath)) {
    try {
        $document = Get-Content -LiteralPath $allowlistPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $entries = @()
        if ($document -is [System.Array]) {
            $entries = $document
        } elseif ($null -ne $document -and $document.PSObject.Properties.Name -contains 'targets') {
            $entries = @($document.targets)
        }
        foreach ($entry in $entries) {
            $hostName = ''
            if ($entry -is [string]) { $hostName = $entry } else { $hostName = [string]$entry.host }
            $hostName = $hostName.Trim().ToLower()
            if (-not (Test-HostName $hostName)) { continue }
            $authorized[$hostName] = @{
                ports       = @(Get-TargetPorts $entry)
                ping        = (Get-TargetPing $entry)
                description = (Get-TargetDescription $entry)
            }
        }
        $allowlistAvailable = $true
    } catch {
        $allowlistAvailable = $false
        $authorized = @{}
    }
}

# --- Montagem da lista efetiva de destinos ----------------------------------
$effective = @()
$rejected = @()

foreach ($entry in $requestedTargets) {
    $hostName = ''
    if ($entry -is [string]) { $hostName = $entry } else { $hostName = [string]$entry.host }
    $hostName = $hostName.Trim().ToLower()
    if (-not (Test-HostName $hostName)) {
        $rejected += [ordered]@{ host = $hostName; reason = 'nome de host invalido' }
        continue
    }
    if (-not $authorized.ContainsKey($hostName)) {
        $rejected += [ordered]@{ host = $hostName; reason = 'destino nao autorizado' }
        continue
    }
    # As portas, a opcao de ping e a descricao vem SEMPRE da lista relida
    # dentro do script, nunca do payload recebido. Assim, mesmo que o
    # payload seja adulterado, a faixa de sondagem nao aumenta.
    $allowed = $authorized[$hostName]
    $effective += [ordered]@{
        host        = $hostName
        ports       = @($allowed.ports)
        ping        = [bool]$allowed.ping
        description = [string]$allowed.description
        source      = 'allowlist'
    }
}

# --- Destinos implicitos: localhost e gateway padrao do proprio endpoint ----
$gateways = @()
try {
    foreach ($config in @(Get-NetIPConfiguration -ErrorAction Stop)) {
        foreach ($gateway in @($config.IPv4DefaultGateway)) {
            if ($gateway -and $gateway.NextHop) { $gateways += [string]$gateway.NextHop }
        }
    }
} catch { }
if ($gateways.Count -eq 0) {
    try {
        foreach ($route in @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop)) {
            if ($route.NextHop) { $gateways += [string]$route.NextHop }
        }
    } catch { }
}
$gateways = @($gateways | Select-Object -Unique)

$effective += [ordered]@{
    host        = 'localhost'
    ports       = @()
    ping        = $true
    description = 'Loopback local do proprio endpoint'
    source      = 'implicit'
}
foreach ($gateway in $gateways) {
    $effective += [ordered]@{
        host        = $gateway
        ports       = @()
        ping        = $true
        description = 'Gateway padrao configurado no endpoint'
        source      = 'implicit'
    }
}

# --- Sondagens --------------------------------------------------------------
$results = @()
foreach ($target in $effective) {
    $hostName = [string]$target.host

    # DNS
    $dnsAddresses = @()
    $dnsResolved = $false
    $dnsError = ''
    $skipDns = $false
    if ($hostName -eq 'localhost') {
        $dnsAddresses = @('127.0.0.1')
        $dnsResolved = $true
        $skipDns = $true
    } elseif (Test-IpLiteral $hostName) {
        $dnsAddresses = @($hostName)
        $dnsResolved = $true
        $skipDns = $true
    } else {
        try {
            $resolved = [System.Net.Dns]::GetHostAddresses($hostName)
            $dnsAddresses = @($resolved | ForEach-Object { $_.IPAddressToString })
            $dnsResolved = $dnsAddresses.Count -gt 0
            if (-not $dnsResolved) { $dnsError = 'Resolucao sem endereco retornado.' }
        } catch {
            $inner = $_.Exception
            while ($inner.InnerException) { $inner = $inner.InnerException }
            $code = ''
            try { $code = [string]$inner.SocketErrorCode } catch { }
            $dnsError = "Falha de resolucao DNS ($code)."
        }
    }

    # ICMP
    $icmpAttempted = [bool]$target.ping -and $dnsResolved
    $icmpReachable = $false
    $icmpStatus = ''
    $icmpRtt = $null
    $icmpError = ''
    if ($icmpAttempted) {
        foreach ($address in $dnsAddresses) {
            $ping = New-Object System.Net.NetworkInformation.Ping
            try {
                $reply = $ping.Send($address, $timeoutMs)
                $icmpStatus = [string]$reply.Status
                if ($reply.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {
                    $icmpReachable = $true
                    $icmpRtt = [int]$reply.RoundtripTime
                    break
                }
            } catch {
                $icmpError = [string]$_.Exception.Message
            } finally {
                $ping.Dispose()
            }
        }
    } elseif ($target.ping -and -not $dnsResolved) {
        $icmpError = 'ICMP nao executado: o nome nao foi resolvido.'
    }

    # TCP
    $tcpResults = @()
    foreach ($port in @($target.ports)) {
        $state = 'erro'
        $errText = ''
        $attempts = @($dnsAddresses)
        foreach ($address in $attempts) {
            $client = New-Object System.Net.Sockets.TcpClient
            try {
                $async = $client.BeginConnect($address, [int]$port, $null, $null)
                if ($async.AsyncWaitHandle.WaitOne($timeoutMs, $false)) {
                    $client.EndConnect($async)
                    $state = 'aberta'
                    $errText = ''
                    break
                }
                $state = 'tempo_esgotado'
                $errText = "Sem resposta em $timeoutMs ms."
            } catch [System.Net.Sockets.SocketException] {
                if ($_.Exception.SocketErrorCode -eq [System.Net.Sockets.SocketError]::ConnectionRefused) {
                    $state = 'recusada'
                    $errText = 'Conexao recusada pelo destino.'
                } else {
                    $state = 'erro'
                    $errText = [string]$_.Exception.Message
                }
            } catch {
                $state = 'erro'
                $errText = [string]$_.Exception.Message
            } finally {
                $client.Close()
            }
        }
        if ($attempts.Count -eq 0) {
            $state = 'sem_resolucao'
            $errText = 'Host nao resolvido: conexao nao tentada.'
        }
        $tcpResults += [ordered]@{
            port  = [int]$port
            state = $state
            error = $errText
        }
    }

    $results += [ordered]@{
        host        = $hostName
        source      = [string]$target.source
        description = [string]$target.description
        dns         = [ordered]@{
            resolved  = $dnsResolved
            addresses = $dnsAddresses
            error     = $dnsError
            skipped   = $skipDns
        }
        icmp        = [ordered]@{
            attempted = $icmpAttempted
            reachable = $icmpReachable
            status    = $icmpStatus
            rtt_ms    = $icmpRtt
            error     = $icmpError
        }
        tcp         = $tcpResults
    }
}

$data = [ordered]@{
    allowlist = [ordered]@{
        path      = $allowlistPath
        available = $allowlistAvailable
        count     = $authorized.Count
    }
    rejected_targets = $rejected
    gateways         = $gateways
    timeout_ms       = $timeoutMs
    targets          = $results
}

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 8 -Compress
