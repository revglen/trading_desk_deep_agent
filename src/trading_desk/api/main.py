from __future__ import annotations

import time
import uuid
from typing import Any

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

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
from observability.logging_config import StructuredLog

settings = get_settings()
StructuredLog.configure_logging(settings)
logger = StructuredLog.get_logger("api")

TAGS_METADATA = [
    {
        "name": "Health",
        "description": (
            "Liveness check for load balancers and uptime monitors - confirms the "
            "process is up and responding. Not meant for humans to click."
        ),
    },
    {
        "name": "Proposals",
        "description": (
            "The core trading-desk workflow: **research → size → approve → execute.**\n\n"
            "1. An LLM-driven analyst team researches a ticker and writes up a "
            "*proposal* - a suggested trade, with reasoning. It never has authority "
            "to actually place a trade.\n"
            "2. A deterministic (non-LLM) risk engine checks that proposal against "
            "position limits and either approves it as-is, shrinks the share count "
            "to fit within limits, or rejects it outright.\n"
            "3. If it's approved, the workflow pauses and waits - nothing happens "
            "next until a human calls `/approve` with an explicit approve/reject "
            "decision.\n"
            "4. Only after that human sign-off does an order go to the paper broker "
            "(a simulated broker - no real money moves, ever, through this API)."
        ),
    },
]

class ErrorDetail(BaseModel):
    field: str = Field(..., examples=["body.ticker"])
    issue: str = Field(..., examples=["Field required"])

class ErrorBody(BaseModel):
    code: str = Field(..., examples=["invalid_request"])
    message: str = Field(..., examples=["Request failed validation - check the fields listed in 'details'."])
    request_id: str = Field(..., examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    details: list[ErrorDetail] | None = None

class ErrorResponse(BaseModel):
    """Every error this API returns - any status >= 400 - has this shape."""
    error: ErrorBody

def _error_example(code: str, message: str, *, details: list[dict] | None = None) -> dict:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    }
    if details:
        body["details"] = details
    return {"error": body}

RESPONSE_400 = {
    "model": ErrorResponse,
    "description": "Invalid business input (e.g. an unrecognized decision value).",
    "content": {
        "application/json": {
            "example": _error_example("invalid_request", "ticker not tradable on this exchange")
        }
    },
}

RESPONSE_404 = {
    "model": ErrorResponse,
    "description": "No proposal exists for the given thread_id.",
    "content": {
        "application/json": {
            "example": _error_example("not_found", "No thread found for thread_id=abc-123")
        }
    },
}

RESPONSE_422 = {
    "model": ErrorResponse,
    "description": "Request failed schema validation.",
    "content": {
        "application/json": {
            "example": _error_example(
                "invalid_request",
                "Request failed validation - check the fields listed in 'details'.",
                details=[{"field": "body.ticker", "issue": "Field required"}],
            )
        }
    },
}

RESPONSE_500 = {
    "model": ErrorResponse,
    "description": "Unexpected server-side failure. Share the request_id with support.",
    "content": {
        "application/json": {
            "example": _error_example(
                "internal_error",
                "Something went wrong processing this request. "
                "If this keeps happening, share the request ID with support.",
            )
        }
    },
}

RESPONSE_502 = {
    "model": ErrorResponse,
    "description": "A downstream dependency (model provider, market data, or broker) didn't respond in time.",
    "content": {
        "application/json": {
            "example": _error_example(
                "upstream_unavailable",
                "A downstream service (model provider, market data, or broker) "
                "did not respond in time. Please retry.",
            )
        }
    },
}

RESPONSE_503 = {
    "model": ErrorResponse,
    "description": "The database is temporarily unreachable.",
    "content": {
        "application/json": {
            "example": _error_example(
                "persistence_unavailable",
                "The database is temporarily unavailable. Please retry shortly.",
            )
        }
    },
}
COMMON_ERROR_RESPONSES = {422: RESPONSE_422, 500: RESPONSE_500, 502: RESPONSE_502, 503: RESPONSE_503}

