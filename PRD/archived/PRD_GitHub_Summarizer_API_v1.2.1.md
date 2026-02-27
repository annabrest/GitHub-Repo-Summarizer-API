# PRD v1.2 — GitHub Repo Summarizer API (Evaluator-Ready)

## 0) Evaluator Compatibility Requirements

The submission **must** satisfy:

* Server starts following README instructions.
* Exposes **`POST /summarize`** exactly.
* Accepts JSON body with key **`github_url`**.
* Runs on **`localhost:8000`**.
* LLM key configured via **environment variable**. For final submission, evaluator will provide **`NEBIUS_API_KEY`**.

## 1) Purpose

Build an HTTP API that takes a public GitHub repository URL and returns:

* `summary`: concise overview of purpose, features, and how it runs
* `technologies`: key languages/frameworks/tools
* `structure`: brief explanation of directory layout and main components

## 2) Goals / Success Criteria

### Blocking goals

* `POST /summarize` returns a non-error response for a valid public repo.
* LLM calls are made via **Nebius Token Factory** (or alternative provider). Final submission must support Nebius.
* No API keys hard-coded. Keys come from env vars.

### Quality goals (scoring)

* Sensible file filtering (binary/lock/vendor skipped or truncated).
* Clear strategy to select informative files.
* Context management robust for large repos (caps + truncation + optional summarization fallback).
* Prompts produce structured JSON reliably.
* Code organized and handles edge cases.

## 3) Non-goals

* Private repos (no auth flow beyond optional token)
* Executing repo code/builds
* Perfect completeness for all languages

## 4) API Spec

### Endpoint

`POST /summarize`

### Request

```json
{ "github_url": "https://github.com/psf/requests" }
```

### Response (200)

```json
{
  "summary": "…",
  "technologies": ["…"],
  "structure": "…"
}
```

### Response (error)

```json
{ "status": "error", "message": "…" }
```

**“5) Provider Strategy (Develop with OpenAI, Submit with Nebius)”**

Add this subsection:

#### 5.1 OpenAI-compatible configuration (Nebius + OpenAI)

Both providers are called via an **OpenAI-compatible HTTP API** (same client code). The provider is selected by environment variables:

**Environment variables**

* `NEBIUS_API_KEY` (submission/evaluation)
* `OPENAI_API_KEY` (local development)
* `LLM_BASE_URL` (optional override)
* `LLM_MODEL` (optional override)

**Selection rules**

1. If `NEBIUS_API_KEY` is set:

   * Provider = Nebius
   * `api_key = NEBIUS_API_KEY`
   * `base_url = LLM_BASE_URL` (must point to Nebius OpenAI-compatible endpoint; required for Nebius mode)
   * `model = LLM_MODEL` (Nebius model name; required for Nebius mode)
2. Else if `OPENAI_API_KEY` is set:

   * Provider = OpenAI
   * `api_key = OPENAI_API_KEY`
   * `base_url = LLM_BASE_URL` (optional; defaults to OpenAI base URL)
   * `model = LLM_MODEL` (optional; defaults to a sensible dev model)
3. Else:

   * return 500 `{status:"error", message:"No LLM API key configured"}`

**Rationale**

* Enables fast local iteration with OpenAI, while guaranteeing evaluators’ `NEBIUS_API_KEY` uses Nebius by configuration rather than code changes.

## 6) GitHub Repo Processing

### 6.1 Fetch strategy (no cloning)

Use GitHub REST API.

**Optional auth**

* If `GITHUB_TOKEN` is set, use it (improves reliability).

**Calls**

1. `GET /repos/{owner}/{repo}` → `default_branch`
2. `GET /repos/{owner}/{repo}/branches/{default_branch}` → commit SHA
3. `GET /repos/{owner}/{repo}/git/commits/{sha}` → tree SHA
4. `GET /repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1` → tree entries

### 6.2 Filtering rules (repo processing scoring)

Skip:

* binary/media: `png/jpg/gif/pdf/zip/tar/gz/mp4/so/dll/dylib`
* generated/vendor: `node_modules/`, `dist/`, `build/`, `.next/`, `target/`, `.venv/`, `venv/`, `__pycache__/`, `vendor/`
* extremely large files (hard cutoff): default `>200KB` (unless explicitly prioritized, then truncate)

**Lock files policy (explicit for rubric)**

