# Bolo Dukaan: put the app live on the internet from this PC, free, no card.
# Uses an ngrok free account (sign in with Google) and its free permanent address, e.g. https://yourname.ngrok-free.dev
#
#   go-live.bat            start (first time: asks for your ngrok token and address)
#   go-live.bat -Stop      stop the live link and the server this script started
#   go-live.bat -NoAutoStart   remove the "start when I log in" shortcut
#
# The site is live while this PC is on and awake. Data stays in data\ on this PC.
param([int]$Port = 8001, [switch]$Stop, [switch]$Quiet, [switch]$NoAutoStart)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$data = Join-Path $PSScriptRoot "data"
New-Item -ItemType Directory -Force -Path $data | Out-Null
$pidFile = Join-Path $data "live.pid"
$startup = Join-Path ([Environment]::GetFolderPath("Startup")) "Bolo Dukaan Live.cmd"

function Say($t, $c = "Gray") { if (-not $Quiet) { Write-Host "  $t" -ForegroundColor $c } }
function Pause-Exit($code) { if (-not $Quiet) { Read-Host "  Press Enter to close" | Out-Null }; exit $code }
function Test-Url($u, $headers = @{}) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $u -Headers $headers -TimeoutSec 8; return $r.StatusCode -eq 200 } catch { return $false }
}
function Read-EnvValue($key) {
    $f = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $f)) { return "" }
    foreach ($line in [IO.File]::ReadAllLines($f)) { if ($line -match "^\s*$key\s*=\s*(.*)$") { return $Matches[1].Trim() } }
    return ""
}
function Set-EnvValue($key, $value) {
    $f = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $f)) { Copy-Item (Join-Path $PSScriptRoot ".env.example") $f }
    $lines = [Collections.Generic.List[string]]([IO.File]::ReadAllLines($f))
    $done = $false
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^\s*$key\s*=") { $lines[$i] = "$key=$value"; $done = $true } }
    if (-not $done) { $lines.Add("$key=$value") }
    [IO.File]::WriteAllLines($f, $lines, (New-Object Text.UTF8Encoding($false)))
}

# ------------------------------------------------------------------ stop
if ($Stop) {
    Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force
    if (Test-Path $pidFile) {
        $p = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($p) { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue }
        Remove-Item $pidFile -Force
    }
    Write-Host "  Stopped the live link." -ForegroundColor Yellow
    exit 0
}
if ($NoAutoStart) {
    if (Test-Path $startup) { Remove-Item $startup -Force }
    Write-Host "  It will no longer start when you log in." -ForegroundColor Yellow
    exit 0
}

Say ""
Say "Bolo Dukaan - go live" "Yellow"
Say ""

# ------------------------------------------------------------------ 1. ngrok installed?
$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    if ($Quiet) { exit 1 }
    Say "ngrok is not installed. It makes the free public https address." "Cyan"
    $ans = Read-Host "  Install it now with winget (Microsoft's installer)? [Y/n]"
    if ($ans -and $ans -notmatch '^[Yy]') { Say "Install it later with:  winget install ngrok.ngrok"; Pause-Exit 1 }
    winget install --id ngrok.ngrok -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
    if (-not $ngrok) { Say "ngrok still not found. Close this window, open a new one and run go-live.bat again." "Red"; Pause-Exit 1 }
}

# ------------------------------------------------------------------ 2. ngrok account token (once)
$cfgOk = $false
try { $out = & $ngrok.Source config check 2>&1 | Out-String; $cfgOk = ($LASTEXITCODE -eq 0) } catch { $cfgOk = $false }
$hasToken = $false
foreach ($cfgFile in @((Join-Path $env:LOCALAPPDATA "ngrok\ngrok.yml"), (Join-Path $env:APPDATA "ngrok\ngrok.yml"), (Join-Path $env:USERPROFILE ".config\ngrok\ngrok.yml"))) {
    if ((Test-Path $cfgFile) -and ((Get-Content $cfgFile -Raw) -match "authtoken")) { $hasToken = $true }
}
if (-not ($cfgOk -and $hasToken)) {
    if ($Quiet) { exit 1 }
    Say "One-time setup (free, no card):" "Cyan"
    Say "  1. Open https://dashboard.ngrok.com/signup and sign in with Google."
    Say "  2. Open https://dashboard.ngrok.com/get-started/your-authtoken and copy your token."
    $tok = Read-Host "  Paste your ngrok authtoken"
    $tok = $tok.Trim()
    if (-not $tok) { Say "No token given." "Red"; Pause-Exit 1 }
    & $ngrok.Source config add-authtoken $tok | Out-Null
    if ($LASTEXITCODE -ne 0) { Say "ngrok did not accept that token." "Red"; Pause-Exit 1 }
    Say "Token saved in ngrok's own settings (not in this project)." "Green"
}

