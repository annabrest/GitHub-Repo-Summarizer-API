import os


def get_llm_config() -> dict:
    nebius_key = os.getenv("NEBIUS_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if nebius_key:
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            raise ValueError("LLM_BASE_URL and LLM_MODEL are required when NEBIUS_API_KEY is set")
        return {"api_key": nebius_key, "base_url": base_url, "model": model}

    elif openai_key:
        return {"api_key": openai_key, "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}

    else:
        raise ValueError("No LLM API key configured. Set NEBIUS_API_KEY or OPENAI_API_KEY.")
