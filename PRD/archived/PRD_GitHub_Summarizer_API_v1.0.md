# PRD — GitHub Repository Summarizer API

PRODUCT REQUIREMENTS DOCUMENT

GitHub Repository Summarizer API

Nebius Academy — AI Performance Engineering 2026

Admission Assignment

Version 1.0  |  February 2026

# 1. Project Overview

This document defines the requirements, design decisions, and implementation strategy for a GitHub Repository Summarizer API. The service accepts a public GitHub repository URL and returns a structured, human-readable summary of the project using a Large Language Model (LLM).


| Field | Details |
| --- | --- |
| Goal | Build a working API that intelligently summarizes any public GitHub repository using an LLM |
| Language | Python 3.10+ |
| Web Framework | FastAPI (recommended for speed and auto-generated docs) |
| LLM Provider | Nebius Token Factory (primary) — OpenAI-compatible API format |
| Model Choice | meta-llama/Meta-Llama-3.1-70B-Instruct or similar from Nebius catalog |
| API Key Config | Via environment variable: NEBIUS_API_KEY (never hardcoded) |
| Deliverables | Source code, requirements.txt, README.md, submitted as .zip |


# 2. API Endpoint Specification

## 2.1  POST /summarize

This is the only required endpoint. It takes a GitHub URL, fetches and processes the repository, and returns an LLM-generated summary.

### Request Body

{

"github_url": "https://github.com/psf/requests"

}

### Success Response (HTTP 200)

{

"summary": "Requests is a popular Python library for making HTTP requests...",

"technologies": ["Python", "urllib3", "certifi"],

"structure": "Standard Python package layout with source in src/requests/..."

}

### Error Response

{

"status": "error",

"message": "Repository not found or is private"

}

⚠️  The response must always contain all 3 fields: summary, technologies, and structure. Missing fields will cause evaluation failure.

# 3. Repository Ingestion & Filtering Strategy

This is the most critical design decision in the project. Repositories can be very large — we cannot send everything to the LLM. The strategy below ensures we send the most informative content within context limits.

## 3.1  How to Access Repository Content

We use the GitHub REST API (no authentication required for public repos). This avoids downloading/cloning the repo entirely.

# Get file tree (all files recursively)

GET https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1

# Get individual file content

GET https://api.github.com/repos/{owner}/{repo}/contents/{path}

💡 The GitHub API returns file content as base64-encoded strings. You must decode them before processing. Also, anonymous API calls are rate-limited to 60 requests/hour — enough for this task.

## 3.2  File Filtering Rules

The table below defines what to include and exclude, and why. Getting this right is worth 20 points in the scoring rubric.


| Decision | File Types / Patterns | Reason |
| --- | --- | --- |
| ✅ ALWAYS Include | README.md, README.rst, README.txt | Highest-signal file. Written to explain the project to humans. |
| ✅ ALWAYS Include | pyproject.toml, package.json, Cargo.toml, go.mod, pom.xml | Reveals project name, version, dependencies, and language ecosystem. |
| ✅ ALWAYS Include | requirements.txt, setup.py, setup.cfg, Pipfile, Gemfile | Lists direct dependencies — key for identifying technologies. |
| 🔶 Include (limited) | .py, .js, .ts, .go, .rs, .java, .rb, .cs files | Include top N files (e.g. 10) sorted by size descending. Truncate each at ~2000 chars. |
| ❌ SKIP | package-lock.json, poetry.lock, yarn.lock, Pipfile.lock | Lock files are auto-generated, massive, and contain zero semantic information. |
| ❌ SKIP | .png, .jpg, .gif, .svg, .ico, .woff, .ttf, .pdf, .mp4 | Binary files — unreadable as text and add no value to LLM context. |
| ❌ SKIP | node_modules/, .git/, dist/, build/, __pycache__/, .venv/ | Generated/dependency folders that can contain thousands of files. |
| ❌ SKIP | .min.js, .min.css, .map files | Minified/compiled output files. Not human-readable source code. |


# 4. Context Management Strategy

LLMs have a 'context window' — a maximum amount of text they can process at once. Think of it like a notepad with a fixed number of lines. If we try to send too much, the API will return an error. Our strategy keeps context lean while maximizing information quality.

## 4.1  Context Budget (30,000 character cap)

📏 30,000 characters ≈ ~7,500 tokens, well within most modern LLMs' limits while leaving room for the system prompt and output.


| Content Type | Budget | Strategy |
| --- | --- | --- |
| Directory tree | ~2,000 chars | Always include. Shows structure cheaply. Truncate at 150 paths. |
| README + config files | ~8,000 chars | Always include. Truncate README at 5,000 chars if very long. Include all config files in full. |
| Source code files | ~20,000 chars | Sort by file size (largest first). Include top N files until budget is consumed. Truncate each file at 2,000 chars. |
| TOTAL LIMIT | 30,000 chars | Track a running character count. Stop adding files when limit is reached. |


## 4.2  File Prioritization Logic (Pseudocode)

def build_context(repo_files):

budget = 30000

context = []

used = 0

# Step 1: Always add directory tree first

tree = build_tree(repo_files)[:150 lines]

context.append(f'## Directory Structure\n{tree}')

used += len(tree)

# Step 2: Always add README and config files

for f in PRIORITY_FILES:  # README, pyproject.toml, etc.

content = truncate(f.content, 5000)

if used + len(content) < budget:

context.append(f'## {f.path}\n{content}')

used += len(content)

# Step 3: Add source files sorted by size (biggest = most code)

source_files = sort_by_size(filter_source_files(repo_files))

for f in source_files:

content = truncate(f.content, 2000)

