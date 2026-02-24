from fastapi import FastAPI
from app.models import SummarizeRequest, SummarizeResponse, ErrorResponse

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/echo")
async def echo(req: SummarizeRequest):
    return req