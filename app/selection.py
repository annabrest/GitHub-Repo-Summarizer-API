"""
File selection strategy: Filter → Prioritize → Cover → Fill

Filter:
* binary/media extensions (.png, .pdf, .zip, .so, etc.)
* generated/vendor dirs (node_modules/, dist/, build/, .venv/, vendor/, etc.)
* lock files (yarn.lock, poetry.lock, etc.)
* files > 200KB (hard cutoff)

Prioritize: README*, LICENSE, CHANGELOG*, manifests, CI/ops files (always include)

Cover: 1–2 top-scoring files per package group (monorepo-aware); up to 12 for src/lib

Fill: remaining budget filled by global score ranking
"""
from pathlib import Path
from collections import defaultdict

MAX_FILES = 25
MAX_FILE_BYTES_HARD = 200_000  # 200KB hard cutoff — skip entirely
MIN_CORE_CODE_FILES = 5
WORKFLOW_DIR = '.github/workflows'
COVERAGE_MIN_SCORE = 1.5  # skip low-signal files in coverage (AUTHORS.rst, NOTICE score ~1.0)

HARD_DEPRIORITIZED_DIRS = {"fixtures"}

DEPRIORITIZED_DIRS = {
    'tests', 'test', 'docs', 'examples', 'spec',
}

PRIORITY_PATTERNS = {
    # Python manifests
    'pyproject.toml', 'setup.py', 'setup.cfg',
    'requirements.txt', 'requirements-dev.txt',
    # Other manifests
    'package.json', 'go.mod', 'Cargo.toml',
    # Ops / CI
    'Dockerfile', 'docker-compose.yml', 'Makefile',
}
# LICENSE matched by prefix at root level (see is_priority), not exact name
# to avoid catching ext/LICENSE, docs/LICENSE, etc.
# README*, CHANGELOG*, CONTRIBUTING* matched by prefix at root level (see is_priority)

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

USEFUL_DOTFILES = {
    '.env.example', '.nvmrc', '.python-version', '.tool-versions',
}

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg',
    '.pdf', '.zip', '.tar', '.gz',
    '.woff', '.woff2', '.ttf', '.eot',
    '.pyc', '.exe', '.bin', '.so', '.dll',
    '.mp4', '.mp3', '.mov',
}

SENSITIVE_EXTENSIONS = {
    '.key', '.pem', '.crt', '.csr', '.p12', '.jks',
}

EXCLUDED_DIRS = {
    'node_modules', 'dist', 'build', '.next', 'target',
    '.venv', 'venv', '__pycache__', 'vendor',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extension(path: str) -> str:
    return Path(path).suffix.lower()

def _filename(path: str) -> str:
    return Path(path).name

def is_too_large(size: int) -> bool:
    return size > MAX_FILE_BYTES_HARD

def is_excluded_path(path: str) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.split('/'))

def is_binary(path: str) -> bool:
    return _extension(path) in BINARY_EXTENSIONS

def is_sensitive(path: str) -> bool:
    return _extension(path) in SENSITIVE_EXTENSIONS or 'fixtures' in path.split('/')

def is_useful_dotfile(path: str) -> bool:
    return Path(path).name in USEFUL_DOTFILES

def is_priority(path: str) -> bool:
    parts = path.split('/')
    # Skip files inside test/docs/examples dirs
    if any(p in DEPRIORITIZED_DIRS for p in parts[:-1]):
        return False

    name = _filename(path)
    stem = Path(path).stem.upper()

    # Exact match (manifests, ops)
    if name in PRIORITY_PATTERNS:
        return True

    # Root-level only: README*, CHANGELOG*, CONTRIBUTING*, LICENSE*
    # Prevents nested ext/LICENSE or docs/README from taking priority slots
    if stem in {'README', 'CHANGELOG', 'CONTRIBUTING', 'LICENSE'}:
        if '/' not in path:
            return True

    # CI workflows
    if WORKFLOW_DIR in path:
        return True

    return False

