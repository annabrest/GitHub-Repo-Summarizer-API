Below is a **novice-friendly, step-by-step implementation plan** with **small steps**, what to build, why, and **how to test each step**. It’s written so you can implement in ~7 hours, but still learn what’s going on.

---

## Implementation plan (step-by-step, test at every step)

### Step 0 — Create the project skeleton

**Goal:** Have a clean folder structure so you don’t get lost.

**Do:**

1. Create a folder, e.g. `repo-summarizer/`
2. Add:

```
repo-summarizer/
  app/
    __init__.py
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
  requirements.txt
  README.md
```

**Why:** Keeping responsibilities separate makes debugging easier.

**Test:** none yet (just structure).

---

### Step 1 — Create a virtual environment + install FastAPI

**Goal:** Run a “hello world” API.

**Do:**

1. Create venv:

   * `python -m venv .venv`
   * `source .venv/bin/activate`
2. Put in `requirements.txt`:

   * `fastapi`
   * `uvicorn[standard]`
3. Install:

   * `pip install -r requirements.txt`

**Test:**

* `python -c "import fastapi; print('ok')"`

---

### Step 2 — Start a minimal FastAPI server (no business logic)

**Goal:** Confirm server starts on **port 8000** (blocking criterion).

**Do:** in `app/main.py`

* Create FastAPI app
* Add a simple health endpoint `/health`

**Test:**

1. Run:

   * `uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. In another terminal:

   * `curl http://localhost:8000/health`
     Expected: `{"status":"ok"}`

**Why:** Proves your environment and server wiring works before adding complexity.

---

### Step 3 — Define request/response models (Pydantic)

**Goal:** Lock the exact request format the evaluator uses: `{ "github_url": "..." }`

**Do:** in `app/models.py`

* `SummarizeRequest(github_url: str)`
* `SummarizeResponse(summary: str, technologies: list[str], structure: str)`
* `ErrorResponse(status: str="error", message: str)`

**Test:**

* Add a temporary endpoint `/echo` that returns the parsed request.
* Curl:

```bash
curl -X POST http://localhost:8000/echo \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/psf/requests"}'
```

Expected: it returns the same URL.

**Why:** Stops you from accidentally using different field names and failing blocking tests.

---

### Step 4 — Create the `/summarize` endpoint (stub)

**Goal:** Endpoint exists and returns correct JSON shape even before LLM logic.

**Do:** in `app/routes.py`

* Define `POST /summarize`
* Return hardcoded response:

```json
{"summary":"stub","technologies":["stub"],"structure":"stub"}
```

Wire routes in `app/main.py`.

**Test (matches evaluator curl):**

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/psf/requests"}'
```

Expected: returns your stub JSON with required keys.

**Why:** You already satisfy 2 of the blocking criteria early.

---

### Step 5 — Parse and validate GitHub URLs

**Goal:** Don’t break on weird input; return clean 400 errors.

**Do:** add a helper function in `github_client.py` or `routes.py`:

* Accept full URL
* Extract owner/repo using regex
* Reject non-github URLs or missing parts

**Test:**

1. Valid:

   * `https://github.com/psf/requests`
2. Invalid:

   * `https://google.com/psf/requests` → 400
   * `https://github.com/psf` → 400

**Why:** This is easy points in “error handling”.

---

### Step 6 — Implement GitHub API calls (repo metadata only)

**Goal:** Confirm you can call GitHub API and get default branch.

**Do:** in `app/github_client.py`

* Use `httpx` (add to requirements):

  * `httpx`
* Implement:

  * `get_repo(owner, repo) -> {default_branch, description, ...}`

Support optional token:

* read `GITHUB_TOKEN` from env
* if present, add `Authorization: Bearer ...`

**Test:**

* Add a temporary endpoint `/debug/repo` to return repo metadata.
* Call for `psf/requests`.
  Expected: JSON includes `default_branch`.

**Why:** Verifies networking + rate limit strategy.

---

### Step 7 — Fetch the repo tree correctly (no HEAD shortcut)

**Goal:** Get all file paths + sizes so you can select files.

