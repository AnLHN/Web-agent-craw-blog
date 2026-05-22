$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $RootDir ".env"
$LogDir = Join-Path $RootDir "logs"
$BackendPidFile = Join-Path $LogDir "backend.pid"
$FrontendPidFile = Join-Path $LogDir "frontend.pid"
$NineRouterPidFile = Join-Path $LogDir "9router.pid"

function Get-EnvMap {
    param([string]$Path)
    $map = @{}
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
            $idx = $line.IndexOf("=")
            $map[$line.Substring(0, $idx)] = $line.Substring($idx + 1)
        }
    }
    return $map
}

function Get-EnvValue {
    param([hashtable]$Map, [string]$Key, [string]$Default)
    if ($Map.ContainsKey($Key) -and $Map[$Key]) { return $Map[$Key] }
    return $Default
}

function Resolve-NpmCommand {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles "nodejs\npm.cmd"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\npm.cmd"),
        (Join-Path $env:APPDATA "npm\npm.cmd")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    $nvmRoots = @(
        (Join-Path $HOME ".nvm\versions\node"),
        (Join-Path $env:LOCALAPPDATA "nvm"),
        (Join-Path $env:APPDATA "nvm")
    )
    foreach ($root in $nvmRoots) {
        if (-not (Test-Path $root)) { continue }
        $candidate = Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $path = Join-Path $_.FullName "bin\npm.cmd"
                if (Test-Path $path) { $path }
            } |
            Select-Object -First 1
        if ($candidate) { return $candidate }
    }
    return $null
}

function Resolve-NineRouterCommand {
    $cmd = Get-Command 9router.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command 9router -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = Join-Path $env:APPDATA "npm\9router.cmd"
    if (Test-Path $candidate) { return $candidate }
    return $null
}

function Stop-ExistingPid {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return }
    $pidValue = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($pidValue) {
        try { Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue } catch {}
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-ByPort {
    param([string]$Port)
    $pids = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -ne 0 })
    foreach ($pidValue in $pids) {
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            Write-Host "[run] Stopped old process on port $Port pid=$pidValue"
        } catch {}
    }
}

$envMap = Get-EnvMap $EnvFile
$BackendHost = Get-EnvValue $envMap "BACKEND_HOST" "127.0.0.1"
$BackendPort = Get-EnvValue $envMap "BACKEND_PORT" "8011"
$FrontendHost = Get-EnvValue $envMap "FRONTEND_HOST" "0.0.0.0"
$FrontendPort = Get-EnvValue $envMap "FRONTEND_PORT" "3005"
$NineRouterAutoStart = Get-EnvValue $envMap "NINEROUTER_AUTO_START" "true"
$NineRouterStartMode = Get-EnvValue $envMap "NINEROUTER_START_MODE" "terminal"
$NineRouterDashboardUrl = Get-EnvValue $envMap "NINEROUTER_DASHBOARD_URL" "http://localhost:20128/dashboard"

$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Khong tim thay .venv. Hay chay .\setup.cmd truoc."
}

$NpmCmd = Resolve-NpmCommand
if (-not $NpmCmd) {
    throw "Khong tim thay npm tren Windows. Hay cai Node.js LTS, hoac chay bang Git Bash: ./run.sh"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Stop-ExistingPid $BackendPidFile
Stop-ExistingPid $FrontendPidFile
Stop-ByPort $BackendPort
Stop-ByPort $FrontendPort

if (@("1", "true", "yes", "y", "on") -contains $NineRouterAutoStart.ToLower()) {
    $nineRouterCmd = Resolve-NineRouterCommand
    if ($nineRouterCmd) {
        $shouldStartNineRouter = $true
        try {
            $uri = [Uri]$NineRouterDashboardUrl
            $listener = Get-NetTCPConnection -State Listen -LocalPort $uri.Port -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($listener) { $shouldStartNineRouter = $false }
        } catch {}
        if ($shouldStartNineRouter) {
            if ($NineRouterStartMode.ToLower() -eq "terminal") {
                $terminalCommand = "`$host.UI.RawUI.WindowTitle='web-agent-9router'; & '$($nineRouterCmd.Replace("'", "''"))'"
                $nine = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $terminalCommand) -WorkingDirectory $RootDir -PassThru
            } else {
                $nineOutLog = Join-Path $LogDir "9router.out.log"
                $nineErrLog = Join-Path $LogDir "9router.err.log"
                $nine = Start-Process -FilePath $nineRouterCmd -WorkingDirectory $RootDir -RedirectStandardOutput $nineOutLog -RedirectStandardError $nineErrLog -WindowStyle Hidden -PassThru
            }
            Set-Content -Path $NineRouterPidFile -Value $nine.Id -Encoding ascii
            Write-Host "[run] 9Router:  $NineRouterDashboardUrl pid=$($nine.Id)"
        } else {
            Write-Host "[run] 9Router:  $NineRouterDashboardUrl already running"
        }
    } else {
        Write-Host "[run][warn] Khong tim thay 9router. Hay chay .\setup.ps1 de cai."
    }
}

$backendArgs = "-m uvicorn src.main:app --host $BackendHost --port $BackendPort"
$backendOutLog = Join-Path $LogDir "backend.dev.out.log"
$backendErrLog = Join-Path $LogDir "backend.dev.err.log"
$backend = Start-Process -FilePath $PythonExe -ArgumentList $backendArgs -WorkingDirectory (Join-Path $RootDir "backend") -RedirectStandardOutput $backendOutLog -RedirectStandardError $backendErrLog -WindowStyle Hidden -PassThru
Set-Content -Path $BackendPidFile -Value $backend.Id -Encoding ascii

$frontendOutLog = Join-Path $LogDir "frontend.dev.out.log"
$frontendErrLog = Join-Path $LogDir "frontend.dev.err.log"
$frontendWorkdir = Join-Path $RootDir "frontend"
$npmDir = Split-Path -Parent $NpmCmd
$escapedNpm = $NpmCmd.Replace("'", "''")
$escapedNpmDir = $npmDir.Replace("'", "''")
$frontendCommand = "`$env:PATH='$escapedNpmDir;' + `$env:PATH; `$env:API_PROXY_HOST='$BackendHost'; `$env:API_PROXY_PORT='$BackendPort'; & '$escapedNpm' run dev -- --hostname $FrontendHost --port $FrontendPort"
$frontend = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) -WorkingDirectory $frontendWorkdir -RedirectStandardOutput $frontendOutLog -RedirectStandardError $frontendErrLog -WindowStyle Hidden -PassThru
Set-Content -Path $FrontendPidFile -Value $frontend.Id -Encoding ascii

Write-Host "[run] Backend:  http://$BackendHost`:$BackendPort"
Write-Host "[run] Frontend: http://localhost:$FrontendPort"
Write-Host "[run] 9Router:  $NineRouterDashboardUrl"
Write-Host "[run] npm:      $NpmCmd"
Write-Host "[run] Logs:     $LogDir"
