# Bolo Dukaan: one-click start for Windows.
# Creates a private Python environment the first time, installs the one small package, then runs the server.
param([int]$Port = 8000, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    foreach ($cmd in @(@("py", "-3"), @("python"), @("python3"))) {
        $exe = Get-Command $cmd[0] -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        $extra = @($cmd | Select-Object -Skip 1)
        $testArgs = $extra + @("-c", "import sys; print(sys.version_info >= (3, 10))")
        try {
            $ok = & $exe.Source @testArgs 2>$null
            if ($ok -eq "True") { $found = @($exe.Source) + $extra; return ,$found }
        } catch { }
    }
    return $null
}

Write-Host ""
Write-Host "  Bolo Dukaan for Restaurants" -ForegroundColor Yellow
Write-Host ""

if ($PSScriptRoot.Length -gt 150) {
    Write-Host "  Note: this folder path is very long. If installing fails, move the folder somewhere short like C:\bolo-dukaan" -ForegroundColor DarkYellow
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $py = Find-Python
    if (-not $py) {
        Write-Host "  Python 3.10 or newer was not found." -ForegroundColor Red
        Write-Host "  Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run start.bat again."
        Read-Host "  Press Enter to close"
        exit 1
    }
    Write-Host "  First run: creating a private Python environment (.venv)..."
    $pyExe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1) + @("-m", "venv", ".venv")
    & $pyExe @pyArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "  Could not create .venv" -ForegroundColor Red; Read-Host "  Press Enter to close"; exit 1 }
}

$marker = Join-Path $PSScriptRoot ".venv\.installed"
$reqHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot "requirements.txt")).Hash
if (-not (Test-Path $marker) -or (Get-Content -LiteralPath $marker -Raw).Trim() -ne $reqHash) {
    Write-Host "  Installing packages (one small pure-Python package)..."
    & $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "  Package install failed. Check the internet connection." -ForegroundColor Red; Read-Host "  Press Enter to close"; exit 1 }
    Set-Content -LiteralPath $marker -Value $reqHash -Encoding ascii
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  Created .env. Open it in Notepad and add your Gemini and Cashfree keys." -ForegroundColor Cyan
}

$runArgs = @("run.py", "--port", "$Port")
if ($NoBrowser) { $runArgs += "--no-browser" }
& $venvPy @runArgs
if ($LASTEXITCODE -ne 0) { Read-Host "  The server stopped with an error. Press Enter to close" }
