param(
    [switch]$KeepImages
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $RootDir ".env"

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

function Remove-DockerContainerIfExists {
    param([string]$Name)
    if (-not $Name) { return }
    docker container inspect $Name *> $null
    if ($LASTEXITCODE -eq 0) {
        docker rm -f -v $Name | Out-Null
        Write-Host "[delete] Removed container: $Name"
    } else {
        Write-Host "[delete] Container not found: $Name"
    }
}

function Remove-DockerImageIfExists {
    param([string]$Image)
    if (-not $Image) { return }
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -eq 0) {
        docker rmi -f $Image | Out-Null
        Write-Host "[delete] Removed image: $Image"
    } else {
        Write-Host "[delete] Image not found: $Image"
    }
}

$stopScript = Join-Path $RootDir "stop.ps1"
if (Test-Path $stopScript) {
    & $stopScript
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[delete][warn] Docker is not available. Skipping container/image cleanup."
    exit 0
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[delete][warn] Docker daemon is not running. Skipping container/image cleanup."
    exit 0
}

$envMap = Get-EnvMap $EnvFile

$postgresContainer = Get-EnvValue $envMap "POSTGRES_CONTAINER_NAME" "websearch-pg"
$pgadminContainer = Get-EnvValue $envMap "PGADMIN_CONTAINER_NAME" "websearch-pgadmin"
$searxngContainer = Get-EnvValue $envMap "SEARXNG_CONTAINER_NAME" "websearch-searxng"

$postgresImage = Get-EnvValue $envMap "POSTGRES_IMAGE" "postgres:16"
$pgadminImage = Get-EnvValue $envMap "PGADMIN_IMAGE" "dpage/pgadmin4:8"
$searxngImage = Get-EnvValue $envMap "SEARXNG_IMAGE" "searxng/searxng:latest"

Remove-DockerContainerIfExists $postgresContainer
Remove-DockerContainerIfExists $pgadminContainer
Remove-DockerContainerIfExists $searxngContainer

if ($KeepImages) {
    Write-Host "[delete] Kept Docker images because -KeepImages was provided."
} else {
    Remove-DockerImageIfExists $postgresImage
    Remove-DockerImageIfExists $pgadminImage
    Remove-DockerImageIfExists $searxngImage
}

Write-Host "[delete] Done"
