# GitHub Repo Summarizer API

FastAPI service: accepts a GitHub repository URL, fetches the repo via GitHub REST API (no cloning), selects the most informative files, and returns a structured JSON summary of the project's purpose, technologies, and architecture.

---

## Table of Contents

- [Quick Start](#quick-start)
  - [Setup](#setup)
  - [Configuration](#configuration)
  - [Run](#run)
  - [Usage](#usage)
  - [Error Reference](#error-reference)
- [Architecture & Design](#architecture--design)
  - [Pipeline Overview](#pipeline-overview)
  - [File Selection Strategy](#file-selection-strategy)
  - [Scoring Formula](#scoring-formula)
  - [Context Budget](#context-budget)
  - [Map/Reduce Fallback](#mapreduce-fallback)
  - [Key Assumptions & Trade-offs](#key-assumptions--trade-offs)
  - [Known Limitations](#known-limitations)
  - [Unit Tests](#unit-tests)
  - [Reading the Logs](#reading-the-logs)

---

## Quick Start

### Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

No `uv`? Use standard venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file at the project root.

**For evaluation (Nebius):**

```
NEBIUS_API_KEY=your-nebius-key
LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3.2        # recommended
GITHUB_TOKEN=your-github-token              # optional — raises GitHub rate limit from 60 to 5000 req/hr
```

Tested Nebius models (set as `LLM_MODEL`):

| Model | Notes |
|-------|-------|
| `deepseek-ai/DeepSeek-V3.2` | Recommended — best results for code analysis |
| `meta-llama/Llama-3.3-70B-Instruct` | Good alternative, reliable JSON output |

**For local development (OpenAI):**

```
OPENAI_API_KEY=your-openai-key
# LLM_MODEL defaults to gpt-4o-mini if not set
GITHUB_TOKEN=your-github-token   # optional
```

> `NEBIUS_API_KEY` takes priority over `OPENAI_API_KEY` when both are set.
> Nebius uses the same OpenAI-compatible wire format — no SDK required.

### Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Usage

```bash
# Simple library — single-pass (all files fit in context)
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/psf/requests"}'

# Large framework — map/reduce triggered (files exceed 60k char budget)
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/django/django"}'

# Monorepo — per-group coverage active
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/vercel/next.js"}'
```

All return:

```json
{
  "summary": "...",
  "technologies": ["Python", "requests", "..."],
  "structure": "..."
}
```

### Error Reference

| Code | Meaning |
|------|---------|
| 400  | Invalid GitHub URL |
| 404  | Repository not found |
| 422  | No useful files found in repository |
| 500  | Server misconfiguration — check env vars (missing API key, or `NEBIUS_API_KEY` set without `LLM_BASE_URL`/`LLM_MODEL`) |
| 502  | LLM upstream error (timed out, unreachable, or returned 4xx/5xx) |
| 503  | GitHub API unreachable after retry |

---

## Architecture & Design

### Pipeline Overview

```
GitHub URL
  → parse owner/repo
  → GitHub REST API: repo metadata + recursive file tree
  → Filter → Prioritize → Cover → Fill   (select ≤25 files)
  → context builder (60k char budget, fetch file contents)
  → LLM: single-pass or map/reduce fallback
  → parse + validate JSON response
  → { summary, technologies, structure }
```

No cloning. All file access uses the GitHub Contents API.

---

### File Selection Strategy

The core challenge: pick the most architecturally informative files from a repo with potentially 10,000+ entries, within the LLM context budget. Selection runs in four phases (`app/selection.py`).

#### Phase 1 — Filter (remove noise)

Excluded entirely:

- Binary and media files (`.png`, `.jpg`, `.pdf`, `.zip`, `.so`, `.dll`, …)
- Lock files (`package-lock.json`, `yarn.lock`, `poetry.lock`, `Pipfile.lock`, …)
- Sensitive files (`.key`, `.pem`, `.crt`, …)
- Hidden dotfiles — *except* useful config hints: `.nvmrc`, `.python-version`, `.env.example`, `.tool-versions`
- Files larger than 200 KB
- Generated / dependency directories: `node_modules`, `dist`, `build`, `.next`, `target`, `.venv`, `vendor`, `__pycache__`

#### Phase 2 — Prioritize (always-include, with caps)

Certain files are always selected, subject to category caps that prevent any single category from crowding out source code:

| Category | Files | Cap |
|----------|-------|-----|
| Manifests (root-level only) | `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `requirements.txt` | 4 |
| Docs (root-level only) | `README*`, `CHANGELOG*`, `CONTRIBUTING*` | 1 |
| CI / Ops (any level) | `Dockerfile`, `docker-compose.yml`, `Makefile`, `.github/workflows/*` | 1 workflow |
| Tests | — | **0** |

Tests are excluded entirely: they describe what the project *should do*, not what it *does*.

The manifest cap (4) prevents monorepos with 50+ `package.json` files from flooding the selection. Root-level manifests are selected first (sorted by path depth).

#### Phase 3 — Coverage (monorepo-aware per-group selection)

- **Package root detection**: any directory containing a manifest file is treated as an independent package root.
- **Group assignment**: each file is assigned to its deepest matching package root, or to its top-level directory if no root matches.
- **Slot allocation**:
  - `src` / `lib` groups → up to **12 files** (primary implementation)
  - All other groups → up to **2 files** (avoids one sub-package dominating)
- Files scoring below `COVERAGE_MIN_SCORE = 1.5` are skipped (filters low-signal files like `AUTHORS.rst`, `NOTICE`).

#### Phase 4 — Fill

Fills remaining budget up to `MAX_FILES = 25` from the global score ranking, skipping files below `COVERAGE_MIN_SCORE`.

**Minimum core code guarantee**: if fewer than 5 code files (`.py`, `.js`, `.ts`, `.go`, etc., outside test/docs dirs) are selected, the lowest-scoring non-code files are swapped out to meet the minimum.

---

### Scoring Formula

`score_file(path, size)` produces a relative ranking score. Higher = selected first.

| Factor | Score |
|--------|-------|
| Filename in `IMPORTANT_NAMES` (main, app, index, server, routes, handler, api, cli…) | +3.0 |
| Top-level dir in `IMPORTANT_DIRS` (src, app, api, lib, core, cmd, pkg, server) | +3.0 |
| Nested `IMPORTANT_DIRS` | +1.5 |
| Code extension (.py, .js, .ts, .go, .rs, .java, .rb, .cpp, .kt, .swift…) | +1.5 |
| In `IMPORTANT_DIRS` **and** code extension (combined boost) | +1.5 extra |
| Root-level file (no `/` in path) | +1.0 |
| `test` or `spec` in any path segment | −2.5 |
| `test` or `spec` in filename | −1.0 |
| `DEPRIORITIZED_DIRS` in path (tests, docs, examples, bench, benches) | −3.0 |
| `HARD_DEPRIORITIZED_DIRS` in path (fixtures) | −6.0 |
| `examples` anywhere in path | −4.0 |
| Filename starts with `_` (except `__init__`) | −1.5 |
| Path depth > 5 | −1.0 |
| File size > 50 KB | −2.0 |

Score is used for ranking only. The absolute value doesn't gate inclusion except at the `COVERAGE_MIN_SCORE = 1.5` threshold in the coverage and fill phases.

---

### Context Budget

The entire LLM prompt is capped at **60,000 characters**.

| Component | Budget |
|-----------|--------|
| Total prompt | 60,000 chars |
| README | 12,000 chars max — smart truncation: first 6k + `...[truncated]...` + last 6k |
| Other files | 6,000 chars each |
| File tree preview | first 250 paths |

**Inclusion logic**: files are added in selection order. If the next file would push the total over budget, it is skipped (not truncated). The loop continues — a later smaller file may still fit.

**README truncation**: most READMEs front-load the project description and back-load config/contributing details. Head + tail preserves both ends while staying within budget.

**Fetch failures**: if a file cannot be fetched (network error, 404, encoding error), it is silently skipped. The summary is built from whatever context was assembled — maximising the chance of a useful response even under transient failures.

---

### Map/Reduce Fallback

**Triggered when**: `build_context()` drops at least one selected file due to budget exhaustion (`files_included < selected`).

**Why**: a single-pass summary over a truncated context may miss important parts of a large repo.

**How**:
1. Selected files are split into two halves.
2. Two `call_llm_map()` calls run **in parallel** via `asyncio.gather` — each summarises its chunk independently.
3. A `call_llm_reduce()` call synthesises the chunk summaries together with the file tree into the final output.
4. If map/reduce itself fails for any reason, the pipeline silently falls back to single-pass over the original context — best-effort rather than error.

---

### Key Assumptions & Trade-offs

- **Lock files ignored**: auto-generated, verbose, and carry no architectural signal for the LLM.
- **Tests excluded (cap = 0)**: tests explain expected behaviour, not project structure. Excluding them frees budget for source files.
- **Examples capped at 1**: example snippets are typically incomplete and don't represent the real implementation.
- **Files included whole or skipped**: no partial file inclusion. The LLM sees coherent file contents rather than truncated fragments, at the cost of potentially dropping more files.
- **No retry sleep**: GitHub retries are immediate (2 attempts). Suitable for transient errors; persistent outages surface as 503.
- **Scoring assumes conventional layout**: entry points in `src/`, `app/`, `api/`, `lib/`, `cmd/`, `core/`. Deeply nested files (depth > 5) are deprioritised. This may underweight codebases with non-standard top-level structure.

---

### Known Limitations

**Large frameworks with deep nesting (e.g. `django/django`)**
Django's core logic lives in `django/contrib/`, `django/db/`, `django/core/` etc. — all at depth 2+. The scoring bonus for top-level `IMPORTANT_DIRS` does not apply to these paths, so coverage can be uneven across the codebase. Map/reduce helps by splitting context across two LLM calls, but with 10,000+ files the synthesised summary may miss architectural nuance. A content-aware approach (e.g. import graph analysis) would improve selection but is outside the scope of a path-only heuristic.

**Non-manifest monorepos**
Package root detection relies on manifest files (`package.json`, `pyproject.toml`, etc.) being present at each package directory. Nx, Bazel, or custom workspace setups without per-package manifests may be treated as a single flat repository.

**Asset-heavy repos**
If most files are images, fonts, or binary data, the filter phase may leave fewer than `MIN_CORE_CODE_FILES = 5` code files — or return 422 if nothing passes the filter at all.

**Private repos**
Require a `GITHUB_TOKEN` with read access. Returns 403 without a valid token.

---

### Unit Tests

```bash
pytest tests/              # all tests
pytest tests/test_parsing.py  # LLM response parsing — 6 tests
```

`test_parsing.py` covers: direct JSON parse, markdown fence stripping, bracket extraction fallback, missing required keys, string-to-list coercion for `technologies`, and fully unparseable input.

---

### Reading the Logs

Single-pass request:

```
INFO:app.routes:single-pass for psf/requests: all 18 files included
INFO:app.llm_client:[single] tokens — prompt: 4210, completion: 312, total: 4522
```

Map/reduce request:

```
INFO:app.routes:map/reduce triggered for django/django: 12/25 files included
INFO:app.llm_client:[map] tokens — prompt: 3100, completion: 201, total: 3301
INFO:app.llm_client:[map] tokens — prompt: 2980, completion: 188, total: 3168
INFO:app.llm_client:[reduce] tokens — prompt: 1540, completion: 289, total: 1829
INFO:app.routes:map/reduce succeeded for django/django
```

Token counts per call let you monitor cost per request. `httpx` and `httpcore` are silenced to `WARNING` to avoid noise from individual file fetches.
