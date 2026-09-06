"""Frozen v2 ledger smoke: exact arithmetic, replay, edits, restore and process restart.

Only a random loopback port and a fresh temporary database are used. No model or secrets.
"""
import argparse
import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def request(port, path, method="GET", body=None, expected=200):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        data = json.dumps(body) if body is not None else None
        conn.request(method, path, data, {"Content-Type": "application/json"} if data else {})
        response = conn.getresponse()
        raw = response.read()
        assert response.status == expected, (path, response.status, raw[:300])
        return json.loads(raw) if raw else None
    finally:
        conn.close()


def start(exe, root, label):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (root / f"{label}.log").open("wb")
    proc = subprocess.Popen([str(exe), "--port", str(port)], cwd=root,
        env={**os.environ, "ZHISHI_DATA_DIR": str(root)}, stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        for _ in range(300):
            if proc.poll() is not None:
                raise RuntimeError(f"Backend exited: {proc.returncode}")
            try:
                request(port, "/health")
                return proc, log, port
            except (OSError, AssertionError):
                time.sleep(.2)
        raise TimeoutError("Backend not ready")
    except BaseException:
        proc.kill(); proc.wait(); log.close()
        raise


def stop(proc, log, port):
    try:
        request(port, "/shutdown", "POST")
        assert proc.wait(timeout=15) == 0
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()
        log.close()


def verify(exe):
    root = Path(tempfile.mkdtemp(prefix="zhishi-ledger-frozen-"))
    print(f"LEDGER_CHECK_ROOT={root}", flush=True)
    proc, log, port = start(exe, root, "first")
    report_path = "/api/ledger/summary?start=2026-09-01&end=2026-09-30"
    try:
        base = {"day": "2026-09-05", "direction": "expense", "amount": "28.50",
                "category": "餐饮", "idempotency_key": "frozen-lunch"}
        row = request(port, "/api/ledger", "POST", base, 201)
        assert row["amount"] == "28.50"
        assert request(port, "/api/ledger", "POST", base, 201)["id"] == row["id"]
        request(port, "/api/ledger", "POST", {**base, "amount": "29"}, 409)
        request(port, "/api/ledger", "POST", {**base, "amount": "0.001"}, 422)
        for amount in ("0.10", "0.20"):
            request(port, "/api/ledger", "POST", {**base, "amount": amount,
                    "idempotency_key": f"frozen-{amount}"}, 201)
        request(port, "/api/ledger", "POST", {**base, "currency": "USD", "amount": "5",
                "idempotency_key": "frozen-usd"}, 201)
        change = {k: v for k, v in base.items() if k != "idempotency_key"}
        request(port, f"/api/ledger/{row['id']}", "PUT", {**change, "amount": "29", "version": 1})
        request(port, f"/api/ledger/{row['id']}?version=1", "DELETE", expected=409)
        request(port, f"/api/ledger/{row['id']}?version=2", "DELETE")
        assert request(port, report_path)["currencies"][0]["expense"] == "0.30"
        request(port, f"/api/ledger/{row['id']}/restore", "POST", {"version": 3})
        assert request(port, report_path)["currencies"][0]["expense"] == "29.30"
        print("LEDGER_WRITES_PRECISION_REPLAY_RESTORE_PASS", flush=True)
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, "restart")
    try:
        totals = request(port, report_path)["currencies"]
        assert [(r["currency"], r["expense"]) for r in totals] == [("CNY", "29.30"), ("USD", "5.00")]
        assert request(port, "/api/ledger")["total"] == 4
        schemas = request(port, "/openapi.json")["components"]["schemas"]
        assert "EntryCreate" in schemas and "LedgerSummary" in schemas
        print("LEDGER_RESTART_CURRENCIES_CONTRACT_PASS", flush=True)
    finally:
        stop(proc, log, port)
    print("LEDGER_FROZEN_PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[1] /
                        "dist" / "zhishi-backend" / "zhishi-backend.exe")
    args = parser.parse_args()
    verify(args.exe.resolve(strict=True))
