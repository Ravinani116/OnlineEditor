
import os
import asyncio
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
JUDGE0_URL = os.getenv(
    "JUDGE0_URL", "https://ce.judge0.com"
).rstrip("/")

LANGUAGES = {
    "python": 71,
    "c": 50,
    "cpp": 54,
    "java": 62,
    "javascript": 63,
}

app = FastAPI(title="Online Compiler API")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded, _rate_limit_exceeded_handler
)

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)


class RunRequest(BaseModel):
    language: str = Field(min_length=1, max_length=20)
    code: str = Field(min_length=1, max_length=20000)
    stdin: str = Field(default="", max_length=5000)


@app.get("/")
async def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/run")
@limiter.limit("5/minute")
async def run_code(request: Request, body: RunRequest):
    language = body.language.lower()

    if language not in LANGUAGES:
        raise HTTPException(400, "Unsupported language")

    if not body.code.strip():
        raise HTTPException(400, "Enter some code")

    payload = {
        "language_id": LANGUAGES[language],
        "source_code": body.code,
        "stdin": body.stdin,
        "cpu_time_limit": 2,
        "cpu_extra_time": 1,
        "wall_time_limit": 5,
        "memory_limit": 65536,
        "stack_limit": 16384,
        "max_processes_and_or_threads": 20,
        "enable_network": False,
    }

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                f"{JUDGE0_URL}/submissions",
                params={"wait": "true"},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

    except httpx.TimeoutException:
        raise HTTPException(504, "Execution service timed out")
    except httpx.HTTPError:
        raise HTTPException(502, "Execution service unavailable")
    except ValueError:
        raise HTTPException(502, "Invalid execution service response")

    return {
        "stdout": result.get("stdout") or "",
        "stderr": result.get("stderr") or "",
        "compile_output": result.get("compile_output") or "",
        "message": result.get("message") or "",
        "status": (result.get("status") or {}).get("description", "Unknown"),
        "time": result.get("time"),
        "memory": result.get("memory"),
    }
