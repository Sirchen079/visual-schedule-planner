# src/zhishi/infra/secrets.py
"""API key 加密存储：Windows DPAPI（keyring）。库内只存 keyring 引用名。"""
from __future__ import annotations
_SERVICE = "zhishi-backend-v2"


def store_api_key(name: str, value: str) -> None:
    import keyring
    keyring.set_password(_SERVICE, name, value)


def load_api_key(name: str) -> str | None:
    import keyring
    try:
        return keyring.get_password(_SERVICE, name)
    except Exception:
        return None


def delete_api_key(name: str) -> None:
    import keyring
    try:
        keyring.delete_password(_SERVICE, name)
    except Exception:
        pass