# ------------------------------------------------------------------ 3. permanent address
$pub = Read-EnvValue "PUBLIC_URL"
$domain = ""
if ($pub -match '^https://([^/]+\.ngrok[^/]*)') { $domain = $Matches[1] }
if (-not $domain) {
    if ($Quiet) { exit 1 }
    Say ""
    Say "Your free permanent address: open https://dashboard.ngrok.com/domains" "Cyan"
    Say "(ngrok gives every free account one, like  yourname.ngrok-free.dev  - create it if the page is empty)"
    $domain = (Read-Host "  Paste the address").Trim().ToLower() -replace '^https?://', '' -replace '/.*$', ''
    if ($domain -notmatch '^[a-z0-9-]+(\.[a-z0-9-]+)+$') { Say "That doesn't look like an address: $domain" "Red"; Pause-Exit 1 }
    Set-EnvValue "PUBLIC_URL" "https://$domain"
    Say "Saved PUBLIC_URL=https://$domain in .env (QR codes and payment links use it)." "Green"
}
$liveUrl = "https://$domain"

# ------------------------------------------------------------------ 4. the app
$local = "http://127.0.0.1:$Port/api/health"
if (-not (Test-Url $local)) {
    $venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Say "First run: preparing Python (one time)..."
        & powershell -NoProfile -ExecutionPolicy Bypass -Command "& { Set-Location -LiteralPath '$PSScriptRoot'; `$py = (Get-Command py -ErrorAction SilentlyContinue); if (`$py) { py -3 -m venv .venv } else { python -m venv .venv }; .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt }"
        if (-not (Test-Path $venvPy)) { Say "Could not prepare Python. Run start.bat once, then go-live.bat." "Red"; Pause-Exit 1 }
    }
    $p = Start-Process -FilePath $venvPy -ArgumentList @("run.py", "--port", "$Port", "--no-browser") -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $data "live.log") -RedirectStandardError (Join-Path $data "live-errors.log")
    Set-Content -Path $pidFile -Value $p.Id
    for ($i = 0; $i -lt 30 -and -not (Test-Url $local); $i++) { Start-Sleep -Milliseconds 700 }
    if (-not (Test-Url $local)) { Say "The app didn't start. See data\live-errors.log" "Red"; Pause-Exit 1 }
    Say "App running on this PC (port $Port)." "Green"
} else {
    Say "App already running on port $Port." "Green"
}

# ------------------------------------------------------------------ 5. the public link
$tunnelUp = $false
try {
    $t = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3
    foreach ($x in $t.tunnels) { if ($x.public_url -eq $liveUrl) { $tunnelUp = $true } }
} catch { }
if (-not $tunnelUp) {
    Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force
    $ver = (& $ngrok.Source version) -replace '[^0-9.]', ''
    $parts = $ver.Split('.')
    $flag = "--url=$liveUrl"
    if ($parts.Count -ge 2 -and [int]$parts[0] -eq 3 -and [int]$parts[1] -lt 16) { $flag = "--domain=$domain" }
    Start-Process -FilePath $ngrok.Source -ArgumentList @("http", $flag, "$Port", "--log=stdout") -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $data "ngrok.log") -RedirectStandardError (Join-Path $data "ngrok-errors.log") | Out-Null
}
$hdr = @{ "ngrok-skip-browser-warning" = "1" }
for ($i = 0; $i -lt 25 -and -not (Test-Url "$liveUrl/api/health" $hdr); $i++) { Start-Sleep -Seconds 1 }
if (-not (Test-Url "$liveUrl/api/health" $hdr)) {
    Say "The public link didn't come up. Last ngrok lines:" "Red"
    if (Test-Path (Join-Path $data "ngrok.log")) { Get-Content (Join-Path $data "ngrok.log") -Tail 8 | ForEach-Object { Say $_ } }
    Pause-Exit 1
}

# ------------------------------------------------------------------ 6. start when I log in
if (-not (Test-Path $startup) -and -not $Quiet) {
    $ans = Read-Host "  Start the live site automatically every time you log in to Windows? [Y/n]"
    if (-not $ans -or $ans -match '^[Yy]') {
        $cmd = "@echo off`r`nstart """" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$PSScriptRoot\go-live.ps1"" -Quiet -Port $Port`r`n"
        [IO.File]::WriteAllText($startup, $cmd, (New-Object Text.ASCIIEncoding))
        Say "Done: it will start by itself after every login (undo: go-live.bat -NoAutoStart)." "Green"
    }
}

Say ""
Say "LIVE:  $liveUrl" "Green"
Say "Owner login     : $liveUrl/owner/login"
Say "Print QR codes  : $liveUrl/owner/qr   (codes now open the live site on any phone)"
Say "Waiter / kitchen: Dashboard -> Staff / Kitchen display"
Say ""
Say "Keep this PC on and awake (Settings -> System -> Power -> Sleep: Never while plugged in)." "DarkYellow"
Say "Stop: go-live.bat -Stop"
if (-not $Quiet) { Start-Process $liveUrl; Read-Host "  Press Enter to close this window (the site keeps running)" | Out-Null }
