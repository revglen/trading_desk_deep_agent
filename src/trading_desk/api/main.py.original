from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from service import Service

from api.schemas import (
    ApproveRequest,
    ApproveResponse,
    HealthResponse,
    ProposalSummary,
    ProposeRequest,
    ProposeResponse,
    StatusResponse,
)

from config import get_settings
from observability.logging_config import StructuredLog #configure_logging

settings = get_settings()
StructuredLog.configure_logging(settings)

app = FastAPI(
    title="Deep Agent Trading Research Desk",
    description=(
        "REST API over the propose -> risk-check -> human-approve -> execute pipeline. "
        "The LLM layer only ever produces a TradeProposal; risk sizing is deterministic; "
        "execution requires an explicit human decision via POST /proposals/{thread_id}/approve."
    ),
    version="0.1.0",
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

@app.get("/healthz", response_model=HealthResponse)
def healthz()-> HealthResponse:
    return HealthResponse(status="ok")

@app.post("/proposals", response_model=ProposeResponse)
def create_proposal(body: ProposeRequest) -> ProposeResponse:
    outcome = Service().propose_trade(settings, ticker=body.ticker, question=body.question)
    return ProposeResponse(**outcome)

@app.post("/proposals/{thread_id}/approve", response_model=ApproveResponse)
def approve_proposal(thread_id: str, body: ApproveRequest)->ApproveResponse:
    try:
        outcome = Service().approve_trade(
        settings, thread_id=thread_id, decision=body.decision, approver=body.approver, notes=body.notes)
        return ApproveResponse(**outcome)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
@app.get("/proposals/{thread_id}", response_model=StatusResponse)
def get_proposal(thread_id: str) -> StatusResponse:
    outcome = Service().get_status(settings, thread_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail=f"No thread found for thread_id={thread_id}")
    return StatusResponse(**outcome)

@app.get("/proposals", response_model=list[ProposalSummary])
def list_proposals(limit: int = 20) -> list[ProposalSummary]:
    return [ProposalSummary(**row) for row in Service().list_recent_proposals(settings, limit=limit)]

def fastaoi_starter():
    import uvicorn
    uvicorn.run("api.main:app", host=settings.api_host, port=settings.api_port, reload=True)

if __name__ == "__main__":
  fastaoi_starter()  
