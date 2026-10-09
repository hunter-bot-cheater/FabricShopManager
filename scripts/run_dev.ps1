$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $VenvPython)) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { throw 'Python 3.11 or newer is required.' }
    & $PythonCommand.Source -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    & $VenvPython -m pip install -r (Join-Path $ProjectRoot 'backend\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }
}

Push-Location (Join-Path $ProjectRoot 'frontend')
try {
    if (-not (Test-Path 'node_modules')) { & npm install }
    if ($LASTEXITCODE -ne 0) { throw 'Could not install Vue dependencies.' }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the Vue frontend.' }
}
finally { Pop-Location }

$env:PYTHONPATH = Join-Path $ProjectRoot 'backend'
Push-Location $ProjectRoot
try { & $VenvPython (Join-Path $ProjectRoot 'desktop\main.py') }
finally { Pop-Location }