if used + len(content) >= budget:

break

context.append(f'## {f.path}\n{content}')

used += len(content)

return '\n\n'.join(context)

# 5. LLM Prompt Engineering

A well-crafted prompt is the difference between a generic response and a structured, accurate one. This section defines exactly what to send to the LLM and why each part matters.

## 5.1  System Prompt

💡 The system prompt sets the LLM's role and output format. Be explicit — tell it exactly what JSON to return.

SYSTEM_PROMPT = """

You are a senior software engineer who specializes in analyzing

code repositories. Your job is to produce clear, accurate summaries

of GitHub projects for developers who are evaluating them.

You will receive partial content from a repository (file tree,

README, configuration files, and source code samples).

Respond ONLY with valid JSON in this exact format:

{

"summary": "2-3 sentence description of what the project does",

"technologies": ["list", "of", "main", "technologies"],

"structure": "1-2 sentence description of project layout"

}

Do not include any text outside the JSON object.

Do not make up information not present in the provided content.

"""

## 5.2  User Prompt Template

USER_PROMPT = f"""

Please analyze this GitHub repository: {repo_url}

Here is the content I was able to extract:

{context}

Based on the above, return the JSON summary as instructed.

"""

## 5.3  Parsing the LLM Response

LLMs sometimes wrap JSON in markdown code blocks (```json ... ```). Always strip these before parsing:

import json, re

def parse_llm_response(text: str) -> dict:

# Strip markdown code fences if present

text = re.sub(r'```json|```', '', text).strip()

return json.loads(text)

# 6. Error Handling & Edge Cases

Good error handling is worth 20 points. The table below maps every important failure scenario to the correct HTTP response.


| Scenario | HTTP Status | Error Message Example |
| --- | --- | --- |
| github_url is missing from request body | 422 | "message": "Field github_url is required" |
| URL is not a valid GitHub URL | 400 | "message": "Invalid GitHub repository URL" |
| Repository does not exist (404 from GitHub) | 404 | "message": "Repository not found" |
| Repository is private | 403 | "message": "Repository is private or inaccessible" |
| Repository is empty (no files) | 422 | "message": "Repository appears to be empty" |
| GitHub API rate limit exceeded | 503 | "message": "GitHub API rate limit reached. Try again later." |
| LLM API is down or returns error | 502 | "message": "LLM service unavailable. Try again later." |
| LLM returns invalid JSON | 500 | "message": "Failed to parse LLM response" |
| Network timeout | 504 | "message": "Request timed out while fetching repository" |


# 7. Recommended Code Structure

Keep the code organized from the start — even for a small project. This makes it easier to debug and shows evaluators you think in systems.

repo-summarizer/

├── main.py              # FastAPI app, /summarize endpoint

├── github_client.py     # GitHub API calls (fetch tree, file content)

├── repo_filter.py       # File filtering and selection logic

├── context_builder.py   # Assemble context string within budget

├── llm_client.py        # LLM API calls (Nebius/OpenAI)

├── prompt_templates.py  # System and user prompt strings

├── models.py            # Pydantic models for request/response

├── requirements.txt

└── README.md

👍 Splitting the code into these files shows good engineering judgment — even if each file is small. It also makes debugging much easier since each file has one clear job.

# 8. README Requirements

The README is worth 10 points and is also critical for the blocking evaluation criteria — if evaluators can't run your code from the README, you get 0 points.

## 8.1  Required README Sections

1. Setup Instructions

git clone or unzip the archive

cd into the project directory

pip install -r requirements.txt

export NEBIUS_API_KEY=your_key_here

uvicorn main:app --reload

2. Testing the Endpoint

Include the exact curl command from the assignment

Show an example response

3. Model Choice & Rationale

1-2 sentences: which model from Nebius and why (e.g., context length, speed, cost)

4. Repo Processing Approach

What files you include and skip, and why

How you handle large repos

Your context budget strategy

# 9. Scoring Rubric & Self-Assessment


| Criteria | Points | Key Actions to Score Full Points |
| --- | --- | --- |
| Functionality | 20 | Return accurate summary, technologies, structure for multiple repos. Match JSON format exactly. |
| Repo Processing | 20 | Implement file filtering (skip binaries, lock files, node_modules). Prioritize README and config files. |
| Context Management | 20 | Enforce character budget. Handle large repos without crashing. Use truncation + prioritization. |
| Prompt Engineering | 10 | Use a clear system prompt. Instruct LLM to output only JSON. Handle markdown code fence stripping. |
| Code Quality & Error Handling | 20 | Handle all error cases (invalid URL, private repo, empty repo, API failures). No hardcoded keys. |
| Documentation | 10 | README with setup steps, model rationale, processing approach. Must run on a clean machine. |
| TOTAL | 100 | A clean, working, thoughtful solution wins. Don't over-engineer. |


# 10. Recommended Implementation Order

🚀 Build in this order — each step gives you something testable. Don't try to build everything at once.

Step 1 — Set up FastAPI project and create the /summarize endpoint skeleton (returns hardcoded JSON)

Step 2 — Add GitHub API integration — fetch file tree and test it works for a real repo

Step 3 — Implement file filtering — skip binaries, lock files, bad directories

Step 4 — Build context assembler — assemble text within the 30,000 character budget

Step 5 — Add LLM call (Nebius or OpenAI) with system + user prompt, parse response

Step 6 — Add all error handling cases from Section 6

Step 7 — Write the README. Test the full flow with 3-4 different repos

Step 8 — Package as zip and submit

Good luck! The key insight of this assignment is that thoughtful content selection beats brute-force inclusion. Quality of what you send to the LLM matters more than quantity.

