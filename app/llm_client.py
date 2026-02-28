import httpx
from app.settings import get_llm_config

LLM_TIMEOUT_S = 60.0
LLM_TEMPERATURE = 0

SYSTEM_PROMPT = """\
You are a code analysis assistant.
You MUST respond with valid JSON only — no markdown, no explanation, no code fences.
Return exactly this structure:
{"summary":"string","technologies":["string"],"structure":"string"}
If uncertain, say so briefly rather than guessing."""

USER_TEMPLATE = (
    "You will be given a GitHub repository snapshot (tree + key files). "
    "Produce:\n"
    "1) summary: what the project does and its key features.\n"
    "2) technologies: key languages/frameworks/tools (proper nouns, dedupe).\n"
    "3) structure: brief description of main folders/modules and their roles.\n\n"
    "Repository snapshot:\n"
    "{context}\n"
)

MAP_SYSTEM = (
    "Return JSON only. No markdown. "
    'Schema: {"chunk_summary":"string","tech_hints":["string"],"structure_hints":"string"}. '
    "Do not invent; use only evidence from the chunk."
)

REDUCE_SYSTEM = (
    "Return JSON only. No markdown. "
    'Schema: {"summary":"string","technologies":["string"],"structure":"string"}. '
    "If uncertain, say so briefly rather than guessing."
)


def build_user_message(context_str: str) -> str:
    return USER_TEMPLATE.format(context=context_str)


def build_map_messages(chunk_context: str) -> list[dict]:
    user = (
        "Summarize this repository chunk. Extract:\n"
        "- chunk_summary: what this chunk reveals\n"
        "- tech_hints: technologies suggested by this chunk\n"
        "- structure_hints: folder/module hints\n\n"
        f"Chunk:\n{chunk_context}\n"
    )
    return [{"role": "system", "content": MAP_SYSTEM}, {"role": "user", "content": user}]


def build_reduce_messages(tree_preview: str, map_summaries: list[dict]) -> list[dict]:
    user = (
        "You will be given partial summaries (from chunks) of a GitHub repo. "
        "Synthesize the final output.\n\n"
        "Directory tree (trimmed):\n"
        f"{tree_preview}\n\n"
        "Chunk summaries:\n"
        f"{map_summaries}\n\n"
        "Rules:\n"
        "- technologies must be deduped and concise.\n"
        "- summary should mention what it does and how it's typically run if evident.\n"
    )
    return [{"role": "system", "content": REDUCE_SYSTEM}, {"role": "user", "content": user}]


async def call_llm(context_str: str) -> str:
    config = get_llm_config()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(context_str)},
    ]
    return await _chat_completions(messages, config)


async def call_llm_map(chunk_context: str) -> str:
    config = get_llm_config()
    return await _chat_completions(build_map_messages(chunk_context), config)


async def call_llm_reduce(tree_preview: str, map_summaries: list) -> str:
    config = get_llm_config()
    return await _chat_completions(build_reduce_messages(tree_preview, map_summaries), config)


async def _chat_completions(messages: list[dict], config: dict) -> str:
    url = config["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": LLM_TEMPERATURE,
    }
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_S) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json=payload,
        )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
