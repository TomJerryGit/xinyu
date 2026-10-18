@echo off
setlocal
cd /d "%~dp0"
set MMKV_LOG_LEVEL=off

set "PY=python"
python -c "import sys" >nul 2>nul
if errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)

if /i "%~1"=="--check" (
    %PY% -c "import sys, webview, cryptography; print(sys.executable); print('deps ok')"
    exit /b %errorlevel%
)

if not exist "data" mkdir "data"
%PY% -c "import webview, cryptography" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies, installing from requirements.txt ...
    %PY% -m pip install -r requirements.txt
)

%PY% app.py 2>"data\startup_error.log"
if errorlevel 1 (
    echo.
    echo Xinyu failed to start. See data\startup_error.log for details.
    pause
)
endlocal
