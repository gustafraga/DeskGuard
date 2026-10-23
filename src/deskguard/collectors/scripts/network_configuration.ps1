<#
Coleta da configuracao de rede do endpoint via PowerShell.

IMPORTANTE: este arquivo e mantido em ASCII puro de proposito. O PowerShell
5.1 interpreta arquivos .ps1 sem BOM usando a codificacao ANSI do sistema e
reconhece aspas "inteligentes" (U+201C/U+201D) como delimitadores de string.
Um caractere nao-ASCII dentro de um docstring pode, portanto, encerrar a
string mais cedo e derrubar o parser. O runner do DeskGuard entrega o script
por -EncodedCommand (UTF-16LE), mas a regra vale para qualquer execucao.

Objetivo: reunir a configuracao de IP, gateway, DNS, rotas e o estado dos
adaptadores - a base para diagnosticar "sem internet", "DNS nao resolve" e
"conexao lenta".

Escopo de dados coletados:
  * adaptadores: nome, descricao, indice, estado, tipo de midia, velocidade,
    endereco MAC e se e virtual;
  * enderecos IPv4/IPv6 com prefixo e escopo;
  * gateway padrao por interface;
  * servidores DNS configurados por interface;
  * rota padrao e rotas relevantes;
  * categoria de rede (Dominio, Privada, Publica) do perfil conectado.

Dados NAO coletados: trafego de rede, conteudo de navegacao, credenciais de
Wi-Fi, chaves WEP/WPA e qualquer dado de usuario.

Todas as operacoes sao de leitura. Nenhuma configuracao e alterada.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$data = [ordered]@{}

# --- Parametros (recebidos por arquivo JSON, nunca pela linha de comando) ---
$payloadPath = $env:DESKGUARD_PAYLOAD_PATH
if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try { Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null } catch { }
}

# --- network.interfaces -----------------------------------------------------
try {
    $adapters = @(Get-NetAdapter -ErrorAction Stop | Select-Object Name, InterfaceDescription,
        InterfaceIndex, Status, MediaType, PhysicalMediaType, LinkSpeed, MacAddress,
        HardwareInterface, Virtual, ifAlias, DriverInformation)

    $items = @()
    foreach ($adapter in $adapters) {
        $driver = ''
        try { $driver = [string]$adapter.DriverInformation.DriverVersion } catch { }
        $items += [ordered]@{
            name              = [string]$adapter.Name
            interface_index   = [int]$adapter.InterfaceIndex
            description       = [string]$adapter.InterfaceDescription
            status            = [string]$adapter.Status
            media_type        = [string]$adapter.MediaType
            physical_media    = [string]$adapter.PhysicalMediaType
            link_speed        = [string]$adapter.LinkSpeed
            mac_address       = [string]$adapter.MacAddress
            hardware          = [bool]$adapter.HardwareInterface
            virtual           = [bool]$adapter.Virtual
            driver_version    = $driver
        }
    }

    $data['network.interfaces'] = [ordered]@{
        count     = $items.Count
        adapters  = $items
        up        = @($items | Where-Object { $_.status -eq 'Up' }).Count
        disabled  = @($items | Where-Object { $_.status -eq 'Disabled' }).Count
    }
} catch {
    $data['network.interfaces'] = [ordered]@{ error = [string]$_.Exception.Message }
}

# --- network.ip_configuration ----------------------------------------------
try {
    $configs = @(Get-NetIPConfiguration -ErrorAction Stop)

    $items = @()
    foreach ($config in $configs) {
        $addresses = @()
        foreach ($family in @('IPv4', 'IPv6')) {
            $collection = $null
            if ($family -eq 'IPv4') { $collection = $config.IPv4Address } else { $collection = $config.IPv6Address }
            if (-not $collection) { continue }
            foreach ($entry in @($collection)) {
                if (-not $entry) { continue }
                $addresses += [ordered]@{
                    family   = $family
                    address  = [string]$entry.IPAddress
                    prefix   = [int]$entry.PrefixLength
                    state    = [string]$entry.AddressState
                    type     = [string]$entry.Type
                }
            }
        }

        $gateways = @()
        foreach ($family in @('IPv4', 'IPv6')) {
            $collection = $null
            if ($family -eq 'IPv4') { $collection = $config.IPv4DefaultGateway } else { $collection = $config.IPv6DefaultGateway }
            if (-not $collection) { continue }
            foreach ($entry in @($collection)) {
                if (-not $entry) { continue }
                $gateways += [ordered]@{
                    family    = $family
                    next_hop  = [string]$entry.NextHop
                    interface = [string]$entry.InterfaceAlias
                }
            }
        }

        $dnsServers = @()
        try {
            foreach ($server in @($config.DNSServer.ServerAddresses)) {
                if ($server) { $dnsServers += [string]$server }
            }
        } catch { }

        $items += [ordered]@{
            interface       = [string]$config.InterfaceAlias
            interface_index = [int]$config.InterfaceIndex
            net_profile     = [string]$config.NetProfile.Name
            has_ipv4        = [bool]$config.IPv4Address
            addresses       = $addresses
            gateways        = $gateways
            dns_servers     = $dnsServers
        }
    }

    $data['network.ip_configuration'] = [ordered]@{
        count   = $items.Count
        configs = $items
    }
} catch {
    $data['network.ip_configuration'] = [ordered]@{ error = [string]$_.Exception.Message }
}

# --- network.routes ---------------------------------------------------------
try {
    $routes = @(Get-NetRoute -ErrorAction Stop |
        Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' -or $_.DestinationPrefix -eq '::/0' } |
        Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric, InterfaceMetric, State)

    $items = @()
    foreach ($route in $routes) {
        $items += [ordered]@{
            destination      = [string]$route.DestinationPrefix
            next_hop         = [string]$route.NextHop
            interface        = [string]$route.InterfaceAlias
            route_metric     = [int]$route.RouteMetric
            interface_metric = [int]$route.InterfaceMetric
            state            = [string]$route.State
        }
    }

    $data['network.routes'] = [ordered]@{
        count          = $items.Count
        default_routes = $items
    }
} catch {
    $data['network.routes'] = [ordered]@{ error = [string]$_.Exception.Message }
}

# --- network.profile --------------------------------------------------------
try {
    $profiles = @(Get-NetConnectionProfile -ErrorAction Stop | Select-Object InterfaceAlias,
        InterfaceIndex, Name, Category, DomainAuthenticationKind, IPv4Connectivity, IPv6Connectivity)

    $items = @()
    foreach ($profile in $profiles) {
        $items += [ordered]@{
            interface   = [string]$profile.InterfaceAlias
            name        = [string]$profile.Name
            category    = [string]$profile.Category
            domain_auth = [string]$profile.DomainAuthenticationKind
            ipv4_state  = [string]$profile.IPv4Connectivity
            ipv6_state  = [string]$profile.IPv6Connectivity
        }
    }

    $data['network.profile'] = [ordered]@{
        count    = $items.Count
        profiles = $items
    }
} catch {
    $data['network.profile'] = [ordered]@{ error = [string]$_.Exception.Message }
}

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 8 -Compress
