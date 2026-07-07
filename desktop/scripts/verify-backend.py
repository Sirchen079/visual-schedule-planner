"""验证打包后的 zhishi-backend.exe 能启动并提供服务。

启动 exe → 轮询 /health → 测 /tasks → POST /shutdown → 确认进程退出。
frozen 模式下数据写入 %APPDATA%/知时/data（真实产品路径）。
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "desktop" / "build" / "backend-dist" / "zhishi-backend" / "zhishi-backend.exe"
PORT = 18799
BASE = f"http://127.0.0.1:{PORT}"


def wait_health(timeout: float = 40) -> bool:
    deadline = time.time() + timeout
    i = 0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=1) as r:
                if r.status == 200:
                    print(f"[ok] /health 200 (try {i})")
                    return True
        except Exception:
            time.sleep(0.3)
            i += 1
    return False


def main() -> None:
    if not EXE.exists():
        print(f"[fail] exe 不存在: {EXE}")
        sys.exit(1)

    cwd = os.environ.get("APPDATA") or str(Path.home())
    print(f"启动 {EXE.name}（cwd={cwd}）")
    proc = subprocess.Popen(
        [str(EXE), "--port", str(PORT)],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        if not wait_health():
            out = b""
            if proc.stdout:
                try:
                    out = proc.stdout.read(4000)
                except Exception:
                    pass
            print(f"[fail] /health 超时\n--- exe 输出 ---\n{out.decode('utf-8', 'replace')}")
            proc.kill()
            sys.exit(1)

        try:
            with urllib.request.urlopen(f"{BASE}/tasks", timeout=5) as r:
                body = r.read(120)
            print(f"[ok] /tasks {r.status} {body!r}")
        except Exception as e:
            print(f"[warn] /tasks 失败: {e}")

        try:
            req = urllib.request.Request(f"{BASE}/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=3)
            print("[ok] /shutdown 已发送")
        except Exception as e:
            print(f"[warn] /shutdown 失败: {e}")

        try:
            proc.wait(timeout=6)
            print(f"[ok] 进程退出 code={proc.returncode}")
        except subprocess.TimeoutExpired:
            print("[warn] 进程未在 6s 内退出，kill")
            proc.kill()
    finally:
        if proc.poll() is None:
            proc.kill()

    data_dir = Path(os.environ.get("APPDATA") or "") / "知时" / "data"
    if data_dir.exists():
        print(f"[ok] 数据目录已创建: {data_dir}")


if __name__ == "__main__":
    main()
