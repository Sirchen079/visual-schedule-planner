# zhishi-backend.spec
# PyInstaller 打包配置：onedir，入口 src/zhishi/server/app.py:main。
# 构建命令：python scripts/build.py（内含打包后自动冒烟 /health → /shutdown）。
# 数据不打入包内：运行时经 ZHISHI_DATA_DIR / 工作目录 data/ 落盘。
# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

# genai_prices（pydantic-ai 价格表）/ keyring 后端等在运行时经 importlib.metadata
# 读包元数据，冻结环境必须显式拷贝 .dist-info
datas = sum((copy_metadata(p) for p in (
    "genai_prices", "pydantic_ai_slim", "pydantic_graph", "pydantic",
    "openai", "anthropic", "fastapi", "uvicorn", "keyring", "icalendar",
    "pdfplumber", "python_multipart",
)), [])
binaries = []
hiddenimports = [
    # uvicorn 动态导入常见坑
    'uvicorn.logging',
    'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
    'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
    'uvicorn.protocols', 'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    # fastapi 表单解析依赖 python-multipart（运行时字符串导入）
    'python_multipart',
    # pydantic-ai 模型/供应商注册表按字符串动态导入
    'pydantic_ai.models.openai', 'pydantic_ai.models.anthropic',
    'pydantic_ai.providers.openai', 'pydantic_ai.providers.anthropic',
    # 解析管道：pdf / docx / xlsx
    'pdfplumber', 'pdfminer', 'pdfminer.pdfpage', 'pdfminer.pdfinterp',
    'pdfminer.pdfdocument', 'pdfminer.converter', 'pdfminer.layout',
    'docx', 'openpyxl',
    # 日历与凭据
    'icalendar', 'keyring', 'keyring.backends.Windows',
]
# fastmcp/pydantic_ai.mcp 为 try-import 懒加载且内部高度动态，整包收集。
# 排除 mcp.cli（依赖未安装的 typer；运行时只用 client 部分）
for _pkg in ("fastmcp", "mcp", "mcp_types"):
    _d, _b, _h = collect_all(
        _pkg, on_error="ignore",
        filter_submodules=lambda n, _p=_pkg: not n.startswith("mcp.cli"))
    datas += _d
    binaries += _b
    hiddenimports += _h

# 前端静态资源随包交付（自包含发布：frozen 模式经 _MEIPASS/frontend/dist 托管）。
# 目录缺失时告警跳过（纯 API 后端包仍可构建，运行时可用 ZHISHI_FRONTEND_DIR 外置）。
_fe = 'frontend/dist'
if os.path.exists(os.path.join(_fe, 'index.html')):
    datas.append((_fe, 'frontend/dist'))
else:
    print('[spec] WARN: frontend/dist 缺失，构建纯后端包（不含静态前端）')

a = Analysis(
    ['src\\zhishi\\server\\app.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['tkinter', 'matplotlib', 'IPython', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='zhishi-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='zhishi-backend',
)
