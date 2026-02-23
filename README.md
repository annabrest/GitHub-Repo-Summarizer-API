This is an admission assignment for Nebius Academy's AI Performance Engineering 2026 program. 

**What You're Building:**
- A Python API service with one endpoint: `POST /summarize`
- You give it a GitHub repo URL → it analyzes the repo → returns a structured summary using an LLM.

**The Core Challenge (what they're really testing):**
- The interesting problem is how you prepare the repo content before sending it to the LLM. Repos can be huge, LLMs have context limits. Your strategy for filtering, prioritizing, and fitting content into the context window is what earns most of the points.


**The outcome:** a smart research assistant tool (small program):
- Someone gives you a GitHub link
- You go "read" the repository (but smartly — not everything, just the important parts)
- You hand a summary of what you read to an AI (LLM)
- The AI writes a human-readable summary
- You return that summary as JSON

**PRD Outline suggested:**
Here's what a good PRD would cover:
1. Goal & Scope — Single endpoint API, Python, FastAPI, Nebius LLM
2. Input/Output Contract — exactly as specified (github_url in, summary/technologies/structure out)
3. Repo Ingestion Strategy (this is the key design decision):

Use GitHub API (no cloning needed) to fetch file tree and contents
Skip: binaries, lock files (package-lock.json, poetry.lock), node_modules, .git, images, build artifacts
Prioritize: README, package.json/pyproject.toml/requirements.txt, main source files, directory structure
Cap: total characters sent to LLM (e.g., 30k chars max), truncate large files

4. Context Management Strategy — build a structured prompt with: directory tree first, then key config files, then top N source files sorted by importance
5. Prompt Engineering — clear instruction to return JSON with the 3 fields
6. Error Handling — invalid URL, private repo, rate limits, LLM failures
7. README requirements — setup steps, model choice rationale, design decisions

---

# README Skeleton (Evaluator-Friendly)

## Title

GitHub Repo Summarizer API

## What this does

This service exposes `POST /summarize` which accepts a public GitHub repository URL and returns:

* a project summary
* key technologies
* a brief structure overview

## Requirements

* Python 3.10+ (or 3.11+)
* Internet access (GitHub + LLM provider)

## Setup (Step-by-step)

### 1) Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure LLM API key (choose one)

#### Option A — Development (OpenAI)

```bash
export OPENAI_API_KEY="your_openai_key"
```

#### Option B — Submission / Evaluation (Nebius)

```bash
export NEBIUS_API_KEY="your_nebius_key"
```

> Provider selection: if `NEBIUS_API_KEY` is set, the app uses Nebius; otherwise it uses OpenAI if `OPENAI_API_KEY` is set.

### 1) Replace the “Configure LLM API key” section with this (more explicit)

## Configure LLM provider

### Option A — Development (OpenAI)

```bash
export OPENAI_API_KEY="your_openai_key"
# Optional overrides:
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"   # or your preferred dev model
```

### Option B — Submission / Evaluation (Nebius)

Nebius is used via an OpenAI-compatible endpoint. Set:

```bash
export NEBIUS_API_KEY="your_nebius_key"
export LLM_BASE_URL="<<NEBIUS_OPENAI_COMPATIBLE_BASE_URL>>"
export LLM_MODEL="<<NEBIUS_MODEL_NAME>>"
```

Provider selection:

* If `NEBIUS_API_KEY` is set, the app uses Nebius.
* Otherwise, if `OPENAI_API_KEY` is set, the app uses OpenAI.

> Do not hardcode keys. The evaluator will supply `NEBIUS_API_KEY` when testing.

### 4) (Optional) Configure GitHub token (recommended)

Helps avoid GitHub rate limits during repeated runs:

```bash
export GITHUB_TOKEN="your_github_token"
```

### 5) Start the server (must be port 8000)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Test the endpoint

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/psf/requests"}'
```

Expected response format:

```json
{
  "summary": "...",
  "technologies": ["..."],
  "structure": "..."
}
```

## Design decisions (brief)

* **Repo processing:** fetches GitHub tree via REST API (no cloning) and selects informative files (README/manifests/CI/entry points).
* **Filtering:** skips binaries and build/vendor directories; lock files are skipped or truncated.
* **Context management:** strict char budgets + structured truncation; uses a max-2-call fallback summarization for large repos.
* **Prompting:** forces JSON-only output with a fixed schema; includes repo tree + key file excerpts.
* **Reliability:** optional `GITHUB_TOKEN`, timeouts, and JSON output repair fallback.

## Error handling

* 400 invalid URL
* 404 repo not found
* 403 private repo / GitHub rate limit
* 502 LLM failure
* 504 timeout

## Project structure

(brief tree of your codebase)

## Development notes

* Default provider is OpenAI for local dev if `OPENAI_API_KEY` is set.
* Set `NEBIUS_API_KEY` to switch to Nebius before submission and verify output formatting.

## Pre-submission checklist

* [ ] Start server on port 8000: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
* [ ] `POST /summarize` works with the evaluator curl example
* [ ] Confirm Nebius mode works:

  * [ ] `NEBIUS_API_KEY` set
  * [ ] `LLM_BASE_URL` points to Nebius OpenAI-compatible endpoint
  * [ ] `LLM_MODEL` is a valid Nebius model name
* [ ] No keys are hardcoded; logs do not print tokens

---
