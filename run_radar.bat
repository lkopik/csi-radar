@echo off
chcp 866 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title CSI-радар - плата-приёмник

set "PORT="
rem --- порт: из аргумента --port, иначе единственный доступный, иначе вопрос ---
echo %* | find /i "--port" >nul
if not errorlevel 1 goto :port_from_arg
if exist "com_port.txt" set /p "PORT="<com_port.txt
if not defined PORT set "PORT=COM10"
set "FOUND="
set "MANY="
for /f "tokens=3" %%p in ('reg query HKLM\HARDWARE\DEVICEMAP\SERIALCOMM 2^>nul') do (
    if not defined FOUND (set "FOUND=%%p") else (set "MANY=1")
)
if not defined FOUND (
    echo.
    echo Плата не найдена: COM-порты отсутствуют.
    echo Будет использован %PORT%. Если порт другой - запустите: run_radar.bat --port COMx
    goto :port_ready
)
if defined MANY goto :port_ask
set "PORT=%FOUND%"
goto :port_ready

:port_ask
echo.
echo Доступные COM-порты:
for /f "tokens=3" %%p in ('reg query HKLM\HARDWARE\DEVICEMAP\SERIALCOMM 2^>nul') do echo    %%p
set "N=%PORT:COM=%"
set /p "P=Номер COM-порта платы-приёмника [%N%]: "
if defined P set "PORT=COM%P:COM=%"

:port_ready
if defined PORT >com_port.txt echo %PORT%
if defined NOADD set "ARGS=%*"
if not defined NOADD set "ARGS=--port %PORT% %*"
goto :main

:port_from_arg
set "NOADD=1"
set "PORT="
set "GRAB="
for %%a in (%*) do (
    if defined GRAB (
        set "PORT=%%a"
        goto :port_ready
    )
    if %%a==--port set "GRAB=1"
)
goto :port_ready
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
echo CSI-радар запущен (%ARGS%). Это окно можно свернуть.
echo Закройте его, чтобы остановить программу.
"%PY%" csi_radar.py %ARGS%
if errorlevel 1 goto :fail
exit /b 0