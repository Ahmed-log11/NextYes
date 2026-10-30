"""Ask a model to answer through one tool, on any model.

Some models accept a forced tool call (tool_choice "tool"); others reject it with a 400
("tool_choice ... not supported for this model"). We try forced first, and on that error
retry with the tool optional (tool_choice "auto") plus an explicit instruction to use it.
If the model still answers in plain text, the JSON object in the text is used. Which models
reject forcing is remembered for the process, so the retry costs one call only once.
"""

from __future__ import annotations

import json
import re
from typing import Any

_NO_FORCING: set[str] = set()


def _from_text(resp: Any, tool: dict[str, Any]) -> dict[str, Any] | None:
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            out = json.loads(m.group())
            if isinstance(out, dict):
                return out
        except json.JSONDecodeError:
            pass
    props = list(tool["input_schema"]["properties"])
    return {props[0]: text} if len(props) == 1 else None  # a single free-text field, e.g. a reply


def call_tool(client: Any, *, model: str, tool: dict[str, Any], stream: bool = False, **request: Any):
    """Returns (fields, response). `request` holds system, messages, max_tokens..."""

    def send(tool_choice: dict[str, Any], extra_text: str | None = None):
        req = dict(request, model=model, tools=[tool], tool_choice=tool_choice)
        if extra_text:
            msgs = [dict(m) for m in req["messages"]]
            content = msgs[-1]["content"]
            note = {"type": "text", "text": extra_text}
            msgs[-1]["content"] = (content + [note]) if isinstance(content, list) else f"{content}\n\n{extra_text}"
            req["messages"] = msgs
        if stream:
            with client.messages.stream(**req) as s:
                return s.get_final_message()
        return client.messages.create(**req)

    resp = None
    if model not in _NO_FORCING:
        try:
            resp = send({"type": "tool", "name": tool["name"]})
        except Exception as e:  # noqa: BLE001 — only the "forcing not supported" error is handled here
            if "tool_choice" not in str(e):
                raise
            _NO_FORCING.add(model)
    if resp is None:
        resp = send({"type": "auto"}, f"Answer by calling the {tool['name']} tool exactly once.")
    block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
    fields = dict(block.input) if block is not None else _from_text(resp, tool)
    return fields, resp
