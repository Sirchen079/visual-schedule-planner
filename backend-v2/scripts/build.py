# scripts/build.py
"""PyInstaller 打包 + 自动冒烟。

流程：
  1. 以当前解释器运行 pyinstaller（zhishi-backend.spec，onedir）。
  2. 冒烟：随机端口启动 dist/zhishi-backend/zhishi-backend.exe --port N，
     轮询 /health 至 200，POST /shutdown，等待进程退出码 0。
  3. 任一步失败 exit 1。冒烟数据目录指向临时目录，绝不触碰仓库/真实 data/。

用法：python scripts/build.py [--skip-build] [--keep-smoke-dir]
"""
from __future__ import annotations

import argparse
import http.client
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "zhishi-backend" / "zhishi-backend.exe"
HEALTH_TIMEOUT_SEC = 90.0


def build() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           str(ROOT / "zhishi-backend.spec")]
    print(f"[build] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"[build] PyInstaller 失败（exit {proc.returncode}）")
    if not EXE.is_file():
        raise SystemExit(f"[build] 未找到产物：{EXE}")
    print(f"[build] 产物就绪：{EXE}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _loopback_request(path: str, port: int, *, method: str = "GET",
                      timeout: float = 3) -> http.client.HTTPResponse:
    """构建冒烟只访问本机后端：主机为字面量回环地址、端口为整数，
    不构造动态 URL，收窄 SSRF 面。响应体必须读尽后关闭连接。"""
    if not 1 <= port <= 65535:
        raise ValueError(f"非法端口：{port}")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path)
        resp = conn.getresponse()
        resp.read()
        return resp
    finally:
        conn.close()


def _health_ok(port: int) -> bool:
    try:
        return _loopback_request("/health", port).status == 200
    except (OSError, ValueError):
        return False


def _log_tail(path: Path, lines: int = 15) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def smoke(*, keep_dir: bool = False) -> None:
    port = free_port()
    smoke_dir = Path(tempfile.mkdtemp(prefix="zhishi-smoke-"))
    env = dict(os.environ, ZHISHI_DATA_DIR=str(smoke_dir))
    proc = None
    out_log = None
    try:
        print(f"[smoke] 启动 {EXE.name} --port {port}（数据目录 {smoke_dir}）")
        out_log = (smoke_dir / "smoke-stdout.log").open("wb")
        proc = subprocess.Popen([str(EXE), "--port", str(port)], cwd=smoke_dir,
                                env=env, stdout=out_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + HEALTH_TIMEOUT_SEC
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out_log.close()
                tail = _log_tail(smoke_dir / "smoke-stdout.log")
                raise SystemExit(f"[smoke] 进程提前退出（exit {proc.returncode}）\n{tail}")
            if _health_ok(port):
                break
            time.sleep(0.5)
        else:
            out_log.close()
            proc.kill()
            raise SystemExit(f"[smoke] {HEALTH_TIMEOUT_SEC:.0f}s 内 /health 未就绪\n"
                             f"{_log_tail(smoke_dir / 'smoke-stdout.log')}")

        assert _loopback_request("/shutdown", port, method="POST",
                                 timeout=5).status == 200
        code = proc.wait(timeout=30)
        out_log.close()
        if code != 0:
            raise SystemExit(f"[smoke] /shutdown 后退出码非 0：{code}\n"
                             f"{_log_tail(smoke_dir / 'smoke-stdout.log')}")
        print("[smoke] 通过：/health 200 → /shutdown → exit 0")
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        if out_log is not None:
            out_log.close()
        if keep_dir:
            print(f"[smoke] 保留诊断目录：{smoke_dir}")
        else:
            shutil.rmtree(smoke_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 zhishi-backend 并冒烟")
    parser.add_argument("--skip-build", action="store_true", help="跳过打包只跑冒烟")
    parser.add_argument("--keep-smoke-dir", action="store_true",
                        help="保留冒烟临时数据目录（排障用）")
    args = parser.parse_args()
    if not args.skip_build:
        build()
    smoke(keep_dir=args.keep_smoke_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
