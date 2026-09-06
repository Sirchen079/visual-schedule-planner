from types import SimpleNamespace

import pytest

from scripts import build


@pytest.mark.parametrize("keep", [True, False])
def test_smoke_keeps_diagnostics_only_when_requested(tmp_path, monkeypatch, keep):
    work = tmp_path / "smoke"
    work.mkdir()

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = -1

    monkeypatch.setattr(build.tempfile, "mkdtemp", lambda **kwargs: str(work))
    monkeypatch.setattr(build, "free_port", lambda: 12345)
    monkeypatch.setattr(build.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(build, "_health_ok", lambda port: True)
    monkeypatch.setattr(build, "_loopback_request", lambda *args, **kwargs: SimpleNamespace(status=200))
    build.smoke(keep_dir=keep)
    assert work.exists() is keep
    if keep:
        assert (work / "smoke-stdout.log").is_file()
