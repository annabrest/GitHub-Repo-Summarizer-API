# Step 8 — Detailed Implementation Reference

**Strategy:** Filter → Prioritize → Cover → Fill
**File:** `app/selection.py`
**PRD ref:** v1.2.2 section 6.2

---

## Constants

Add to `app/selection.py`:

```python
from pathlib import Path
from collections import defaultdict

MAX_FILES = 25
MAX_FILE_BYTES_HARD = 200_000  # 200KB hard cutoff — skip entirely

PRIORITY_PATTERNS = {
    # Docs
    'LICENSE',
    # Python manifests
    'pyproject.toml', 'setup.py', 'setup.cfg',
    'requirements.txt', 'requirements-dev.txt',
    # Other manifests
    'package.json', 'go.mod', 'Cargo.toml',
    # Ops / CI
    'Dockerfile', 'docker-compose.yml', 'Makefile',
}
# README*, CHANGELOG*, CONTRIBUTING* matched by prefix (see is_priority)

MANIFEST_FILES = {
    'pyproject.toml', 'package.json', 'go.mod',
    'Cargo.toml', 'setup.py', 'setup.cfg',
}

LOCK_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'poetry.lock', 'Pipfile.lock',
}

CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.go', '.rs', '.java',
    '.rb', '.cpp', '.c', '.cs', '.kt', '.swift',
}

IMPORTANT_NAMES = {
    'main', 'app', 'index', 'server', 'cli',
    'routes', 'handler', 'handlers',
    'controller', 'controllers', 'api',
}

IMPORTANT_DIRS = {
    'src', 'app', 'api', 'lib', 'server',
    'cmd', 'core', 'pkg',
}
```

---

## Functions

### `is_too_large(size: int) -> bool`

Hard cutoff — skip files over 200KB entirely.

```python
def is_too_large(size: int) -> bool:
    return size > MAX_FILE_BYTES_HARD
```

---

### `is_priority(path: str) -> bool`

Returns True for docs, manifests, and CI/ops files.

```python
def is_priority(path: str) -> bool:
    name = Path(path).name
    stem = Path(path).stem.upper()

    # Exact match
    if name in PRIORITY_PATTERNS:
        return True

    # Prefix match: README*, CHANGELOG*, CONTRIBUTING*, LICENSE*
    if stem in {'README', 'CHANGELOG', 'CONTRIBUTING', 'LICENSE'}:
        return True

    # CI workflows directory
    if '.github/workflows' in path:
        return True

    return False
```

---

### `score_file(path: str, size: int) -> float`

Returns a score — higher = more informative. No single right set of values; these are reasonable defaults.

```python
def score_file(path: str, size: int) -> float:
    score = 0.0
    name  = Path(path).stem.lower()       # filename without extension
    fname = Path(path).name               # full filename
    ext   = Path(path).suffix.lower()     # extension
    parts = path.split('/')               # all path segments

    # Boosts
    if name in IMPORTANT_NAMES:                         score += 3.0
    if any(p in IMPORTANT_DIRS for p in parts):         score += 2.0
    if ext in CODE_EXTENSIONS:                          score += 1.5
    if '/' not in path:                                 score += 1.0  # root-level file

    # Penalties
    if fname in LOCK_FILES:                             score -= 5.0
    if 'test' in parts or 'spec' in parts:              score -= 1.5  # test directory
    if 'test' in name or 'spec' in name:                score -= 1.0  # test filename
    if len(parts) > 5:                                  score -= 1.0  # extreme nesting
    if size > 50_000:                                   score -= 2.0  # large file

    return score
```

---

### `get_package_roots(tree_entries: list[dict]) -> set[str]`

Detects monorepo package roots — any directory containing a manifest file.

```python
def get_package_roots(tree_entries: list[dict]) -> set[str]:
    roots = set()
    for entry in tree_entries:
        if entry.get('type') == 'blob' and Path(entry['path']).name in MANIFEST_FILES:
            parent = str(Path(entry['path']).parent)
            if parent != '.':
                roots.add(parent)
    return roots
```

---

### `get_group(path: str, package_roots: set[str]) -> str`

Assigns a file to its deepest package root. Falls back to top-level directory.

```python
def get_group(path: str, package_roots: set[str]) -> str:
    # Find deepest matching package root
    matching = [r for r in package_roots if path.startswith(r + '/')]
    if matching:
        return max(matching, key=len)
    # Fallback: top-level directory, or '.' for root-level files
    return path.split('/')[0] if '/' in path else '.'
```

---

### `select_files(tree_entries: list[dict]) -> list[str]`

Main selection function. Implements the full strategy.

```python
def select_files(tree_entries: list[dict]) -> list[str]:
    # Step 1: Filter — blobs only, not binary, not excluded dir, not too large
    candidates = [
        e for e in tree_entries
        if e.get('type') == 'blob'
        and not is_binary(e['path'])
        and not is_excluded_path(e['path'])
        and not is_too_large(e.get('size', 0))
    ]

    # Step 2: Priority files (always include)
    priority = [e['path'] for e in candidates if is_priority(e['path'])]
    remaining = [e for e in candidates if not is_priority(e['path'])]

    # Step 3: Detect package roots for monorepo grouping
    package_roots = get_package_roots(tree_entries)

    # Step 4: Coverage — 1-2 top-scoring files per group
    groups = defaultdict(list)
    for e in remaining:
        g = get_group(e['path'], package_roots)
        groups[g].append(e)

    coverage = []
    for g, entries in groups.items():
        top = sorted(
            entries,
            key=lambda e: score_file(e['path'], e.get('size', 0)),
            reverse=True
        )
        coverage.extend(e['path'] for e in top[:2])

    # Step 5: Global fill — remaining slots by score
    already = set(priority) | set(coverage)
    fill_pool = sorted(
        [e for e in remaining if e['path'] not in already],
        key=lambda e: score_file(e['path'], e.get('size', 0)),
        reverse=True
    )

    result = priority + coverage
    for e in fill_pool:
        if len(result) >= MAX_FILES:
            break
        result.append(e['path'])

    return result[:MAX_FILES]
```

---

## Debug endpoint (add to `app/main.py`)

```python
from app.github_client import get_repo, get_default_branch_sha, get_tree_sha, get_recursive_tree
from app.selection import select_files

@app.get("/debug/selection")
async def debug_selection(owner: str, repo: str):
    repo_info  = get_repo(owner, repo)
    branch     = repo_info["default_branch"]
    commit_sha = get_default_branch_sha(owner, repo, branch)
    tree_sha   = get_tree_sha(owner, repo, commit_sha)
    tree       = get_recursive_tree(owner, repo, tree_sha)
    selected   = select_files(tree)
    return {"count": len(selected), "files": selected}
```

---

## Test

```bash
# Python repo
curl -s "http://localhost:8000/debug/selection?owner=psf&repo=requests" | python3 -m json.tool

# JS repo
curl -s "http://localhost:8000/debug/selection?owner=expressjs&repo=express" | python3 -m json.tool
```

**Expected for both:**
- README present
- Manifest file present (pyproject.toml / package.json)
- Source code files from src/ or lib/
- No .png, .lock, or node_modules entries
- Count ≤ 25
