<#
Coleta do estado das impressoras e das filas de impressao via PowerShell.

IMPORTANTE: este arquivo e mantido em ASCII puro de proposito. O PowerShell
5.1 interpreta arquivos .ps1 sem BOM usando a codificacao ANSI do sistema e
reconhece aspas "inteligentes" (U+201C/U+201D) como delimitadores de string.
Um caractere nao-ASCII dentro de um docstring pode, portanto, encerrar a
string mais cedo e derrubar o parser.

Objetivo: responder as perguntas mais comuns de Service Desk sobre impressao:
"quais impressoras estao instaladas", "por que a impressora X nao imprime" e
"a impressora esta offline".

Escopo de dados coletados:
  * inventario de impressoras: nome, driver, porta, tipo (local ou de rede),
    compartilhada, local, comentarios, status do dispositivo e estado de erro;
  * fila de trabalhos de cada impressora: documento, usuario, hora de envio,
    situacao e tamanho;
  * estado do servico "Print Spooler".

Acoes explicitamente NAO executadas (todas alteram o sistema ou o
dispositivo):
  * Test-Printer - imprimiria uma pagina de teste;
  * Remove-PrintJob - removeria trabalhos da fila;
  * Restart-Service Spooler - reiniciaria o servico;
  * Suspend-PrintJob / Resume-PrintJob - alterariam a fila.

Dados NAO coletados: conteudo dos documentos impressos, caminhos de arquivos
impressos, credenciais de usuario e conteudo de trabalhos de impressao.
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$data = [ordered]@{}

# --- Parametros (recebidos por arquivo JSON, nunca pela linha de comando) ---
$includeJobs = $true
$payloadPath = $env:DESKGUARD_PAYLOAD_PATH
if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try {
        $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($payload.PSObject.Properties.Name -contains 'include_jobs') {
            $includeJobs = [bool]$payload.include_jobs
        }
    } catch { }
}

# --- printers.inventory -----------------------------------------------------
$inventoryAvailable = $false
$printers = @()
$inventoryError = ''

try {
    $cimPrinters = @(Get-CimInstance -ClassName Win32_Printer -ErrorAction Stop)

    foreach ($printer in $cimPrinters) {
        $port = ''
        $driver = ''
        $location = ''
        $comment = ''
        $shared = $false
        $shareName = ''
        try { $port = [string]$printer.PortName } catch { }
        try { $driver = [string]$printer.DriverName } catch { }
        try { $location = [string]$printer.Location } catch { }
        try { $comment = [string]$printer.Comment } catch { }
        try { $shared = [bool]$printer.Shared } catch { }
        try { $shareName = [string]$printer.ShareName } catch { }

        $isNetwork = $false
        try { $isNetwork = [bool]$printer.Network } catch { }
        $isLocal = $false
        try { $isLocal = [bool]$printer.Local } catch { }
        if (-not $isNetwork -and -not $isLocal) { $isLocal = $true }

        $printerStatus = 0
        try { $printerStatus = [int]$printer.PrinterStatus } catch { }
        $detectedError = 0
        try { $detectedError = [int]$printer.DetectedErrorState } catch { }
        $extendedStatus = 0
        try { $extendedStatus = [int]$printer.ExtendedPrinterStatus } catch { }
        $availability = 0
        try { $availability = [int]$printer.Availability } catch { }
        $workOffline = $false
        try { $workOffline = [bool]$printer.WorkOffline } catch { }
        $isDefault = $false
        try { $isDefault = [bool]$printer.Default } catch { }

        $printers += [ordered]@{
            name                 = [string]$printer.Name
            port                 = $port
            driver               = $driver
            location             = $location
            comment              = $comment
            shared               = $shared
            share_name           = $shareName
            is_network           = $isNetwork
            is_local             = $isLocal
            printer_status       = $printerStatus
            detected_error_state = $detectedError
            extended_status      = $extendedStatus
            availability         = $availability
            work_offline         = $workOffline
            is_default           = $isDefault
        }
    }
    $inventoryAvailable = $true
} catch {
    $inventoryError = [string]$_.Exception.Message
}

# Complemento com o modulo PrintManagement, quando disponivel.
$managementError = ''
try {
    $management = @(Get-Printer -ErrorAction Stop)
    $managementNames = @($management | ForEach-Object { [string]$_.Name })
    if ($managementNames.Count -gt 0 -and $printers.Count -eq 0) {
        foreach ($printer in $management) {
            $printers += [ordered]@{
                name                 = [string]$printer.Name
                port                 = [string]$printer.PortName
                driver               = [string]$printer.DriverName
                location             = [string]$printer.Location
                comment              = [string]$printer.Comment
                shared               = [bool]$printer.Shared
                share_name           = [string]$printer.ShareName
                is_network           = ($printer.Type -eq 3)
                is_local             = ($printer.Type -ne 3)
                printer_status       = 0
                detected_error_state = 0
                extended_status      = 0
                availability         = 0
                work_offline         = $false
                is_default           = [bool]$printer.Default
            }
        }
        $inventoryAvailable = $true
    }
} catch {
    $managementError = [string]$_.Exception.Message
}

$data['printers.inventory'] = [ordered]@{
    available    = $inventoryAvailable
    count        = $printers.Count
    printers     = $printers
    error        = $inventoryError
    module_error = $managementError
}

# --- printers.queue ---------------------------------------------------------
$queue = @()
$queueError = ''
if ($includeJobs) {
    try {
        foreach ($printer in $printers) {
            $name = [string]$printer.name
            if (-not $name) { continue }
            $jobs = @()
            try {
                $jobList = @(Get-PrintJob -PrinterName $name -ErrorAction Stop)
                foreach ($job in $jobList) {
                    $submitted = ''
                    try { $submitted = $job.SubmittedTime.ToString('o') } catch { }
                    $size = 0
                    try { $size = [int]$job.Size } catch { }
                    $pages = 0
                    try { $pages = [int]$job.PagesPrinted } catch { }
                    $jobs += [ordered]@{
                        id              = [int]$job.ID
                        document        = [string]$job.DocumentName
                        user            = [string]$job.UserName
                        submitted       = $submitted
                        job_status      = [int]$job.JobStatus
                        job_status_text = [string]$job.JobStatus
                        size_bytes      = $size
                        pages_printed   = $pages
                    }
                }
            } catch {
                # Sem permissao para a fila: a impressora continua sendo reportada.
            }
            $queue += [ordered]@{
                printer = $name
                count   = $jobs.Count
                jobs    = $jobs
            }
        }
    } catch {
        $queueError = [string]$_.Exception.Message
    }
}

$data['printers.queue'] = [ordered]@{
    included = $includeJobs
    count    = $queue.Count
    queues   = $queue
    error    = $queueError
}

# --- printers.spooler -------------------------------------------------------
try {
    $spooler = Get-Service -Name 'Spooler' -ErrorAction Stop
    $data['printers.spooler'] = [ordered]@{
        name       = [string]$spooler.Name
        status     = [string]$spooler.Status
        start_type = [string]$spooler.StartType
        available  = $true
    }
} catch {
    $data['printers.spooler'] = [ordered]@{
        name       = 'Spooler'
        status     = ''
        start_type = ''
        available  = $false
        error      = [string]$_.Exception.Message
    }
}

$result = [ordered]@{ ok = $true; data = $data }
$result | ConvertTo-Json -Depth 8 -Compress
