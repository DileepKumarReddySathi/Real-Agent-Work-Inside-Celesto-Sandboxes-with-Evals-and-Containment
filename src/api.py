"""
FastAPI HTTP Control Plane and Run Ledger API.

Endpoints:
- GET /health -> 200 {"status": "ok"}
- GET /api/runs -> 200 [ { "run_id": ..., "sandbox_name": ..., "execution_target": "celesto_sandbox", ... } ]
- POST /api/runs -> 201 with created object, or 400 if validation fails
"""

import os
import re
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from src.database import init_db, list_runs, insert_run
from src.models import RunCreate

SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")
VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database connection and verify seeds
    init_db()
    yield

app = FastAPI(title="Celesto Run Ledger API", version="1.0.0", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure schema validation errors return HTTP 400 as strictly specified."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Validation error", "errors": exc.errors()}
    )

@app.get("/health", status_code=status.HTTP_200_OK)
async def get_health():
    """Health check probe for container orchestrator."""
    return {"status": "ok"}

@app.get("/api/runs", status_code=status.HTTP_200_OK)
async def get_runs() -> List[Dict[str, Any]]:
    """Retrieve all logged sandbox runs from Postgres."""
    runs = list_runs()
    return runs

@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
async def create_run(request: Request):
    """Record a sandbox execution run in the Postgres ledger."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    # Strict validation of required fields
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body must be an object")

    for field in ["run_id", "sandbox_name", "problem_id", "state", "execution_target"]:
        if field not in body or not isinstance(body[field], str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing or invalid string field: {field}"
            )

    sandbox_name = body["sandbox_name"]
    if not SANDBOX_REGEX.match(sandbox_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"sandbox_name '{sandbox_name}' does not match pattern '^sbx-[a-z0-9]{{8,}}$'"
        )

    state = body["state"]
    if state not in VALID_STATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"state '{state}' must be one of: {sorted(VALID_STATES)}"
        )

    execution_target = body["execution_target"]
    if execution_target != "celesto_sandbox":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"execution_target must be exactly 'celesto_sandbox', got '{execution_target}'"
        )

    saved_run = insert_run(body)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=saved_run)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
