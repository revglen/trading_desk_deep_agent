from __future__ import annotations
from typing import Any, TypedDict

class TradingDeskState(TypedDict, total=False):
    correlation_id: str
    ticker: str
    user_request: str

    proposal: dict[str, Any] | None
    risk_verdict: dict[str, Any] | None
    human_decision: dict[str, Any] | None
    execution_result: dict[str, Any] | None

    status: str