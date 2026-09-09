"""Safe compaction boundaries inside a long tool-using turn."""
from pydantic_ai.messages import (
    ModelRequest, ModelResponse, RetryPromptPart, SystemPromptPart,
    ToolCallPart, ToolReturnPart,
)

from zhishi.agent.context_budget import safe_round_starts
from zhishi.agent.context_parts import is_user_input


def step_boundaries(messages: list) -> list[int]:
    """Cut before an assistant step only after all earlier calls are resolved."""
    pending = set()
    completed = False
    cuts = set(safe_round_starts(messages))
    for index, message in enumerate(messages):
        if isinstance(message, ModelResponse) and completed and not pending:
            cuts.add(index)
        for part in message.parts:
            kind = getattr(part, 'part_kind', '')
            if isinstance(part, ToolCallPart) or kind == 'native-tool-call':
                pending.add(part.tool_call_id)
            elif (isinstance(part, ToolReturnPart) or kind == 'native-tool-return'
                  or isinstance(part, RetryPromptPart) and part.tool_name):
                pending.discard(part.tool_call_id)
                completed = True
    return sorted(cut for cut in cuts if 0 < cut < len(messages))


def retained_prefix(messages: list, cut: int) -> list:
    """Preserve system prompts and verbatim user input in a split current turn.

    No pending tool call is copied or separated from its result. A mixed request
    can carry further user input; those input parts remain pinned as well.
    """
    starts = safe_round_starts(messages)
    current = starts[-1] if starts else 0
    system = [part for message in messages[:cut] if isinstance(message, ModelRequest)
              for part in message.parts if isinstance(part, SystemPromptPart)]
    user = [part for message in messages[current:cut] if isinstance(message, ModelRequest)
            for part in message.parts if is_user_input(part)] if cut > current else []
    return ([ModelRequest(parts=system)] if system else []) + ([ModelRequest(parts=user)] if user else [])
