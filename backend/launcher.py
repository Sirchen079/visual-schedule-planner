"""PyInstaller 打包入口：解析 --host/--port 并启动 uvicorn 服务。

打包后由 Electron 主进程以子进程方式拉起。延迟 import app.main，
让 config/database 在 frozen 检测后初始化（数据目录由 ZHISHI_DATA_DIR 环境变量决定，
默认跟随安装目录，回退到 %APPDATA%/知时/data）。
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="知时后端服务入口")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18731)
    args = parser.parse_args()

    # 先初始化文件日志（config/database 已在 import 时按 frozen 状态解析好数据根），
    # 再 import app.main —— 这样 app 加载、DB 迁移、路由注册全程都有日志覆盖。
    from app.services.log_service import setup_logging

    log_file = setup_logging()
    import logging

    logging.getLogger("launcher").info(
        "后端启动 host=%s port=%s log=%s", args.host, args.port, log_file
    )

    import uvicorn
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
