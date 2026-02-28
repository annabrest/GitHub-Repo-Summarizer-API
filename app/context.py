from pathlib import Path
import httpx
from app.github_client import get_file_content

MAX_TOTAL_CHARS  = 60_000
README_MAX_CHARS = 12_000   # head (6k) + tail (6k)
MAX_FILE_CHARS   =  6_000
MAX_TREE_LINES   =    250


def _is_readme(path: str) -> bool:
    return Path(path).stem.upper() == "README"


def _truncate_readme(content: str) -> str:
    if len(content) <= README_MAX_CHARS:
        return content
    half = README_MAX_CHARS // 2
    return content[:half] + "\n...[truncated]...\n" + content[-half:]


def build_context(
    owner: str,
    repo: str,
    branch: str,
    repo_info: dict,
    tree: list[dict],
    selected_files: list[str],
) -> dict:
    parts = []

    # 1. Repo header
    desc = repo_info.get("description") or "N/A"
    parts.append(f"# {owner}/{repo}\nDescription: {desc}\nBranch: {branch}")

    # 2. Tree preview (blob paths only)
    blob_paths = [e["path"] for e in tree if e.get("type") == "blob"]
    parts.append("## File tree\n" + "\n".join(blob_paths[:MAX_TREE_LINES]))

    # 3. Per-file sections with budget enforcement
    chars_used = sum(len(p) for p in parts)
    files_included = []

    for path in selected_files:
        try:
            if _is_readme(path):
                raw = get_file_content(owner, repo, path, ref=branch, max_chars=MAX_TOTAL_CHARS)
                content = _truncate_readme(raw)
            else:
                content = get_file_content(owner, repo, path, ref=branch, max_chars=MAX_FILE_CHARS)
        except (httpx.ConnectError, httpx.HTTPError, Exception):
            continue  # skip files that fail to fetch

        if not content:
            continue

        section = f"=== {path} ===\n{content}"
        if chars_used + len(section) > MAX_TOTAL_CHARS:
            continue
        parts.append(section)
        chars_used += len(section)
        files_included.append(path)

    context = "\n\n".join(parts)
    return {
        "context": context,
        "total_chars": len(context),
        "files_included": files_included,
    }