**Do:** implement in `github_client.py`:

1. `get_default_branch_sha(owner, repo, default_branch)`

   * `GET /repos/{owner}/{repo}/branches/{branch}` → commit sha
2. `get_tree_sha(owner, repo, commit_sha)`

   * `GET /repos/{owner}/{repo}/git/commits/{commit_sha}` → tree sha
3. `get_recursive_tree(owner, repo, tree_sha)`

   * `GET /repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1`

Return a list of entries: `{path, type, size, sha}`

**Test:**

* Temporary endpoint `/debug/tree?repo=psf/requests` returns:

  * count of files
  * first 20 file paths
    Expected: lots of entries.

**Why:** This is the foundation for repo processing scoring.

---

### Step 8 — Implement file filtering + ranking (selection.py)

**Goal:** Pick “most informative files” and skip junk.

**Do:** in `app/selection.py`

* `is_binary(path)`: by extension list
* `is_excluded_path(path)`: node_modules, dist, build, vendor, etc.
* Lock files: deprioritize/skip
* `score_file(path, size)` based on:

  * src/app/api/server/cmd/lib directories
  * main/routes/handlers/controllers names
  * code extensions
  * penalize size outliers

Then implement:

* `select_files(tree_entries) -> list[str]` that:

  * always includes priority files if present
  * fills remaining slots by score
  * respects `MAX_FILES` cap

**Test:**

* Temporary endpoint `/debug/selection`

  * returns selected file list
* Run on 2 repos:

  * `psf/requests` (python)
  * a JS repo (any popular one)
    Expected:
* includes README + requirements/pyproject or package.json if present
* includes src/ files

**Why:** This is the difference between “generic summary” and “good summary”.

---

### Step 9 — Fetch file contents safely (github_client.py)

**Goal:** Get text content for selected files without blowing up.

**Do:**
Implement `get_file_content(owner, repo, path, ref)` using:

* `GET /repos/{owner}/{repo}/contents/{path}?ref={branch}`
* base64 decode
* return text (best effort)
* if file too big: return truncated content

Add:

* `MAX_FILE_BYTES_HARD` (e.g., 200KB) skip or truncate
* if decode fails: treat as binary, skip

**Test:**

* Temporary endpoint `/debug/file?path=README.md` returns first 500 chars
* Check that README reads correctly

**Why:** Content retrieval is where rate limits and failures happen.

---

### Step 10 — Build the “context package” (context.py)

**Goal:** Assemble the LLM input with budgets.

**Do:** in `app/context.py`

* Build:

  * Repo header (name/desc/branch)
  * Tree preview (first N lines)
  * Sections per file: `=== path ===` then truncated snippet
* Enforce budgets:

  * `MAX_TOTAL_CHARS`
  * `README_MAX_CHARS` head+tail
  * `MAX_FILE_CHARS`

Return a single string to send to LLM, plus stats (chars used, files included).

**Test:**

* Temporary endpoint `/debug/context` returns:

  * `total_chars`
  * list of included files
  * first 1000 chars of the context
    Expected:
* under 60k chars
* readable structured content

**Why:** Prevents crashes + makes prompt reliable.

---

### Step 11 — Implement OpenAI-compatible LLM client (llm_client.py)

**Goal:** Make one function that can call either OpenAI or Nebius later.

**Do:**
Add requirements:

* `openai` (the official OpenAI Python SDK supports base_url overrides in modern versions)
  OR use raw `httpx` to call `/chat/completions` (more explicit, less magic).

Implement config precedence:

* if `NEBIUS_API_KEY` exists: use it + require `LLM_BASE_URL` and `LLM_MODEL`
* else if `OPENAI_API_KEY` exists: use it + default OpenAI base url/model
* else error

**Test (dev with OpenAI):**

* Add a temporary endpoint `/debug/llm` that sends a tiny prompt and returns response
* Ensure it works before integrating repo context

**Why:** Isolating provider logic makes “swap to Nebius late” safe.

---

### Step 12 — Add prompts (single-pass)

**Goal:** Make output structured and consistently JSON.

