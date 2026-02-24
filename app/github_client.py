from urllib.parse import urlparse
from fastapi import HTTPException


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