def score_file(path: str, size: int) -> float:
    """Higher score = more informative for LLM context."""
    score = 0.0
    p = Path(path)
    name  = p.stem.lower()
    ext   = p.suffix.lower()
    parts = p.parts

    # Boosts
    if name in IMPORTANT_NAMES:                        score += 3.0
    if parts[0] in IMPORTANT_DIRS:                     score += 3.0   # top-level src/lib = strong
    elif any(p in IMPORTANT_DIRS for p in parts):      score += 1.5   # nested = weaker
    if ext in CODE_EXTENSIONS:                         score += 1.5
    if '/' not in path:                                score += 1.0   # root-level file

    # Extra boost for core code in important dirs
    if any(part in IMPORTANT_DIRS for part in parts) and ext in CODE_EXTENSIONS:
        score += 1.5

    # Penalties
    if 'test' in parts or 'spec' in parts:             score -= 2.5
    if 'test' in name or 'spec' in name:               score -= 1.0
    if 'examples' in parts:                            score -= 4.0
    if name.startswith('_') and not name.startswith('__init__'):
        score -= 1.5
    if any(part in DEPRIORITIZED_DIRS for part in parts):
        score -= 3.0
    if any(part in HARD_DEPRIORITIZED_DIRS for part in parts):
        score -= 6.0
    if len(parts) > 5:                                 score -= 1.0
    if size > 50_000:                                  score -= 2.0

    return score

def get_package_roots(tree_entries: list[dict]) -> set[str]:
    """Detects monorepo package roots — any directory containing a manifest file."""
    roots = set()
    for e in tree_entries:
        if e.get('type') == 'blob' and Path(e['path']).name in MANIFEST_FILES:
            parent = str(Path(e['path']).parent)
            if parent != '.':
                roots.add(parent)
    return roots

def get_group(path: str, package_roots: set[str]) -> str:
    """Assigns a file to its deepest package root; falls back to top-level dir."""
    matching = [r for r in package_roots if path.startswith(r + '/')]
    if matching:
        return max(matching, key=len)
    return path.split('/')[0] if '/' in path else '.'


# ---------------------------------------------------------------------------
# Main selection
# ---------------------------------------------------------------------------

