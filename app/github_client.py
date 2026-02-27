from urllib.parse import urlparse
from fastapi import HTTPException
import httpx
import os

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
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = httpx.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Repo '{owner}/{repo}' not found on GitHub")
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="Private repo or rate limit exceeded")
    response.raise_for_status()  # catches other unexpected errors (500, 403, etc.)

    return response.json()  # returns a dictionary of the response


