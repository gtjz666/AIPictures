$ErrorActionPreference = 'Stop'
$comfyRoot = 'D:\Local Comfy\ComfyUI'
$pythonExe = Join-Path $comfyRoot '.venv\Scripts\python.exe'
$modelConfig = Join-Path $env:APPDATA 'ComfyUI\extra_models_config.yaml'
$logRoot = Join-Path $PSScriptRoot 'data\logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$launchMutex = [System.Threading.Mutex]::new($false, 'Local\AIPictures-Comfy-Start')
if (-not $launchMutex.WaitOne(20000)) { throw 'Another local engine launch is still in progress.' }
try {
# Reuse the Desktop-owned Python server, including a port chosen after a conflict.
$processRows = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$|^Comfy( Desktop|UI)?\.exe$' })
$processMap = @{}; foreach ($row in $processRows) { $processMap[[int]$row.ProcessId] = $row }
$candidatePorts = [System.Collections.Generic.List[int]]::new()
foreach ($row in $processRows) {
    if ($row.CommandLine -notmatch '(?:^|[\\/\s"])main\.py(?:"|\s|$)') { continue }
    $ancestor = $row
    for ($depth=0; $depth -lt 5; $depth++) {
        $ancestor = $processMap[[int]$ancestor.ParentProcessId]
        if (-not $ancestor) { break }
        if ($ancestor.Name -match '^Comfy( Desktop|UI)?\.exe$') {
            $enginePort = 8188
            if ($row.CommandLine -match '--port(?:\s+|=)(\d+)') { $enginePort=[int]$Matches[1] }
            if ($enginePort -gt 0 -and $enginePort -lt 65536 -and -not $candidatePorts.Contains($enginePort)) { $candidatePorts.Add($enginePort) }
            break
        }
    }
}
foreach ($enginePort in $candidatePorts) {
    try {
        $engineUrl = 'http://127.0.0.1:' + $enginePort
        $stats = Invoke-RestMethod ($engineUrl+'/system_stats') -TimeoutSec 2
        if ($stats.system -and $null -ne $stats.devices) {
            Write-Host ('Reusing the open ComfyUI at '+$engineUrl+'. Use this same address in AIPictures.')
            exit 0
        }
    } catch {}
}
try {
    Invoke-RestMethod 'http://127.0.0.1:8188/system_stats' -TimeoutSec 3 | Out-Null
    Write-Host 'ComfyUI is already running at http://127.0.0.1:8188'
    exit 0
} catch {}
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'ComfyUI Python not found. Edit comfyRoot in this file.' }
$logStamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
foreach ($logName in @('comfy-output.log', 'comfy-error.log')) {
    $existingLog = Join-Path $logRoot $logName
    if (Test-Path -LiteralPath $existingLog) {
        Copy-Item -LiteralPath $existingLog -Destination (Join-Path $logRoot ($logStamp + '-' + $logName))
    }
}
# Drop disposable node caches under RAM pressure; does not change model precision or sampling.
$launchArgs = @('main.py', '--listen', '127.0.0.1', '--port', '8188', '--cache-ram', '4')
if (Test-Path -LiteralPath $modelConfig) { $launchArgs += @('--extra-model-paths-config', ('"' + $modelConfig + '"')) }
Start-Process -FilePath $pythonExe -ArgumentList $launchArgs -WorkingDirectory $comfyRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'comfy-output.log') -RedirectStandardError (Join-Path $logRoot 'comfy-error.log')
Write-Host 'ComfyUI is starting. Initial model imports may take several minutes. Open run.bat and click Connect when ready.'
} finally {
    $launchMutex.ReleaseMutex(); $launchMutex.Dispose()
}
