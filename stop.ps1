$ErrorActionPreference = "SilentlyContinue"

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

function Stop-ByPidFile {
    param([string]$Label, [string]$PidFile)
    if (-not (Test-Path $PidFile)) {
        Write-Host "[stop] Khong co pid file cho $Label"
        return
    }
    $pidValue = Get-Content $PidFile
    if ($pidValue) {
        Stop-Process -Id ([int]$pidValue) -Force
        Write-Host "[stop] Da dung $Label pid=$pidValue"
    }
    Remove-Item $PidFile -Force
}

function Stop-ByPort {
    param([string]$Port)
    $pids = @(Get-NetTCPConnection -State Listen -LocalPort $Port | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -and $_ -ne 0 })
    foreach ($pidValue in $pids) {
        Stop-Process -Id $pidValue -Force
        Write-Host "[stop] Da dung process tren port $Port pid=$pidValue"
    }
}

$envMap = Get-EnvMap $EnvFile
$BackendPort = Get-EnvValue $envMap "BACKEND_PORT" "8011"
$FrontendPort = Get-EnvValue $envMap "FRONTEND_PORT" "3005"
$NineRouterDashboardUrl = Get-EnvValue $envMap "NINEROUTER_DASHBOARD_URL" "http://localhost:20128/dashboard"

Stop-ByPidFile "backend" $BackendPidFile
Stop-ByPidFile "frontend" $FrontendPidFile
Stop-ByPidFile "9router" $NineRouterPidFile
Stop-ByPort $BackendPort
Stop-ByPort $FrontendPort
try {
    $nineRouterPort = ([Uri]$NineRouterDashboardUrl).Port
    if ($nineRouterPort -gt 0) { Stop-ByPort $nineRouterPort }
} catch {}

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine.Contains($RootDir) -and
        ($_.Name -match "python|node|npm|powershell")
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }

Write-Host "[stop] Done"
