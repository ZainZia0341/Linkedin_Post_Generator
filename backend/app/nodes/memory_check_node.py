from __future__ import annotations

from langchain_core.messages import RemoveMessage

from app.config import DEFAULT_MAX_MESSAGES
from app.graph_state_schema import GraphState


def delete_messages(state: GraphState) -> dict[str, object]:
    messages = list(state.get("messages", []))
    if len(messages) <= DEFAULT_MAX_MESSAGES:
        print(f"Memory check kept {len(messages)} message(s).")
        return {"messages": messages}

    trimmed = messages[-DEFAULT_MAX_MESSAGES:]
    print(f"Memory check trimmed {len(messages) - len(trimmed)} old message(s).")
    return {"messages": trimmed}


def remove_message_commands(messages: list[object], keep_last: int = DEFAULT_MAX_MESSAGES) -> list[RemoveMessage]:
    old_messages = messages[:-keep_last] if keep_last else messages
    commands = []
    for message in old_messages:
        message_id = getattr(message, "id", None)
        if message_id:
            commands.append(RemoveMessage(id=message_id))
    return commands
