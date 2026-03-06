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

**File selection logic (monorepo-aware, rubric-aligned)**

The service selects files using a filter → prioritize → cover → fill strategy to maximize signal within strict context limits and to handle both single-package repos and monorepos.

**Filter (skip noise)**:

1. Skip binary/media files by extension (e.g., .png, .pdf, .zip, .mp4, .so, .dll).

2. Skip generated/vendor/build directories (e.g., node_modules/, dist/, build/, .venv/, target/, vendor/).

3. Apply a hard size cutoff (e.g., >200KB) to avoid huge blobs.

4. Treat lock files (yarn.lock, package-lock.json, pnpm-lock.yaml, poetry.lock) as low-signal noise: skip in normal selection; optionally include at most one (heavily truncated) only as an ecosystem hint.

**Prioritize (always include if present)**:

1. Documentation: README*, LICENSE, CHANGELOG*, CONTRIBUTING*

2. Manifests: pyproject.toml, requirements*.txt, setup.py, package.json, go.mod, Cargo.toml, etc.

3. Ops/CI: .github/workflows/*, Dockerfile, docker-compose.yml, Makefile

**Detect package roots (monorepo support)**:

A “package root” is any directory containing a manifest (e.g., packages/foo/package.json, apps/bar/pyproject.toml).

Each file is assigned to the deepest matching package root; if none, it’s assigned to its top-level directory.

**Coverage-first selection**:

After priority files, select 1–2 top-scoring code files per group (package root / top-level folder) to ensure broad coverage across components.

**Global fill**:

If budget remains, add the next highest-scoring files globally until MAX_FILES.

**Scoring (within group)**:
1. Files are scored with simple heuristics favoring entry points and wiring:

2. Boosts for filenames like main, index, app, server, cli, routes, handlers, controllers, api

3. Boosts for common code extensions (.py, .ts, .js, .go, .rs, .java, etc.)

4. Mild penalties for tests/spec files and extreme nesting/size outliers
This yields a clear, explainable strategy and avoids monorepo summaries being dominated by a single package.


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