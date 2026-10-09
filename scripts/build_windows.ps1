$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Frontend = Join-Path $ProjectRoot 'frontend'

if (-not (Test-Path $VenvPython)) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { throw 'Python 3.11 or newer is required.' }
    & $PythonCommand.Source -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
& $VenvPython -m pip install -r (Join-Path $ProjectRoot 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }

Push-Location $Frontend
try {
    if (Test-Path 'package-lock.json') { & npm ci } else { & npm install }
    if ($LASTEXITCODE -ne 0) { throw 'Could not install Vue dependencies.' }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the Vue frontend.' }
}
finally { Pop-Location }

Push-Location $ProjectRoot
try {
    & $VenvPython -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name 'FabricShopManager' `
        --paths (Join-Path $ProjectRoot 'backend') `
        --add-data "$(Join-Path $Frontend 'dist');frontend/dist" `
        --hidden-import webview.platforms.edgechromium `
        --hidden-import openpyxl `
        --distpath (Join-Path $ProjectRoot 'release') `
        --workpath (Join-Path $ProjectRoot 'build') `
        (Join-Path $ProjectRoot 'desktop\main.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not package the desktop application.' }
}
finally { Pop-Location }

Write-Host "Desktop application created: $(Join-Path $ProjectRoot 'release\FabricShopManager.exe')"
