$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $basePython = $null
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike "*\WindowsApps\python.exe") {
        & $python.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $basePython = $python.Source
        }
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $basePython -and $launcher) {
        try {
            & $launcher.Source -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $basePython = & $launcher.Source -3 -c "import sys; print(sys.executable)"
            }
        } catch {
            $basePython = $null
        }
    }

    if (-not $basePython) {
        $uv = Get-Command uv -ErrorAction SilentlyContinue
        if ($uv) {
            & $uv.Source python install 3.12
            if ($LASTEXITCODE -ne 0) {
                throw "Could not install a managed Python 3.12 runtime."
            }
            $basePython = & $uv.Source python find 3.12
            if ($LASTEXITCODE -ne 0) {
                throw "Could not find the managed Python runtime."
            }
        }
    }

    if (-not $basePython) {
        throw "Python 3.9 or later is required. Install Python or install uv, then run this script again."
    }

    & $basePython -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the virtual environment. Check your Python installation."
    }
}

if (-not (Test-Path $pythonExe)) {
    throw "Could not create the virtual environment at $pythonExe"
}

$pythonVersion = & $pythonExe -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.9") {
    throw "Python 3.9 or later is required."
}

& $pythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

$env:SMARTALERT_HOST = "127.0.0.1"
Write-Host "Starting SmartAlert at http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop the server."
& $pythonExe server.py
