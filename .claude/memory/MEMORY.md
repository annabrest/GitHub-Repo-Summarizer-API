# Project Memory — GitHub Repo Summarizer API

## What this is
Nebius Academy admission assignment. FastAPI service: `POST /summarize` accepts GitHub URL, fetches repo via GitHub REST API (no cloning), selects informative files, builds context, calls LLM, returns structured JSON.

## User preferences
- **Show code in chat, don't edit files directly** — user writes code themselves
- Explain concepts, don't over-scaffold
- Ask before assuming on approach decisions
- When in "editing mode" (user says "proceed by yourself"): edit files directly, stop after each piece for review

## Build state: Steps 0–12 complete. Next: Step 13 (parsing.py)

## Key files
- `app/main.py` — FastAPI app + all debug endpoints (incl. /debug/llm)
- `app/github_client.py` — GitHub API calls (timeout=10s, full error handling)
- `app/models.py` — Pydantic models
- `app/selection.py` — file filtering + ranking (Step 8 complete)
- `app/context.py` — LLM context builder with char budgets (Step 10 complete)
- `app/settings.py` — get_llm_config(): Nebius/OpenAI provider selection (Step 11)
- `app/llm_client.py` — async call_llm(), map/reduce builders, prompts (Steps 11+12)
- `app/parsing.py` — empty (Step 13 next)
- `Implimentation/Implimentation_plan_PRD_v1.2.2.md` — step-by-step plan (Steps 0–18)
- `PRD/PRD_GitHub_Summarizer_API_v1.2.2.md` — full PRD

## See session_summary.md for current build state