**Do:** in `llm_client.py` or a separate `prompts.py`

* System message: “Return JSON only; no markdown; schema required”
* User message: include context and instructions

**Test:**

* Use a tiny fake context first:

  * confirm JSON output
* Then use real repo context (psf/requests):

  * run and inspect output

**Why:** Prompt engineering is 10 points.

---

### Step 13 — Implement JSON parsing + repair fallback (parsing.py)

**Goal:** Avoid failing because model returns slightly invalid JSON.

**Do:**

* Try `json.loads`
* If fails:

  * strip ``` fences
  * extract first `{...}` block (simple bracket matching)
  * try again
* Validate required keys exist; ensure technologies list

**Test:**

* Unit test with:

  * valid JSON
  * JSON inside fences
  * JSON preceded by text
    Expected: parser returns structured dict or controlled error.

**Why:** This is a major “pass reliably” lever.

---

### Step 14 — Wire the real `/summarize` pipeline end-to-end

**Goal:** Replace stub endpoint with real flow.

**Do:** in `routes.py` `POST /summarize`:

1. Parse owner/repo
2. Fetch repo metadata + tree
3. Select files
4. Fetch content
5. Build context
6. Call LLM (single-pass)
7. Parse output
8. Return response

**Test:**

* Run evaluator curl:

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url":"https://github.com/psf/requests"}'
```

Expected: meaningful response with correct format.

---

### Step 15 — Add fallback map→reduce (max 2 calls)

**Goal:** Handle large repos without crashing or losing signal.

**Do:**
In `routes.py` (or orchestrator module):

* After building context, check:

  * “do we have README or manifest + 3 code files?”
  * “did we exceed budget too much?”
    If yes:

1. Build 2–4 chunk contexts
2. Call LLM to summarize each chunk (map)
3. Build final reduce context and call LLM once
4. Parse final JSON

If map fails: fallback to single-pass output.

**Test:**

* Try a larger repo (any big one) and confirm:

  * doesn’t crash
  * returns a response
  * logs show fallback triggered

**Why:** This is directly aligned with “context management” scoring.

---

### Step 16 — Harden errors + timeouts

**Goal:** Don’t hang; return controlled errors.

**Do:**

* Set `httpx.Timeout` for GitHub calls
* Add 1 retry for transient network errors
* Handle:

  * 404 repo
  * 403 private/rate limit
  * empty selection → 422
  * missing API key → 500
  * LLM errors → 502

**Test:**

* invalid URL → 400
* private repo → 403
* missing key (unset env vars) → 500
* nonexistent repo → 404

---

### Step 17 — Write README (blocking + documentation points)

**Goal:** Evaluator can follow steps and succeed.

**Do:**

* Use the README skeleton we drafted
* Include:

  * install
  * set `OPENAI_API_KEY` (dev)
  * set `NEBIUS_API_KEY + LLM_BASE_URL + LLM_MODEL` (submission)
  * run server on 8000
  * exact curl command

**Test:** follow README from scratch in a new terminal.

---

### Step 18 — Final swap to Nebius (late-stage)

**Goal:** Ensure evaluator env works.

**Do:**

* Set:

  * `NEBIUS_API_KEY`
  * `LLM_BASE_URL` (Nebius OpenAI-compatible)
  * `LLM_MODEL` (Nebius model)
* Run the same curl tests on 2–3 repos.

**Test:**

* Confirm responses are valid JSON with required keys.
* Confirm the server still runs on 8000.

---

## Bottlenecks + practical tips (so you don’t get stuck)

### Bottleneck 1: GitHub rate limits

* Optional `GITHUB_TOKEN` makes local testing smoother.
* Keep content fetch count low (<= 25 files).

### Bottleneck 2: Context budget

* The structured truncation (README head+tail, code head) is key.
* Don’t over-include tests or lock files.

### Bottleneck 3: JSON formatting

* Strict prompt + repair fallback avoids most failures.

### Bottleneck 4: Provider swap differences

* Some models are more verbose; keep “JSON only” very explicit.
* Validate and repair output rather than trusting it.

---
