# Project Memory — GitHub Repo Summarizer API

## What this is
Nebius Academy admission assignment. FastAPI service: `POST /summarize` accepts GitHub URL, fetches repo via GitHub REST API (no cloning), selects informative files, builds context, calls LLM, returns structured JSON.

## User preferences
- **Show code in chat, don't edit files directly** — user writes code themselves
- Explain concepts, don't over-scaffold
- Ask before assuming on approach decisions

## Key files
- `app/main.py` — FastAPI app + all debug endpoints
- `app/github_client.py` — GitHub API calls (Steps 5–9 complete)
- `app/models.py` — Pydantic models
- `app/selection.py` — file filtering + ranking (Step 8 complete)
- `app/context.py` — LLM context builder (Step 10 complete)
- `app/llm_client.py` — empty (Step 11 next)
- `app/parsing.py` — empty (Step 13)
- `Implimentation/Implimentation_plan_PRD_v1.2.2.md` — step-by-step plan (Steps 0–18)
- `PRD/PRD_GitHub_Summarizer_API_v1.2.2.md` — full PRD

## Build state
Steps 0–10 complete. Next: Step 11 (llm_client.py).

## See session_summary.md for current build state
