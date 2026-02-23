# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Nebius Academy admission assignment. A Python FastAPI service with one endpoint `POST /summarize`: accepts a GitHub repo URL, fetches the repo via GitHub REST API (no cloning), selects the most informative files, builds a context-limited prompt, calls an LLM, and returns structured JSON.

**What earns points:** the repo ingestion + context management strategy (filtering, prioritizing, fitting content into the LLM context window).

## Environment variables

Stored in `.env` (gitignored — never commit). Load with `python-dotenv` or export manually.

```
OPENAI_API_KEY=       # dev/testing
NEBIUS_API_KEY=       # submission — takes priority over OpenAI
LLM_BASE_URL=         # required when using Nebius
LLM_MODEL=            # required when using Nebius
GITHUB_TOKEN=         # optional but recommended to avoid rate limits
```

Provider selection logic: if `NEBIUS_API_KEY` is set → use Nebius. Else if `OPENAI_API_KEY` → use OpenAI.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run server (port 8000 is a hard requirement)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Test the endpoint
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/psf/requests"}'

# Run tests
pytest tests/
pytest tests/test_parsing.py   # single test file
```

## Implementation plan

See `Implimentation_plan_PRD_v1.2.1` for the full step-by-step build plan (Steps 0–18).
