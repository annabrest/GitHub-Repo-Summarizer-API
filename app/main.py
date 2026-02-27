from fastapi import FastAPI
from app.models import SummarizeRequest, SummarizeResponse, ErrorResponse
from app.github_client import parse_github_url, get_repo

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
