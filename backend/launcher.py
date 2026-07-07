"""PyInstaller 打包入口：解析 --host/--port 并启动 uvicorn 服务。

打包后由 Electron 主进程以子进程方式拉起。延迟 import app.main，
让 config/database 在 frozen 检测后初始化（打包模式自动走 %APPDATA%/知时/data）。
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="知时后端服务入口")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18731)
    args = parser.parse_args()

    import uvicorn
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
