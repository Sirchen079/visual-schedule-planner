"""验证打包后的 zhishi-backend.exe 能启动并提供服务。

启动 exe → 轮询 /health → 测 /tasks → POST /shutdown → 确认进程退出。
覆盖两条数据路径：
  1. 便携模式（ZHISHI_DATA_DIR 指定临时目录，模拟 Electron 拉起后端）；
  2. 回退模式（不设 ZHISHI_DATA_DIR、APPDATA 指向临时目录，验证默认解析链未被破坏）。
"""
import os
import shutil
import subprocess
import sys
import tempfile
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


def run_instance(label: str, env: dict, cwd: str, expect_db: Path) -> bool:
    """启动一个后端实例做基本验证，退出后由调用方清理临时目录。"""
    print(f"\n=== {label} ===")
    print(f"启动 {EXE.name}（cwd={cwd}）")
    proc = subprocess.Popen(
        [str(EXE), "--port", str(PORT)],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    ok = False
    try:
        if not wait_health():
            out = b""
            if proc.stdout:
                try:
                    out = proc.stdout.read(4000)
                except Exception:
                    pass
            print(f"[fail] /health 超时\n--- exe 输出 ---\n{out.decode('utf-8', 'replace')}")
            return False
        try:
            with urllib.request.urlopen(f"{BASE}/tasks", timeout=5) as r:
                body = r.read(120)
            print(f"[ok] /tasks {r.status} {body!r}")
            ok = True
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
    if expect_db.exists():
        print(f"[ok] 数据已写入: {expect_db}")
    else:
        print(f"[fail] 期望的数据未出现: {expect_db}")
        ok = False
    return ok


def main() -> None:
    if not EXE.exists():
        print(f"[fail] exe 不存在: {EXE}")
        sys.exit(1)

    results = []

    # 1. 便携模式：ZHISHI_DATA_DIR 显式指定临时数据目录（模拟产品中 Electron 拉起后端）
    portable = Path(tempfile.mkdtemp(prefix="zhishi-portable-"))
    try:
        env = {**os.environ, "ZHISHI_DATA_DIR": str(portable)}
        results.append(
            run_instance("便携模式 (ZHISHI_DATA_DIR)", env, str(portable), portable / "app.db")
        )
    finally:
        shutil.rmtree(portable, ignore_errors=True)

    # 2. 回退模式：不设 ZHISHI_DATA_DIR、APPDATA 指向临时目录，验证 frozen 默认解析链
    appdata = Path(tempfile.mkdtemp(prefix="zhishi-appdata-"))
    try:
        env = {k: v for k, v in os.environ.items() if k != "ZHISHI_DATA_DIR"}
        env["APPDATA"] = str(appdata)
        expect = appdata / "知时" / "data" / "app.db"
        results.append(run_instance("回退模式 (APPDATA)", env, str(appdata), expect))
    finally:
        shutil.rmtree(appdata, ignore_errors=True)

    if not all(results):
        print("\n[fail] 存在失败用例")
        sys.exit(1)
    print("\n[ok] 全部用例通过")


if __name__ == "__main__":
    main()
