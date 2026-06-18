@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 backend\.venv
    echo 请先按 README.md 安装依赖。
    pause
    exit /b 1
)

echo ========================================
echo   可视化日程安排  正在启动...
echo ========================================

REM 在新窗口启动后端服务（前台可见日志；关闭该窗口即停止服务）
start "日程安排-服务（关闭即停止）" cmd /k "backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend"

REM 等待服务就绪
echo 等待服务就绪（约 4 秒）...
timeout /t 4 /nobreak >nul

REM 服务就绪后再打开浏览器
echo 打开浏览器...
start "" http://127.0.0.1:8000

echo.
echo   若浏览器没自动打开，请手动访问： http://127.0.0.1:8000
echo   停止服务：关闭弹出的"日程安排-服务"那个窗口。
echo.
pause
