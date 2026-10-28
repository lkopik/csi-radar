# Сборка и прошивка: .\build.ps1 csi_recv COM10   (без порта — только сборка)
# Нужен ESP-IDF v6.1, установленный через EIM (скрипт активации ниже).
param([string]$proj, [string]$port = "")
$ErrorActionPreference = "Continue"
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1 | Out-Null
Set-Location (Join-Path $PSScriptRoot $proj)
if (-not (Test-Path sdkconfig)) { idf.py set-target esp32s3 2>&1 | Select-Object -Last 5 }
idf.py build 2>&1 | Select-Object -Last 25
if ($port) { idf.py -p $port -b 921600 flash 2>&1 | Select-Object -Last 15 }
