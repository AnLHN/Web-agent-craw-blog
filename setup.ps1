$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootEnv = Join-Path $RootDir ".env"
$RootEnvExample = Join-Path $RootDir ".env.example"
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$BackendEnv = Join-Path $BackendDir ".env"
$BackendEnvExample = Join-Path $BackendDir ".env.example"
$FrontendEnv = Join-Path $FrontendDir ".env.local"
$LogDir = Join-Path $RootDir "logs"
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

function Set-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @()
    if (Test-Path $Path) { $lines = @(Get-Content $Path) }
    $updated = $false
    $lines = $lines | ForEach-Object {
        if ($_ -match "^$([regex]::Escape($Key))=") {
            $updated = $true
            "$Key=$Value"
        } else {
            $_
        }
    }
    if (-not $updated) { $lines += "$Key=$Value" }
    Set-Content -Path $Path -Value $lines -Encoding utf8
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

function Ensure-FileFromExample {
    param([string]$Path, [string]$Example)
    if (-not (Test-Path $Path)) {
        Copy-Item $Example $Path
        Write-Host "[setup] Tao $Path"
    }
}

function Ensure-DockerContainer {
    param(
        [string]$Name,
        [string]$Image,
        [string[]]$RunArgs
    )
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "[setup][warn] Khong tim thay docker, bo qua $Name"
        return
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[setup][warn] Docker daemon chua chay, bo qua $Name"
        return
    }
    docker container inspect $Name *> $null
    if ($LASTEXITCODE -eq 0) {
        $running = docker inspect -f "{{.State.Running}}" $Name 2>$null
        if ($running -eq "true") {
            Write-Host "[setup] Container dang chay: $Name"
            return
        }
        docker start $Name | Out-Null
        Write-Host "[setup] Da start lai container: $Name"
        return
    }
    docker run --name $Name @RunArgs -d $Image | Out-Null
    Write-Host "[setup] Da tao container: $Name"
}

function Test-IsTrue {
    param([string]$Value)
    return @("1", "true", "yes", "y", "on") -contains $Value.ToLower()
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

function Ensure-NineRouter {
    param([string]$NpmCmd)
    if (Resolve-NineRouterCommand) {
        Write-Host "[setup] 9Router da duoc cai"
        return
    }

    $npmGlobalDir = Join-Path $env:APPDATA "npm"
    New-Item -ItemType Directory -Force -Path $npmGlobalDir | Out-Null
    Write-Host "[setup] Dang cai 9Router global"
    & $NpmCmd install -g 9router
    if ($LASTEXITCODE -ne 0) {
        throw "Cai 9Router that bai. Thu chay thu cong: npm install -g 9router"
    }
}

function Start-WpChromeIfEnabled {
    param([string]$Port, [string]$Url)
    $script = Join-Path $RootDir "scripts\start_wp_chrome.ps1"
    if (-not (Test-Path $script)) {
        Write-Host "[setup][warn] Khong tim thay $script, bo qua start WordPress browser"
        return
    }

    try {
        $listener = Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            Write-Host "[setup] WordPress browser CDP dang chay tai http://127.0.0.1:$Port"
            return
        }
    } catch {}

    Write-Host "[setup] Dang mo WordPress browser CDP port $Port"
    & $script -Port ([int]$Port) -Url $Url
}

function Start-NineRouterIfEnabled {
    param([string]$NineRouterDashboardUrl, [string]$StartMode)
    $nineRouterCmd = Resolve-NineRouterCommand
    if (-not $nineRouterCmd) {
        Write-Host "[setup][warn] Chua tim thay 9router command, bo qua auto-start"
        return
    }

    try {
        $uri = [Uri]$NineRouterDashboardUrl
        $port = $uri.Port
        if ($port -gt 0) {
            $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($listener) {
                Write-Host "[setup] 9Router dang chay tai $NineRouterDashboardUrl"
                return
            }
        }
    } catch {}

    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    if ($StartMode.ToLower() -eq "terminal") {
        $terminalCommand = "`$host.UI.RawUI.WindowTitle='web-agent-9router'; & '$($nineRouterCmd.Replace("'", "''"))'"
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $terminalCommand) -WorkingDirectory $RootDir -PassThru
        Set-Content -Path $NineRouterPidFile -Value $proc.Id -Encoding ascii
        Write-Host "[setup] Da mo terminal 9Router pid=$($proc.Id) dashboard=$NineRouterDashboardUrl"
        return
    }

    $outLog = Join-Path $LogDir "9router.out.log"
    $errLog = Join-Path $LogDir "9router.err.log"
    $proc = Start-Process -FilePath $nineRouterCmd -WorkingDirectory $RootDir -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Set-Content -Path $NineRouterPidFile -Value $proc.Id -Encoding ascii
    Write-Host "[setup] Da start 9Router pid=$($proc.Id) dashboard=$NineRouterDashboardUrl"
}

