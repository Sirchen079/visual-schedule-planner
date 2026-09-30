"""Vocabulary loading survives Windows checkouts without accepting altered data."""
from pathlib import Path

import pytest

from zhishi.agent import token_count


@pytest.fixture
def vocabulary_copy(tmp_path, monkeypatch):
    raw = (Path(token_count.__file__).parent / 'vocab' / 'cl100k_base.tiktoken').read_bytes()
    vocab = tmp_path / 'vocab' / 'cl100k_base.tiktoken'
    vocab.parent.mkdir()
    monkeypatch.setattr(token_count, '__file__', str(tmp_path / 'token_count.py'))
    token_count._encoding.cache_clear()
    yield vocab, raw
    token_count._encoding.cache_clear()


@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
def test_vocabulary_line_endings_keep_bpe_estimates(vocabulary_copy, newline):
    vocab, raw = vocabulary_copy
    vocab.write_bytes(raw.replace(b'\r\n', b'\n').replace(b'\n', newline))

    assert len(token_count._encoding().encode_ordinary('abc')) == 1
    assert token_count.count_text('abc') == 2
    assert 4 <= token_count.count_text('中文🙂') <= 10


@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
def test_vocabulary_content_changes_still_fail_integrity(vocabulary_copy, newline):
    vocab, raw = vocabulary_copy
    vocab.write_bytes((raw + b'altered\n').replace(b'\r\n', b'\n').replace(b'\n', newline))

    with pytest.raises(ValueError, match='integrity check'):
        token_count._encoding()
    assert token_count.count_text('中文🙂') == len('中文🙂'.encode())