* Default: **deprioritize or skip** lock files (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`).
* If included, **truncate heavily** (they’re mostly noise, but can signal ecosystem).

### 6.3 Priority include list

Try to include in this order:

1. `README*`, `CHANGELOG*`, `LICENSE`, `CONTRIBUTING*`
2. Manifests: `pyproject.toml`, `requirements*.txt`, `setup.py`, `package.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `*.csproj`
3. Ops/CI: `.github/workflows/*`, `Dockerfile`, `docker-compose.yml`, `Makefile`
4. Entry points & core dirs: `src/`, `app/`, `server/`, `api/`, `cmd/`, `lib/`, `main.*`, `app.*`, `server.*`, `index.*`

### 6.4 Ranking heuristic (avoid “largest-first”)

Score files by:

* * directory signal (`src/`, `app/`, `api/`, `server/`, etc.)
* * filename signal (`main`, `routes`, `handlers`, `controllers`, `cli`)
* * extension signal (`.py .ts .js .go .rs .java .kt .cs`)
* − test folders (deprioritize but allow)
* − size outliers (<200B or >80KB)

Select top-scoring files until budgets are met.

## 7) Context Management (large repo safety)

### 7.1 Budgets

Use char budgets (simple, reliable):

* `MAX_TOTAL_CHARS = 60_000`
* `MAX_FILES = 25`
* `MAX_FILE_CHARS = 6_000`
* `README_MAX_CHARS = 12_000`
* `MAX_TREE_LINES = 250`

### 7.2 Truncation policy (structured)

* README: **head + tail**
* Code: **head** (imports + definitions usually at top)
* Manifests/config: **head**, full if small
* If a file is too big: take first N lines + optionally last few lines for context

### 7.3 Fallback summarization (max 2 LLM calls)

Default single-pass.

Trigger fallback only when:

* After truncation you still exceed `MAX_TOTAL_CHARS` by >30%, **or**
* You cannot include at least: (README or 1 manifest) AND ≥3 meaningful code files

Fallback:

1. Map: summarize 2–4 chunks
2. Reduce: synthesize final JSON

Hard limit: **2 LLM calls total**.
If map fails → return best-effort single-pass output (don’t hard-fail).

## 8) Prompt Engineering (scoring)

### 8.1 Output schema

Model must return JSON only:

```json
{
  "summary": "string",
  "technologies": ["string"],
  "structure": "string"
}
```

### 8.2 Prompts (templates)

**System instruction**

* “Return JSON only. No markdown. No extra keys.”

**User prompt includes**

* Repo metadata (name/description)
* Directory tree (trimmed)
* Selected file excerpts (labeled)
* Clear instructions:

  * summarize purpose + key features
  * list technologies (dedupe, proper nouns)
  * describe structure (top-level components and their roles)
  * if uncertain, say so briefly instead of guessing

## 9) Output Parsing & Validation (reliability)

* Strict `json.loads`
* Fallback: strip code fences, extract first `{...}` block, retry
* Validate required keys exist:

  * If missing: set safe defaults or re-ask (avoid extra calls; prefer defaults)
* Ensure `technologies` is a list of strings (dedupe)

## 10) Error Handling

* 400 invalid URL / payload
* 404 repo not found
* 403 private repo / rate limit
* 422 no meaningful text extracted
* 502 LLM failure / unrecoverable output
* 504 timeout

All error responses:

```json
{ "status":"error", "message":"..." }
```

## 11) Observability

Per request log:

* repo
* tree entries count
* selected files count
* total chars included
* provider used (openai/nebius)
* latencies + status

Never log tokens or full file contents.

#### LLM client implementation note

Use a single OpenAI-compatible client with configurable `base_url` and `api_key` to avoid provider-specific branching. Log only `provider` (openai/nebius), not keys or raw prompts.

## 12) Repo Layout (recommended)

```
app/
  main.py
  routes.py
  models.py
  settings.py
  github_client.py
  selection.py
  context.py
  llm_client.py
  parsing.py
tests/
README.md
requirements.txt
```

## 13) Acceptance Tests

* curl example works for `psf/requests`
* invalid URL → 400
* nonexistent repo → 404
* large repo returns 200 best-effort and does not crash
* missing LLM key returns 500 with clear message

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

---

## Thoughts / consequences of your “OpenAI first, Nebius last” plan

**Pros**

* Faster dev loop and easier debugging.
* You reduce integration risk by isolating Nebius-specific changes to the provider layer.

**Cons / bottleneck**

* OpenAI and Nebius models may differ slightly in JSON compliance and verbosity.

  * Mitigation: keep prompts strict and implement JSON repair fallback.
  * Before submission, run 3–5 repos using Nebius to confirm stable output.

---

## Questions (only what I need to ensure the PRD is implementable without surprises)

1. Are you planning to use Nebius via an **OpenAI-compatible base URL** (ideal), or a distinct SDK/endpoint?
2. Which runtime do you prefer: **Python/FastAPI** (recommended for speed) or Node?

If you answer those, I can also give you a minimal `settings.py` env precedence + `llm_client.py` interface that makes the swap genuinely “one-line”.
