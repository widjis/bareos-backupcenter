param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$node = (Get-Command node -ErrorAction Stop).Source
$next = Join-Path $projectRoot 'node_modules\next\dist\bin\next'
if (-not (Test-Path $python) -or -not (Test-Path $next)) {
    throw 'Install backend and frontend dependencies first. See docs/LOCAL-DEVELOPMENT.md.'
}
$logDirectory = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:PATH = (Split-Path $node) + ';' + $env:PATH
function Test-LocalPort([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try { $task = $client.ConnectAsync('127.0.0.1', $Port); return ($task.Wait(500) -and $client.Connected) }
    catch { return $false }
    finally { $client.Dispose() }
}
function Start-LocalService($Name, $Executable, $Arguments, [int]$Port) {
    if (Test-LocalPort $Port) {
        Write-Host "$Name port $Port is already in use; no duplicate process started."
        return
    }
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory "$Name.log") -RedirectStandardError (Join-Path $logDirectory "$Name.err.log") -PassThru
    Set-Content -LiteralPath (Join-Path $logDirectory "$Name.pid") -Value $process.Id
    Write-Host "$Name started (PID $($process.Id)); logs are in .local/."
}
Start-LocalService 'backend' $python @('-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8001') 8001
Start-LocalService 'frontend' $node @('node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1','--port','3000') 3000
Write-Host 'Open http://127.0.0.1:3000. This launcher does not change operation-dispatch flags.'