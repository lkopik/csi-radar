@echo off
chcp 866 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title CSI-радар - демо

set "ARGS=--demo"
goto :main

:sys_python
set "SYS="
for %%v in (3.8 3.9 3.10 3.11 3.12 3.13) do if not defined SYS (
    for /f "delims=" %%i in ('py -%%v -c "import sys; print(sys.executable)" 2^>nul') do set "SYS=%%i"
)
if not defined SYS for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "SYS=%%i"
if not defined SYS exit /b 0
"%SYS%" -c "import sys; sys.exit(0 if (3, 8) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
echo.
echo Создаю окружение .venv (только при первом запуске)...
"%SYS%" -m venv .venv
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось создать .venv в этой папке.
    echo Скопируйте весь проект в папку, доступную для записи.
    goto :fail
)
set "PY=.venv\Scripts\python.exe"
exit /b 0

:broken
echo.
echo ОШИБКА: не удалось запустить Python: "%PY%"
echo Если это папка .venv - удалите её и запустите снова.
echo Если это папка python\ из комплекта - нужна 64-битная Windows 7 SP1 или новее.
goto :fail

:nopython
echo.
echo ОШИБКА: не найден Python 3.8-3.13.
echo Установите Python 3.8 с https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe
echo или принесите весь проект вместе с папкой python\ - тогда ничего ставить не нужно.
goto :fail

:fail
echo.
echo Программа остановлена.
pause
exit /b 1

:main
rem --- 1. переносимый Python из комплекта (работает и на Windows 7) ---
if exist "python\python.exe" set "PY=python\python.exe"
rem --- 2. окружение проекта .venv ---
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
rem --- 3. установленный в системе Python 3.8-3.13 ---
if not defined PY call :sys_python
if not defined PY goto :nopython

"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :broken

"%PY%" -c "import numpy, serial, pyqtgraph, PyQt5.QtCore" >nul 2>&1
if not errorlevel 1 goto :run

echo.
echo Ставлю зависимости (нужен интернет; только при первом запуске)...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
)
"%PY%" -c "import numpy, serial, pyqtgraph, PyQt5.QtCore" >nul 2>&1
if errorlevel 1 goto :fail

:run
echo.
echo CSI-радар запущен. Это окно можно свернуть.
echo Закройте его, чтобы остановить программу.
"%PY%" csi_radar.py %ARGS%
if errorlevel 1 goto :fail
exit /b 0