from fastapi import APIRouter, HTTPException
from app.models import SummarizeRequest, SummarizeResponse
from app.github_client import (
    parse_github_url, get_repo,
    get_default_branch_sha, get_tree_sha, get_recursive_tree,
)
from app.selection import select_files
from app.context import build_context
from app.llm_client import call_llm
from app.parsing import parse_llm_response

router = APIRouter()


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest):
    # Step 1 — parse URL
    try:
        owner, repo = parse_github_url(req.github_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Steps 2–8 — pipeline
    try:
        repo_info = get_repo(owner, repo)
        branch = repo_info["default_branch"]
        commit_sha = get_default_branch_sha(owner, repo, branch)
        tree_sha = get_tree_sha(owner, repo, commit_sha)
        tree = get_recursive_tree(owner, repo, tree_sha)
        selected = select_files(tree)
        result = build_context(owner, repo, branch, repo_info, tree, selected)
        raw = await call_llm(result["context"])
        parsed = parse_llm_response(raw)
        return SummarizeResponse(**parsed)
    except HTTPException:
        raise  # don't swallow HTTPExceptions from downstream
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
