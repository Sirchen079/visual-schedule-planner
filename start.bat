@echo off
cd /d "%~dp0"

set "PYTHON_EXE="

if exist "backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=backend\.venv\Scripts\python.exe"
) else (
    python --version >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python was not found.
    echo Install Python 3.11+ or create backend\.venv as described in README.md.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -c "import uvicorn, fastapi, sqlalchemy, pydantic, pydantic_settings, multipart, httpx" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Backend runtime dependencies are missing for the selected Python.
    echo.
    echo Selected Python: %PYTHON_EXE%
    echo.
    echo Option 1, recommended isolated install:
    echo   python -m venv backend\.venv
    echo   backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    echo.
    echo Option 2, install into the current Python:
    echo   %PYTHON_EXE% -m pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [ERROR] Frontend build output was not found: frontend\dist\index.html
    echo Run this before starting:
    echo   cd frontend
    echo   npm install
    echo   npm run build
    echo.
    pause
    exit /b 1
)

dir /b "frontend\dist\assets\*.js" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Frontend JavaScript assets were not found under frontend\dist\assets.
    echo Run: cd frontend ^&^& npm run build
    pause
    exit /b 1
)

echo ========================================
echo   Visual Schedule is starting...
echo ========================================
echo Python: %PYTHON_EXE%

start "Schedule Service" cmd /k "%PYTHON_EXE% -m uvicorn app.main:app --host 127.0.0.1 --port 18731 --app-dir backend"

echo Waiting for the service to become ready...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0; $i -lt 40; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18731/health' -TimeoutSec 1; if($r.StatusCode -eq 200){ $ok=$true; break } } catch { Start-Sleep -Seconds 1 } }; if(-not $ok){ exit 1 }" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Service did not become ready. Check the Schedule Service window.
    pause
    exit /b 1
)

echo Opening browser...
start "" http://127.0.0.1:18731

echo.
echo If the browser did not open, visit: http://127.0.0.1:18731
echo To stop the service, use the shutdown button in the page or close the service window.
echo.
pause
