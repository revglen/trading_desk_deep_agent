from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

class TradeProposal(BaseModel):
    ticker: str =Field(..., description="Exchange ticker symbol, e.g. AAPL")
    action: Literal["buy", "sell"]
    shares: int =Field(..., gt=0, description="Requested share quantity, must be positive")
    rationale: str = Field(..., min_length=20, description="Full research rationale")
    confidence: float = Field(..., ge=0.0, le=1.0)
    risks: list[str] = Field(..., min_length=1, description="Concrete, specific risk factors")

    @field_validator("ticker")
    @classmethod
    def _uppercase_ticker(cls, v: str) -> str:
        return v.strip().upper()

class RiskVerdict(BaseModel):
   approved: bool
   original_shares: int
   approved_shares: int = Field(..., ge=0)
   resized: bool
   reason: str
   risk_metrics: dict =  Field(default_factory=dict)
   evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketSnapshot(BaseModel):
    ticker: str
    price: float = Field(..., gt=0)
    daily_volatility_pct: float = Field(..., ge=0, description="e.g. ATR% or stdev of daily returns")
    sector: str
    source: Literal["live", "mock"] = "mock"

class ExecutionResult(BaseModel):
    """Outcome of an order submission attempt (paper or, if ever enabled, live)."""

    status: Literal["submitted", "duplicate_suppressed", "failed", "skipped"]
    broker_order_id: str | None = None
    idempotency_key: str
    ticker: str
    action: Literal["buy", "sell"]
    shares: int
    detail: str = ""
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))