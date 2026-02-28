from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.models import SummarizeRequest, SummarizeResponse, ErrorResponse
from app.github_client import parse_github_url, get_repo, get_default_branch_sha, get_tree_sha, get_recursive_tree
from app.selection import select_files

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/echo")
async def echo(req: SummarizeRequest):
    return req

@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest):
    owner, repo = parse_github_url(req.github_url)
    return SummarizeResponse(summary="stub", technologies=["stub"], structure="stub")
    
@app.get("/debug/repo")
async def debug_repo(owner: str, repo: str):
    data = get_repo(owner, repo)
    return data

@app.get("/debug/tree")
async def debug_tree(owner: str, repo: str):
    repo_info = get_repo(owner, repo)                          # → gets default_branch
    branch = repo_info["default_branch"]
    commit_sha = get_default_branch_sha(owner, repo, branch)   # → gets commit SHA
    tree_sha = get_tree_sha(owner, repo, commit_sha)          # → gets tree SHA
    files = get_recursive_tree(owner, repo, tree_sha)      # → gets all files
    return {"repo_info": repo_info, "branch": branch, "commit_sha": commit_sha, "tree_sha": tree_sha, "files": files}

@app.get("/debug/selection")
async def debug_selection(owner: str, repo: str):
    repo_info = get_repo(owner, repo)                          # → gets default_branch
    branch = repo_info["default_branch"]
    commit_sha = get_default_branch_sha(owner, repo, branch)   # → gets commit SHA
    tree_sha = get_tree_sha(owner, repo, commit_sha)          # → gets tree SHA
    files = get_recursive_tree(owner, repo, tree_sha)      # → gets all files
    selected_files = select_files(files)
    return { "total": len(files), "selected": len(selected_files), "files": selected_files}
    
@app.get("/debug/scores")
async def debug_scores(owner: str, repo: str):
    from app.selection import score_file, get_group, get_package_roots, is_priority, is_excluded_path, is_binary
    repo_info = get_repo(owner, repo)
    branch = repo_info["default_branch"]
    commit_sha = get_default_branch_sha(owner, repo, branch)
    tree_sha = get_tree_sha(owner, repo, commit_sha)
    tree = get_recursive_tree(owner, repo, tree_sha)
    package_roots = get_package_roots(tree)
    lib_files = [
        {"path": e["path"], "score": score_file(e["path"], e.get("size", 0)), "group": get_group(e["path"], package_roots)}
        for e in tree
        if e.get("type") == "blob" and e["path"].startswith("lib/")
    ]
    return sorted(lib_files, key=lambda x: x["score"], reverse=True)
