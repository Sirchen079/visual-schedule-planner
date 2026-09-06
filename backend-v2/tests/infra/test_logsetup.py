import logging
from zhishi.infra.logsetup import setup_logging

def test_setup_logging_writes_file(tmp_path):
    log_file = setup_logging(logs_dir=tmp_path, console=False)
    logging.getLogger("t").info("hello-zhishi")
    for h in logging.getLogger().handlers:
        h.flush()
    assert log_file.exists()
    assert "hello-zhishi" in log_file.read_text(encoding="utf-8")

def test_setup_logging_idempotent(tmp_path):
    a = setup_logging(logs_dir=tmp_path, console=False)
    b = setup_logging(logs_dir=tmp_path, console=False)
    assert a == b
