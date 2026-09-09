"""Append application context without editing the user or pretending it is a new turn."""
from dataclasses import replace
import hashlib

from pydantic_ai.messages import CachePoint, ModelRequest, TextContent, UserPromptPart


def context_items(part):
    if isinstance(part, UserPromptPart) and not isinstance(part.content, str):
        return [item for item in part.content if isinstance(item, TextContent)
                and isinstance(item.metadata, dict) and item.metadata.get('zhishi_context')]
    return []


def is_user_input(part) -> bool:
    if not isinstance(part, UserPromptPart):
        return False
    if isinstance(part.content, str):
        return True
    return any(not isinstance(item, CachePoint) and not (
        isinstance(item, TextContent) and isinstance(item.metadata, dict) and item.metadata.get('zhishi_context'))
        for item in part.content)


def latest_context(messages, key):
    for message in reversed(messages):
        for part in reversed(message.parts):
            for item in reversed(context_items(part)):
                if item.metadata['zhishi_context'] == key:
                    return item.content
    return None


def append_context(messages, key, content, *, cache_before=False, cache_ttl='5m'):
    """The SDK persists these typed parts in its normal history checkpoint."""
    result = list(messages)
    item = TextContent(content, metadata={'zhishi_context': key,
                       'revision': hashlib.sha256(content.encode()).hexdigest()})
    part = UserPromptPart(content=[*([CachePoint(ttl=cache_ttl)] if cache_before else []), item])
    if result and isinstance(result[-1], ModelRequest):
        result[-1] = replace(result[-1], parts=[*result[-1].parts, part])
    else:
        result.append(ModelRequest(parts=[part]))
    return result


def adapt_cache_points(messages, ttl=None):
    """Historical provider hints must follow the current configuration/model."""
    result = []
    for message in messages:
        parts = []
        for part in message.parts:
            if isinstance(part, UserPromptPart) and not isinstance(part.content, str):
                content = [CachePoint(ttl=ttl) if isinstance(item, CachePoint) else item
                           for item in part.content if not isinstance(item, CachePoint) or ttl is not None]
                part = replace(part, content=content)
            parts.append(part)
        result.append(replace(message, parts=parts))
    return result