Ensure-FileFromExample $RootEnv $RootEnvExample
Ensure-FileFromExample $BackendEnv $BackendEnvExample

$envMap = Get-EnvMap $RootEnv
$BackendHost = Get-EnvValue $envMap "BACKEND_HOST" "127.0.0.1"
$BackendPort = Get-EnvValue $envMap "BACKEND_PORT" "8011"
$FrontendPort = Get-EnvValue $envMap "FRONTEND_PORT" "3005"
$FeatureSession = Get-EnvValue $envMap "FEATURE_SESSION_HISTORY" "true"
$FeatureOps = Get-EnvValue $envMap "FEATURE_OPS_DASHBOARD" "true"
$FeatureLlmConfig = Get-EnvValue $envMap "FEATURE_LLM_RUNTIME_CONFIG" "true"
$OpsRole = Get-EnvValue $envMap "OPS_ROLE" "admin"
$OpsToken = Get-EnvValue $envMap "OPS_ADMIN_TOKEN" ""
$LlmBaseUrl = Get-EnvValue $envMap "LLM_BASE_URL" "http://localhost:8007/v1"
$LlmModel = Get-EnvValue $envMap "LLM_MODEL" "google/gemma-4-E4B-it"
$NineRouterInstall = Get-EnvValue $envMap "NINEROUTER_INSTALL" "true"
$NineRouterAutoStart = Get-EnvValue $envMap "NINEROUTER_AUTO_START" "true"
$NineRouterStartMode = Get-EnvValue $envMap "NINEROUTER_START_MODE" "terminal"
$NineRouterBaseUrl = Get-EnvValue $envMap "NINEROUTER_BASE_URL" "http://127.0.0.1:20128/v1"
$NineRouterDashboardUrl = Get-EnvValue $envMap "NINEROUTER_DASHBOARD_URL" "http://localhost:20128/dashboard"
$WpChromeAutoStart = Get-EnvValue $envMap "WP_CHROME_AUTO_START" "true"
$WpChromePort = Get-EnvValue $envMap "WP_CHROME_PORT" "9227"
$WpChromeUrl = Get-EnvValue $envMap "WP_CHROME_URL" "about:blank"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Khong tim thay python trong PATH."
}

$NpmCmd = Resolve-NpmCommand
if (-not $NpmCmd) {
    throw "Khong tim thay npm tren Windows. Hay cai Node.js LTS, hoac chay bang Git Bash: ./setup.sh"
}

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    python -m venv (Join-Path $RootDir ".venv")
    Write-Host "[setup] Da tao .venv"
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e "${BackendDir}[dev]"

Push-Location $FrontendDir
& $NpmCmd install
Pop-Location

if (Test-IsTrue $NineRouterInstall) {
    Ensure-NineRouter $NpmCmd
} else {
    Write-Host "[setup] NINEROUTER_INSTALL=false, bo qua cai 9Router"
}

New-Item -ItemType Directory -Force -Path (Join-Path $BackendDir "config") | Out-Null
if (-not (Test-Path (Join-Path $BackendDir "config\tavily_keys.json"))) { Set-Content -Path (Join-Path $BackendDir "config\tavily_keys.json") -Value "[]" -Encoding utf8 }
if (-not (Test-Path (Join-Path $BackendDir "config\chat_sessions.json"))) { Set-Content -Path (Join-Path $BackendDir "config\chat_sessions.json") -Value "[]" -Encoding utf8 }
if (-not (Test-Path (Join-Path $BackendDir "config\audit_logs.jsonl"))) { New-Item -ItemType File -Path (Join-Path $BackendDir "config\audit_logs.jsonl") | Out-Null }

$cors = "[`"http://localhost:$FrontendPort`",`"http://127.0.0.1:$FrontendPort`"]"
Set-EnvValue $BackendEnv "APP_CORS_ORIGINS" $cors
Set-EnvValue $BackendEnv "APP_LLM_BASE_URL" $LlmBaseUrl
Set-EnvValue $BackendEnv "APP_LLM_MODEL" $LlmModel
Set-EnvValue $BackendEnv "APP_FEATURE_SESSION_HISTORY" $FeatureSession
Set-EnvValue $BackendEnv "APP_FEATURE_OPS_DASHBOARD" $FeatureOps
Set-EnvValue $BackendEnv "APP_FEATURE_LLM_RUNTIME_CONFIG" $FeatureLlmConfig
Set-EnvValue $BackendEnv "APP_ARTICLE_LLM_PROVIDER" "9router_openai"
Set-EnvValue $BackendEnv "APP_9ROUTER_BASE_URL" $NineRouterBaseUrl
Set-EnvValue $BackendEnv "APP_ARTICLE_OPENAI_MODEL" "cx/gpt-5.5"