app = FastAPI(
    title="Deep Agent Trading Research Desk",
    description=(
        "REST API over the propose -> risk-check -> human-approve -> execute pipeline. "
        "The LLM layer only ever produces a TradeProposal; risk sizing is deterministic; "
        "execution requires an explicit human decision via POST /proposals/{thread_id}/approve.\n\n"
        "**Errors:** every response with status >= 400 uses the same envelope - "
        "`{\"error\": {\"code\", \"message\", \"request_id\", \"details\"?}}` - and every response, "
        "success or failure, carries an `X-Request-ID` header for support/log correlation."
    ),
    version="0.1.0",
    openapi_tags=TAGS_METADATA,
    contact={"name": "Trading Desk team"},
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
_UPSTREAM_EXCEPTION_TYPES = (TimeoutError, ConnectionError)

def _error_envelope(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    StructuredLog.set_correlation_id(request_id)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.error(
            "unhandled_exception_in_middleware",
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            duration_ms=duration_ms,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_envelope(
                "internal_error",
                "Something went wrong processing this request.",
                request_id,
            ),
            headers={"X-Request-ID": request_id},
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        request_id=request_id,
        duration_ms=duration_ms,
    )
    return response

def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")

@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    request_id = _request_id(request)
    logger.warning("validation_error", request_id=request_id, errors=exc.errors())
    envelope = _error_envelope(
        "invalid_request",
        "Request failed validation - check the fields listed in 'details'.",
        request_id,
    )
    envelope["error"]["details"] = [
        {"field": ".".join(str(p) for p in err["loc"]), "issue": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=envelope)

@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    request_id = _request_id(request)
    code = {404: "not_found", 400: "invalid_request", 409: "conflict"}.get(
        exc.status_code, "http_error"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(code, str(exc.detail), request_id),
    )

@app.exception_handler(ValueError)
async def handle_value_error(request: Request, exc: ValueError):
    request_id = _request_id(request)
    logger.warning("invalid_request", request_id=request_id, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_error_envelope("invalid_request", str(exc), request_id),
    )

@app.exception_handler(LookupError)
async def handle_lookup_error(request: Request, exc: LookupError):
    request_id = _request_id(request)
    logger.warning("resource_not_found", request_id=request_id, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=_error_envelope(
            "not_found", "The requested resource could not be found.", request_id
        ),
    )

@app.exception_handler(SQLAlchemyError)
async def handle_db_error(request: Request, exc: SQLAlchemyError):
    request_id = _request_id(request)
    logger.error("persistence_error", request_id=request_id, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=_error_envelope(
            "persistence_unavailable",
            "The database is temporarily unavailable. Please retry shortly.",
            request_id,
        ),
    )

async def handle_upstream_error(request: Request, exc: Exception):
    request_id = _request_id(request)
    logger.error("upstream_dependency_error", request_id=request_id, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=_error_envelope(
            "upstream_unavailable",
            "A downstream service (model provider, market data, or broker) "
            "did not respond in time. Please retry.",
            request_id,
        ),
    )

for _exc_type in _UPSTREAM_EXCEPTION_TYPES:
    app.add_exception_handler(_exc_type, handle_upstream_error)

@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    request_id = _request_id(request)
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        exception_type=type(exc).__name__,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_envelope(
            "internal_error",
            "Something went wrong processing this request. "
            "If this keeps happening, share the request ID with support.",
            request_id,
        ),
    )

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get(
    "/healthz",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Liveness check",
    responses={500: RESPONSE_500},
)
def healthz() -> HealthResponse:
    """Returns `{"status": "ok"}` if the process is up. Does not check the
    database, checkpointer, or any downstream dependency - use this only for
    liveness, not readiness."""
    return HealthResponse(status="ok")

@app.post(
    "/proposals",
    response_model=ProposeResponse,
    tags=["Proposals"],
    summary="Kick off research on a ticker",
    description=(
        "Runs the lead agent's technical / fundamentals / macro-news sub-agents, "
        "produces a `TradeProposal`, and runs it through the deterministic risk "
        "engine. If the risk engine approves (with or without resizing), the "
        "workflow pauses and the response's `state` is `pending_approval` - call "
        "`POST /proposals/{thread_id}/approve` next. If the risk engine rejects "
        "outright, `state` reflects that and the pipeline stops there."
    ),
    responses={400: RESPONSE_400, **COMMON_ERROR_RESPONSES},
)
def create_proposal(body: ProposeRequest) -> ProposeResponse:
    if not body.ticker or not body.ticker.strip():
        raise HTTPException(status_code=422, detail="ticker must not be empty")

    outcome = Service().propose_trade(settings, ticker=body.ticker, question=body.question)
    return ProposeResponse(**outcome)

@app.post(
    "/proposals/{thread_id}/approve",
    response_model=ApproveResponse,
    tags=["Proposals"],
    summary="Approve or reject a pending proposal",
    description=(
        "Resumes a workflow that's paused at the human-approval gate. On "
        "`decision: approve`, the risk-adjusted order is submitted to the "
        "paper broker (idempotently - safe to retry). On `decision: reject`, "
        "the workflow ends without ever contacting the broker."
    ),
    responses={400: RESPONSE_400, 404: RESPONSE_404, **COMMON_ERROR_RESPONSES},
)
def approve_proposal(thread_id: str, body: ApproveRequest) -> ApproveResponse:
    if not body.approver or not body.approver.strip():
        raise HTTPException(status_code=422, detail="approver must not be empty")

    outcome = Service().approve_trade(
        settings,
        thread_id=thread_id,
        decision=body.decision,
        approver=body.approver,
        notes=body.notes,
    )
    return ApproveResponse(**outcome)

@app.get(
    "/proposals/{thread_id}",
    response_model=StatusResponse,
    tags=["Proposals"],
    summary="Get a proposal's current state and audit trail",
    responses={404: RESPONSE_404, **COMMON_ERROR_RESPONSES},
)
def get_proposal(thread_id: str) -> StatusResponse:
    outcome = Service().get_status(settings, thread_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail=f"No thread found for thread_id={thread_id}")
    return StatusResponse(**outcome)

@app.get(
    "/proposals",
    response_model=list[ProposalSummary],
    tags=["Proposals"],
    summary="List recent proposals",
    responses={**COMMON_ERROR_RESPONSES},
)
def list_proposals(limit: int = 20) -> list[ProposalSummary]:
    """`limit` must be between 1 and 200 (default 20)."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    return [ProposalSummary(**row) for row in Service().list_recent_proposals(settings, limit=limit)]

def fastaoi_starter():
    import uvicorn
    uvicorn.run("api.main:app", host=settings.api_host, port=settings.api_port, reload=True)

if __name__ == "__main__":
    fastaoi_starter()