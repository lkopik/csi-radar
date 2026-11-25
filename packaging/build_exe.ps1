# Сборка CSI_radar.exe и CSI_radar_demo.exe в dist\.
# Получаются из переносимого Python 3.8 (python\), поэтому работают на Windows 7 SP1 и новее.
# Запуск из корня проекта:
#     powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root 'python\python.exe'
if (-not (Test-Path $py)) { throw "python\python.exe not found: build needs the bundled Python 3.8" }
Set-Location $root

& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name CSI_radar --paths . csi_radar.py
if ($LASTEXITCODE -ne 0) { throw "CSI_radar build failed" }

& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name CSI_radar_demo --paths . packaging\csi_radar_demo.py
if ($LASTEXITCODE -ne 0) { throw "CSI_radar_demo build failed" }

Get-ChildItem (Join-Path $root 'dist') -Filter *.exe | Select-Object Name, Length