Set-EnvValue $FrontendEnv "NEXT_PUBLIC_API_BASE" "http://127.0.0.1:$BackendPort/api/v1"
Set-EnvValue $FrontendEnv "NEXT_PUBLIC_FEATURE_SESSION_HISTORY" $FeatureSession
Set-EnvValue $FrontendEnv "NEXT_PUBLIC_FEATURE_OPS_DASHBOARD" $FeatureOps
Set-EnvValue $FrontendEnv "NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG" $FeatureLlmConfig
Set-EnvValue $FrontendEnv "NEXT_PUBLIC_OPS_ROLE" $OpsRole
Set-EnvValue $FrontendEnv "NEXT_PUBLIC_OPS_ADMIN_TOKEN" $OpsToken
Set-EnvValue $FrontendEnv "NEXT_PUBLIC_9ROUTER_DASHBOARD_URL" $NineRouterDashboardUrl

if ((Get-EnvValue $envMap "POSTGRES_AUTO_START" "false").ToLower() -eq "true") {
    $pgName = Get-EnvValue $envMap "POSTGRES_CONTAINER_NAME" "websearch-pg"
    $pgImage = Get-EnvValue $envMap "POSTGRES_IMAGE" "postgres:16"
    $pgPort = Get-EnvValue $envMap "POSTGRES_PORT" "5432"
    $pgDb = Get-EnvValue $envMap "POSTGRES_DB" "web_search"
    $pgUser = Get-EnvValue $envMap "POSTGRES_USER" "postgres"
    $pgPassword = Get-EnvValue $envMap "POSTGRES_PASSWORD" "postgres"
    Ensure-DockerContainer $pgName $pgImage @("-e", "POSTGRES_PASSWORD=$pgPassword", "-e", "POSTGRES_USER=$pgUser", "-e", "POSTGRES_DB=$pgDb", "-p", "$pgPort`:5432")
}

if ((Get-EnvValue $envMap "PGADMIN_AUTO_START" "false").ToLower() -eq "true") {
    $pgAdminName = Get-EnvValue $envMap "PGADMIN_CONTAINER_NAME" "websearch-pgadmin"
    $pgAdminImage = Get-EnvValue $envMap "PGADMIN_IMAGE" "dpage/pgadmin4:8"
    $pgAdminPort = Get-EnvValue $envMap "PGADMIN_PORT" "5050"
    $pgAdminEmail = Get-EnvValue $envMap "PGADMIN_DEFAULT_EMAIL" "admin@local.dev"
    $pgAdminPassword = Get-EnvValue $envMap "PGADMIN_DEFAULT_PASSWORD" "admin"
    Ensure-DockerContainer $pgAdminName $pgAdminImage @("-e", "PGADMIN_DEFAULT_EMAIL=$pgAdminEmail", "-e", "PGADMIN_DEFAULT_PASSWORD=$pgAdminPassword", "-e", "PGADMIN_CONFIG_ENHANCED_COOKIE_PROTECTION=False", "-p", "$pgAdminPort`:80")
}

if ((Get-EnvValue $envMap "SEARXNG_AUTO_START" "false").ToLower() -eq "true") {
    $searxName = Get-EnvValue $envMap "SEARXNG_CONTAINER_NAME" "websearch-searxng"
    $searxImage = Get-EnvValue $envMap "SEARXNG_IMAGE" "searxng/searxng:latest"
    $searxPort = Get-EnvValue $envMap "SEARXNG_PORT" "8080"
    $searxConfig = Join-Path $RootDir "config\searxng"
    New-Item -ItemType Directory -Force -Path $searxConfig | Out-Null
    Ensure-DockerContainer $searxName $searxImage @("-e", "BASE_URL=http://127.0.0.1:$searxPort/", "-e", "INSTANCE_NAME=web-agent-searxng", "-v", "$searxConfig`:/etc/searxng:ro", "-p", "$searxPort`:8080")
}

if (Test-IsTrue $NineRouterAutoStart) {
    Start-NineRouterIfEnabled $NineRouterDashboardUrl $NineRouterStartMode
} else {
    Write-Host "[setup] NINEROUTER_AUTO_START=false, bo qua start 9Router"
}

if (Test-IsTrue $WpChromeAutoStart) {
    Start-WpChromeIfEnabled $WpChromePort $WpChromeUrl
} else {
    Write-Host "[setup] WP_CHROME_AUTO_START=false, bo qua start WordPress browser"
}

Write-Host ""
Write-Host "Chay backend:"
Write-Host "  cd backend"
Write-Host "  $VenvPython -m uvicorn src.main:app --host $BackendHost --port $BackendPort"
Write-Host ""
Write-Host "Chay frontend:"
Write-Host "  cd frontend"
Write-Host "  npm run dev -- --hostname 0.0.0.0 --port $FrontendPort"
Write-Host ""
Write-Host "Chay 9Router:"
Write-Host "  9router"
Write-Host "  Dashboard: $NineRouterDashboardUrl"

if ((Get-EnvValue $envMap "AUTO_START_APPS" "true").ToLower() -eq "true") {
    & (Join-Path $RootDir "run.ps1")
} else {
    Write-Host "[setup] Done. Chay .\run.ps1 de start app."
}
