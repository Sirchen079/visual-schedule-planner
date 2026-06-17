@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 backend\.venv
    echo 请先按 README.md 的步骤安装依赖。
    pause
    exit /b 1
)

echo 正在启动可视化日程安排... 浏览器将自动打开。
start "" http://127.0.0.1:8000
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
pause
