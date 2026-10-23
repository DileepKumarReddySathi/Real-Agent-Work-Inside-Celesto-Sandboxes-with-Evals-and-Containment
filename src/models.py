from pydantic import BaseModel, Field, field_validator
import re
from typing import Literal, Optional
from datetime import datetime

SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")
VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}

class RunCreate(BaseModel):
    run_id: str = Field(..., min_length=1, description="Unique run identifier")
    sandbox_name: str = Field(..., description="Sandbox name matching sbx- and 8+ lowercase alphanumeric")
    problem_id: str = Field(..., min_length=1, description="Associated problem or benchmark ID")
    state: str = Field(..., description="Lifecycle state of the sandbox run")
    execution_target: str = Field(..., description="Target execution environment (must be celesto_sandbox)")

    @field_validator("sandbox_name")
    def validate_sandbox_name(cls, v: str) -> str:
        if not SANDBOX_REGEX.match(v):
            raise ValueError(f"sandbox_name '{v}' must match pattern '^sbx-[a-z0-9]{{8,}}$'")
        return v

    @field_validator("state")
    def validate_state(cls, v: str) -> str:
        if v not in VALID_STATES:
            raise ValueError(f"state '{v}' must be one of: {sorted(VALID_STATES)}")
        return v

    @field_validator("execution_target")
    def validate_execution_target(cls, v: str) -> str:
        if v != "celesto_sandbox":
            raise ValueError(f"execution_target must be exactly 'celesto_sandbox', got '{v}'")
        return v

class RunRecord(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str
    created_at: Optional[str] = None
