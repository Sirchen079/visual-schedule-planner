@echo off
rem 编译知时安装包：自动探测 Inno Setup 6 位置（适配多台开发机）
chcp 65001 >nul
setlocal enabledelayedexpansion

set "ISCC="

rem 1) 常见安装路径
for %%P in (
  "D:\Inno Setup 6\ISCC.exe"
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  "C:\Program Files\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do (
  if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
)

rem 2) 注册表兜底（HKCU / HKLM 卸载信息里的 InstallLocation）
if not defined ISCC (
  for /f "tokens=2,*" %%A in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" /v InstallLocation 2^>nul ^| findstr /i "InstallLocation"') do set "ISCC=%%BISCC.exe"
)
if not defined ISCC (
  for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" /v InstallLocation 2^>nul ^| findstr /i "InstallLocation"') do set "ISCC=%%BISCC.exe"
)

if not defined ISCC (
  echo [错误] 未找到 Inno Setup 6，请先安装：https://jrsoftware.org/issetup.php
  exit /b 1
)
if not exist "%ISCC%" (
  echo [错误] 探测到的 ISCC 路径无效：%ISCC%
  exit /b 1
)

echo 使用 ISCC: %ISCC%
cd /d "%~dp0\.."
"%ISCC%" installer\zhishi.iss
