"""Offline text token estimates with a margin for different provider tokenizers."""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from math import ceil
from pathlib import Path

# cl100k_base's vocabulary and expression are distributed under tiktoken's MIT
# license; see THIRD_PARTY_NOTICES.md. Loading never contacts a remote service.
_VOCAB_SHA256 = '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7'
_PATTERN = r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    raw = (Path(__file__).parent / 'vocab' / 'cl100k_base.tiktoken').read_bytes()
    if hashlib.sha256(raw).hexdigest() != _VOCAB_SHA256:
        raise ValueError('Bundled token vocabulary failed its integrity check')
    ranks = {base64.b64decode(token): int(rank) for token, rank in
             (line.split() for line in raw.splitlines() if line)}
    return tiktoken.Encoding(name='zhishi_cl100k', pat_str=_PATTERN,
                             mergeable_ranks=ranks, special_tokens={})


def count_text(text: str) -> int:
    """A local BPE estimate, not the gateway's billable usage.

    A 15% margin accounts for common tokenizer differences. Binary/media costs
    are handled separately. Unavailable vocabulary falls back to the byte bound
    without downloading anything or making an otherwise usable chat unavailable.
    """
    if not text:
        return 0
    try:
        return ceil(len(_encoding().encode_ordinary(text)) * 1.15)
    except (ImportError, OSError, ValueError):
        return len(text.encode('utf-8', errors='replace'))
