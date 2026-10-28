@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe csi_radar.py --port COM10 %*
