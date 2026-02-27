# Project Memory — GitHub Repo Summarizer API

## What this is
Nebius Academy admission assignment. FastAPI service: `POST /summarize` accepts GitHub URL, fetches repo via GitHub REST API (no cloning), selects informative files, builds context, calls LLM, returns structured JSON.

## User preferences
- **Show code in chat, don't edit files directly** — user writes code themselves
- Explain concepts, don't over-scaffold
- Ask before assuming on approach decisions

## Key files
- `app/main.py` — FastAPI app + all endpoints
- `app/github_client.py` — GitHub API calls
- `app/models.py` — Pydantic models
- `app/selection.py` — file filtering + ranking (Step 8 in progress)
- `Implimentation_plan_PRD_v1.2.2.md` — current implementation plan (18 steps)
- `Implimentation/Implimentation_Step8.md` — detailed Step 8 reference
- `PRD/PRD_GitHub_Summarizer_API_v1.2.2.md` — full PRD

## See session_summary.md for current build state
