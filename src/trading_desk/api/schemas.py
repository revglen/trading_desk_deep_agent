from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

class ProposeRequest(BaseModel):
    ticker: str = Field(..., examples=["AAPL"])
    question: str = Field(
        default="Evaluate for a potential position.",
        examples=["Evaluate for a swing-trade long entry"],
    )

class ProposeResponse(BaseModel):
    thread_id: str
    state: str
    interrupt: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

class ApproveRequest(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str = Field(..., examples=["jane.doe"])
    notes: str = ""

class ApproveResponse(BaseModel):
    thread_id: str
    state: str
    result: dict[str, Any]

class StatusResponse(BaseModel):
    thread_id: str
    state: dict[str, Any]
    audit_trail: list[dict[str, Any]]

class ProposalSummary(BaseModel):
    correlation_id: str
    ticker: str | None
    latest_event: str
    last_activity_at: Any

class HealthResponse(BaseModel):
    status: Literal["ok"]