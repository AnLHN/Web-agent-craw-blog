param(
  [int]$Port = 9227,
  [string]$ProfileDir = "D:\NTC_AI\ChromeProfiles\web-agent-wp",
  [string]$Url = "about:blank",
  [string]$BrowserPath = ""
)

function Resolve-BrowserPath {
  param([string]$PreferredPath)
  if ($PreferredPath -and (Test-Path $PreferredPath)) {
    return $PreferredPath
  }

  $commands = @("chrome.exe", "brave.exe", "msedge.exe")
  foreach ($command in $commands) {
    $resolved = Get-Command $command -ErrorAction SilentlyContinue
    if ($resolved) {
      return $resolved.Source
    }
  }

  $candidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  throw "Khong tim thay Chrome/Brave/Edge. Truyen -BrowserPath `"C:\Path\browser.exe`" neu browser nam o vi tri khac."
}

$browser = Resolve-BrowserPath $BrowserPath
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
Write-Host "[wp-chrome] Browser: $browser"
Write-Host "[wp-chrome] CDP: http://127.0.0.1:$Port"
Write-Host "[wp-chrome] URL: $Url"
Start-Process $browser -ArgumentList @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$ProfileDir",
  "--new-window",
  $Url
)
