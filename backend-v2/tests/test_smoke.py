# tests/test_smoke.py
def test_import_package():
    import zhishi
    assert zhishi.__version__ == "2.14.2"
