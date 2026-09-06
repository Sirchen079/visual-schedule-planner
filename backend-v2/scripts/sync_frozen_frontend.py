"""Stage rebuilt static assets in the existing frozen backend, without changing backend code."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = (root / 'frontend/dist').resolve()
target = (root / 'dist/zhishi-backend/_internal/frontend/dist').resolve()
assert source.is_relative_to(root) and target.is_relative_to(root)
assert (source / 'index.html').is_file() and (target / 'index.html').is_file()
original = {p.relative_to(source):p for p in source.rglob('*') if p.is_file()}
for p in target.rglob('*'):
    assert p.resolve().is_relative_to(target)
    if p.is_file() and p.relative_to(target) not in original:
        p.unlink()
for relative, p in original.items():
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(p, dest)
assert {p.relative_to(target) for p in target.rglob('*') if p.is_file()} == set(original)
assert all(p.read_bytes() == (target / relative).read_bytes() for relative, p in original.items())
print(f'FROZEN_FRONTEND_MATCHES: {len(original)} files')
