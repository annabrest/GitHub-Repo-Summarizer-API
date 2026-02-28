"""

Skip: filtering rules

* binary/media: `png/jpg/gif/pdf/zip/tar/gz/mp4/so/dll/dylib`
* generated/vendor: `node_modules/`, `dist/`, `build/`, `.next/`, `target/`, `.venv/`, `venv/`, `__pycache__/`, `vendor/`
* extremely large files (hard cutoff): default `>200KB` (unless explicitly prioritized, then truncate)
MAX_FILES = 25, 
MAX_FILE_BYTES_HARD = 200_000
PRIORITY_PATTERNS, LOCK_FILES, CODE_EXTENSIONS, IMPORTANT_NAMES, IMPORTANT_DIRS, MANIFEST_FILES

"""
from pathlib import Path
from collections import defaultdict

MAX_FILES = 25
MAX_FILE_BYTES_HARD = 200_000 # 200KB hard cutoff — skip entirely
WORKFLOW_DIR = '.github/workflows'

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

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg',
    '.pdf', '.zip', '.tar', '.gz',
    '.woff', '.woff2', '.ttf', '.eot',
    '.pyc', '.exe', '.bin', '.so', '.dll',
    '.mp4', '.mp3', '.mov',
}

EXCLUDED_DIRS = {
    'node_modules', 'dist', 'build', '.next', 'target',
    '.venv', 'venv', '__pycache__', 'vendor'
}


def _extantion(path: str) -> str:
    return Path(path).suffix.lower()

def _filename(path: str) -> str:
    return Path(path).name

def is_too_large(size: int) -> bool:
    return size > MAX_FILE_BYTES_HARD

def is_excluded_path(path: str) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.split('/'))

def is_binary(path: str) -> bool:
    return _extantion(path) in BINARY_EXTENSIONS


def is_priority(path: str) -> bool:
    name = _filename(path)
    stem = Path(path).stem.upper()
    # Exact match
    if name in PRIORITY_PATTERNS:
        return True
    # Prefix match: README*, CHANGELOG*, CONTRIBUTING*, LICENSE*
    if stem in {'README', 'CHANGELOG', 'CONTRIBUTING', 'LICENSE'}:
        return True
    # CI workflows directory
    if WORKFLOW_DIR in path:
        return True
    return False


def score_file(path: str, size: int) -> float:
    """
    Returns a score — higher = more informative. 
    No single right set of values; these are reasonable defaults.
    """
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
    # if fname in LOCK_FILES:                             score -= 5.0
    if 'test' in parts or 'spec' in parts:              score -= 1.5  # test directory
    if 'test' in name or 'spec' in name:                score -= 1.0  # test filename
    if len(parts) > 5:                                  score -= 1.0  # extreme nesting
    if size > 50_000:                                   score -= 2.0  # large file

    return score

def get_package_roots(tree_entries: list[dict]) -> set[str]:
    """
    Detects monorepo package roots — any directory containing a manifest file.
    """
    roots = set()
    for e in tree_entries:
        if e.get('type') == 'blob' and Path(e['path']).name in MANIFEST_FILES:
            roots.add(str(Path(e['path']).parent))
    return roots

def get_group(path: str, package_roots: set[str]) -> str:
    """
    Assigns a file to its deepest package root. Falls back to top-level directory.
    """
    matching = [r for r in package_roots if path.startswith(r + '/')]
    if matching:
        return max(matching, key=len)
    return path.split('/')[0] if '/' in path else '.'

def select_files(tree_entries: list[dict]) -> list[str]:
    """ 
    Main selection function. Implements the full strategy. 
    """
    # Step 1: Filter — blobs only, not binary, not excluded dir, not too large
    candidates = [
        e for e in tree_entries
        if e.get('type') == 'blob'
        and not is_binary(e['path'])
        and not is_excluded_path(e['path'])
        and not is_too_large(e.get('size', 0))
        and not Path(e['path']).name in LOCK_FILES
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

