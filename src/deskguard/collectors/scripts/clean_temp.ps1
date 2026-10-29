<#
Limpeza de arquivos temporarios do sistema e do usuario (Somente leitura ou modificador).
Remove arquivos temporarios em %TEMP% e C:\Windows\Temp com seguranca.
#>

$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$cleanedFiles = 0
$cleanedBytes = 0

$tempDirs = @($env:TEMP, "$env:SystemRoot\Temp")
foreach ($dir in $tempDirs) {
    if (Test-Path $dir) {
        Get-ChildItem -Path $dir -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                if (-not $_.PSIsContainer) {
                    $size = $_.Length
                    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
                    $cleanedFiles++
                    if ($size) { $cleanedBytes += $size }
                }
            } catch {}
        }
    }
}

$data = [ordered]@{
    cleaned_files = $cleanedFiles
    cleaned_mb = [Math]::Round($cleanedBytes / 1MB, 2)
    status = 'success'
}

$result = [ordered]@{ ok = $true; data = @{ "maintenance.temp" = $data } }
$result | ConvertTo-Json -Depth 6 -Compress
