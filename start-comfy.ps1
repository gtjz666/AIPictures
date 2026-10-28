$ErrorActionPreference = 'Stop'
$comfyRoot = 'D:\Local Comfy\ComfyUI'
$pythonExe = Join-Path $comfyRoot '.venv\Scripts\python.exe'
$modelConfig = Join-Path $env:APPDATA 'ComfyUI\extra_models_config.yaml'
$logRoot = Join-Path $PSScriptRoot 'data\logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
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
