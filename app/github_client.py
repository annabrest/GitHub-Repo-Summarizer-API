from urllib.parse import urlparse
from fastapi import HTTPException
import httpx
import os
import base64

def _github_get(url: str) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = httpx.get(url, headers=headers, timeout=10.0)
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Resource not found: {url}")
    if response.status_code == 403:
        body = response.json() if response.content else {}
        msg = body.get("message", "")
        if "rate limit" in msg.lower():
            raise HTTPException(status_code=429, detail="GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limit.")
        raise HTTPException(status_code=403, detail="Repository is private or access denied.")
    response.raise_for_status()  # catches other unexpected errors (500, 403, etc.)
    return response.json()

def parse_github_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise HTTPException(status_code=400, detail="Invalid GitHub URL. Expected: https://github.com/owner/repo")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL. Expected: https://github.com/owner/repo")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return owner, repo

def get_repo(owner: str, repo: str) -> dict:
    data=_github_get(f"https://api.github.com/repos/{owner}/{repo}")
    return data


def get_default_branch(owner: str, repo: str) -> str:
    data=get_repo(owner, repo)
    return data["default_branch"]

def get_default_branch_sha(owner: str, repo: str, default_branch: str) -> str:
    data=_github_get(f"https://api.github.com/repos/{owner}/{repo}/branches/{default_branch}")
    return data["commit"]["sha"]

def get_tree_sha(owner: str, repo: str, commit_sha: str) -> str:
    data=_github_get(f"https://api.github.com/repos/{owner}/{repo}/git/commits/{commit_sha}")
    return data["tree"]["sha"]

def get_recursive_tree(owner: str, repo: str, tree_sha: str) -> list[dict]:
    data=_github_get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1")
    return data["tree"]

def get_file_content(owner: str, repo: str, path: str, ref: str, max_chars: int = 10_000) -> str:
    data = _github_get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}")
    if data.get("encoding") != "base64":
        return ""
    try:
        text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except (UnicodeDecodeError, Exception):
        return ""
    return text[:max_chars]
