from pathlib import Path

import zhishi


def test_import_package():
    version = (Path(__file__).resolve().parents[2] / "VERSION").read_text(
        encoding="utf-8").strip()
    assert zhishi.__version__ == version
