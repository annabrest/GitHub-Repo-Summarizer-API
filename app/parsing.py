import json


def parse_llm_response(raw: str) -> dict:
    # Attempt 1 — direct parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        pass
    else:
        return _validate(data)  # ValueError from _validate propagates immediately

    # Attempt 2 — strip markdown fences, retry
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        pass
    else:
        return _validate(data)

    # Attempt 3 — extract first {...} block by bracket depth
    try:
        data = json.loads(_extract_object(raw))
    except (json.JSONDecodeError, ValueError):  # ValueError from _extract_object if no { found
        pass
    else:
        return _validate(data)

    raise ValueError(f"Could not parse LLM response: {raw[:200]!r}")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # remove opening fence line (```json or ```)
        text = text.split("\n", 1)[1]
        # remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text


def _extract_object(text: str) -> str:
    start = end = None
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                end = i + 1
                break
    if start is None or end is None:
        raise ValueError("No JSON object found in response")
    return text[start:end]


def _validate(data: dict) -> dict:
    required = {"summary", "technologies", "structure"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"LLM response missing keys: {missing}")
    if isinstance(data["technologies"], str):
        data["technologies"] = [t.strip() for t in data["technologies"].split(",") if t.strip()]
    return data
