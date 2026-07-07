# -*- mode: python ; coding: utf-8 -*-
"""知时后端 PyInstaller 打包配置（onedir，无控制台窗口）。

构建命令（在 backend/ 目录下）：
    python -m PyInstaller zhishi-backend.spec --noconfirm

产物：dist/zhishi-backend/zhishi-backend.exe（含 _internal/ 资源）
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 前端构建产物（供 FastAPI StaticFiles 托管）+ 文档解析库的运行时资源
datas = [("../frontend/dist", "frontend/dist")]
datas += collect_data_files("pypdf")
datas += collect_data_files("docx")
datas += collect_data_files("openpyxl")
datas += collect_data_files("pptx")

# 动态 import 的子模块需显式收集，避免运行时 ModuleNotFoundError
hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("app")
hiddenimports += [
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.sql.default_comparator",
    "greenlet",
    "h11",
    "anyio",
    "sniffio",
    "httptools",
    "websockets",
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],  # 让 import app.* 在收集期可解析
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "playwright"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="zhishi-backend",  # ASCII exe 名，规避 Electron spawn 中文文件名风险
    console=False,  # GUI 模式，不弹黑窗；排错时改 True 看完整堆栈
    icon="../desktop/build/icon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="zhishi-backend")
