@echo off
setlocal
cd /d "%~dp0"
if not exist "backend-v2\dist\zhishi-backend\zhishi-backend.exe" (
  echo Build the backend first. See README.md.
  pause
  exit /b 1
)
if not exist "electron-v2\node_modules\electron\dist\electron.exe" (
  echo Install desktop dependencies first. See README.md.
  pause
  exit /b 1
)
pushd electron-v2
call npm start
set "result=%errorlevel%"
popd
exit /b %result%
