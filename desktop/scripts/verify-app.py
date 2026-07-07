"""冒烟测试：启动 win-unpacked/知时.exe，确认后端就绪，再优雅退出。

验证 Electron 打包后能正确拉起 resources 里的后端子进程。
启动期间窗口会短暂弹出，验证后自动关闭。
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "desktop" / "release" / "win-unpacked" / "知时.exe"


def find_backend(timeout: float = 50):
    """扫描 18731-18740 端口范围，找后端 /health 200 的端口。"""
    for i in range(int(timeout / 0.5)):
        for port in range(18731, 18741):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as r:
                    if r.status == 200:
                        return port, i
            except Exception:
                continue
        time.sleep(0.5)
    return None, -1


def main() -> None:
    if not APP.exists():
        print(f"[fail] 应用不存在: {APP}")
        sys.exit(1)
    print(f"启动 {APP.name}（窗口会短暂弹出）")
    proc = subprocess.Popen([str(APP)])
    port, tries = find_backend()
    if port is None:
        print("[fail] 50s 内未在后端端口范围发现 /health")
        proc.kill()
        sys.exit(1)
    print(f"[ok] 后端就绪 port={port} (try {tries})")

    # 触发托盘式优雅退出：/shutdown 让后端备份+落盘并 exit(0) → Electron app.quit()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", method="POST")
        urllib.request.urlopen(req, timeout=3)
        print("[ok] /shutdown 已发送")
    except Exception as e:
        print(f"[warn] /shutdown: {e}")

    try:
        proc.wait(timeout=12)
        print(f"[ok] 应用退出 code={proc.returncode}")
    except subprocess.TimeoutExpired:
        print("[warn] 12s 未退出，kill")
        proc.kill()


if __name__ == "__main__":
    main()