def select_files(tree_entries: list[dict]) -> list[str]:
    """Main selection function. Implements Filter → Prioritize → Cover → Fill."""

    def dedupe_preserve_order(paths: list[str]) -> list[str]:
        seen = set()
        out = []
        for p in paths:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def category(path: str) -> str:
        p = path.replace("\\", "/")
        parts = p.split("/")
        if p.startswith(WORKFLOW_DIR) or f"/{WORKFLOW_DIR}" in p:
            return "workflow"
        if p.startswith(".github/"):
            return "github_meta"
        if Path(p).name.startswith("."):
            return "dotfile"
        if parts and parts[0] in ("docs", "doc"):
            return "docs"
        if parts and parts[0] in ("examples", "example"):
            return "examples"
        if parts and parts[0] in ("test", "tests", "__tests__"):
            return "tests"
        return "other"

    # Category caps — keep low-value categories from crowding out core code
    caps = {
        "workflow":    1,   # 1 CI workflow gives enough context
        "github_meta": 1,   # CONTRIBUTING is enough
        "dotfile":     2,
        "docs":        1,
        "examples":    1,   # examples are low signal
        "tests":       0,   # tests don't help explain the project
    }
    used: dict[str, int] = defaultdict(int)

    def can_add(path: str) -> bool:
        c = category(path)
        if c in caps:
            return used[c] < caps[c]
        return True

    def add_path(acc: list[str], path: str) -> None:
        if not can_add(path):
            return
        acc.append(path)
        used[category(path)] += 1

    # ------------------------------------------------------------------
    # Step 1: Filter — remove noise
    # ------------------------------------------------------------------
    candidates = [
        e for e in tree_entries
        if e.get('type') == 'blob'
        and not is_binary(e['path'])
        and not is_sensitive(e['path'])
        and not is_excluded_path(e['path'])
        and not is_too_large(e.get('size', 0))
        and Path(e['path']).name not in LOCK_FILES
        and not (Path(e['path']).name.startswith('.') and not is_useful_dotfile(e['path']))
    ]

    # ------------------------------------------------------------------
    # Step 2: Priority files — always include (with workflow cap)
    # ------------------------------------------------------------------
    priority_all = [e for e in candidates if is_priority(e['path'])]

    workflows     = [e for e in priority_all if WORKFLOW_DIR in e['path']]
    non_workflows = [e for e in priority_all if WORKFLOW_DIR not in e['path']]

    # Pick best workflow by score, apply cap
    workflows_sorted = sorted(
        workflows,
        key=lambda e: score_file(e['path'], e.get('size', 0)),
        reverse=True,
    )[:caps["workflow"]]

    priority: list[str] = []
    for e in non_workflows:
        add_path(priority, e['path'])
    for e in workflows_sorted:
        add_path(priority, e['path'])

    selected_set = set(priority)

    # ------------------------------------------------------------------
    # Step 3: Detect package roots (monorepo support)
    # ------------------------------------------------------------------
    package_roots = get_package_roots(tree_entries)

    # ------------------------------------------------------------------
    # Step 4: Coverage — top-scoring files per group
    # ------------------------------------------------------------------
    remaining = [e for e in candidates if e['path'] not in selected_set]

    groups: dict[str, list] = defaultdict(list)
    for e in remaining:
        g = get_group(e['path'], package_roots)
        groups[g].append(e)

    coverage: list[str] = []

    for g in sorted(groups.keys()):
        entries = groups[g]
        top = sorted(
            entries,
            key=lambda e: score_file(e['path'], e.get('size', 0)),
            reverse=True,
        )
        # src/lib get more slots — they hold the core code
        per_group_limit = 12 if g in ('lib', 'src') else 2

        added = 0
        for e in top:
            if added >= per_group_limit:
                break
            p = e['path']
            if p in selected_set:
                continue
            if not can_add(p):
                continue
            # Skip low-signal files (AUTHORS.rst, NOTICE, MANIFEST.in score ~1.0)
            if score_file(p, e.get('size', 0)) < COVERAGE_MIN_SCORE:
                continue
            add_path(coverage, p)
            selected_set.add(p)
            added += 1

    result = priority + coverage

    # ------------------------------------------------------------------
    # Step 5: Enforce minimum core-code quota
    # ------------------------------------------------------------------
    def is_core_code_path(path: str) -> bool:
        if _extension(path) not in CODE_EXTENSIONS:
            return False
        if any(p in DEPRIORITIZED_DIRS for p in path.split('/')):
            return False
        return True

    core_now = [p for p in result if is_core_code_path(p)]
    if len(core_now) < MIN_CORE_CODE_FILES:
        missing_core = sorted(
            [e for e in candidates
             if e['path'] not in selected_set and is_core_code_path(e['path'])],
            key=lambda e: score_file(e['path'], e.get('size', 0)),
            reverse=True,
        )

        result_list = list(result)
        repl_idxs = [i for i, p in enumerate(result_list) if not is_core_code_path(p)]

        add_idx = 0
        for i in repl_idxs:
            if len(core_now) >= MIN_CORE_CODE_FILES or add_idx >= len(missing_core):
                break
            new_p = missing_core[add_idx]['path']
            if not can_add(new_p):
                add_idx += 1
                continue
            old_p = result_list[i]
            used[category(old_p)] -= 1
            result_list[i] = new_p
            used[category(new_p)] += 1
            selected_set.add(new_p)
            core_now.append(new_p)
            add_idx += 1

        result = result_list

    # ------------------------------------------------------------------
    # Step 6: Global fill — top remaining files by score
    # ------------------------------------------------------------------
    fill_pool = sorted(
        [e for e in candidates if e['path'] not in selected_set],
        key=lambda e: score_file(e['path'], e.get('size', 0)),
        reverse=True,
    )

    for e in fill_pool:
        if len(result) >= MAX_FILES:
            break
        p = e['path']
        if score_file(p, e.get('size', 0)) < COVERAGE_MIN_SCORE:
            break  # fill_pool is sorted desc — everything after is also below threshold
        if p in selected_set:
            continue
        if not can_add(p):
            continue
        add_path(result, p)
        selected_set.add(p)

    return dedupe_preserve_order(result)[:MAX_FILES]
