"""
PaperBroker: the ONLY execution path enabled by default.

Wraps Alpaca's paper-trading (sandbox) API. If no Alpaca credentials are
configured, falls back to a DryRunClient that simulates fills and logs them -
this keeps the whole system runnable end-to-end (including in this
repository's own tests/demo) without requiring any external account.

Every order submission is protected by an idempotency key derived from
(correlation_id, ticker, action, approved_shares) so that retries - e.g. a
CLI re-run after a network blip, or a resumed LangGraph run after a crash -
can never result in a duplicate order at the broker.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from execution.idempotency import IdempotencyStore
from observability import metrics
from observability.audit import AuditLogger
from schemas import ExecutionResult, RiskVerdict, TradeProposal


class DryRunClient:
    """Local stand-in used when no ALPACA_API_KEY is configured. Simulates
    an immediate fill and returns a fake broker order id. Clearly logged as
    a simulation so it is never mistaken for a real fill."""

    def submit_market_order(self, *, symbol: str, qty: int, side: str, client_order_id: str) -> dict:
        return {
            "id": f"dryrun-{uuid.uuid4()}",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "client_order_id": client_order_id,
            "status": "filled",
            "simulated": True,
        }


class AlpacaPaperClient:
    """Thin wrapper around alpaca-py's TradingClient, paper=True. Imported
    lazily so the alpaca-py dependency is optional at runtime for anyone
    running in DRY_RUN mode."""

    def __init__(self, api_key: str, secret_key: str):
        from alpaca.trading.client import TradingClient  # lazy import

        self._client = TradingClient(api_key, secret_key, paper=True)

    def submit_market_order(self, *, symbol: str, qty: int, side: str, client_order_id: str) -> dict:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        order = self._client.submit_order(request)
        return {
            "id": str(order.id),
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "client_order_id": client_order_id,
            "status": str(order.status),
            "simulated": False,
        }


@dataclass
class PaperBroker:
    idempotency_store: IdempotencyStore
    audit: AuditLogger
    api_key: str | None = None
    secret_key: str | None = None

    def __post_init__(self) -> None:
        if self.api_key and self.secret_key:
            self._client = AlpacaPaperClient(self.api_key, self.secret_key)
            self._mode = "alpaca_paper"
        else:
            self._client = DryRunClient()
            self._mode = "dry_run"

    def submit_order(
        self,
        proposal: TradeProposal,
        verdict: RiskVerdict,
        correlation_id: str,
    ) -> ExecutionResult:
        if not verdict.approved or verdict.approved_shares <= 0:
            raise ValueError("submit_order called with a non-approved RiskVerdict - this is a bug upstream")

        idempotency_key = self.idempotency_store.make_key(
            correlation_id, proposal.ticker, proposal.action, verdict.approved_shares
        )

        existing = self.idempotency_store.get(idempotency_key)
        if existing is not None:
            self.audit.log_execution(
                correlation_id=correlation_id,
                event="duplicate_suppressed",
                detail={"idempotency_key": idempotency_key, "existing_status": existing["status"]},
            )
            metrics.BROKER_ORDERS_TOTAL.labels(mode=self._mode, status="duplicate_suppressed").inc()
            return ExecutionResult(
                status="duplicate_suppressed",
                broker_order_id=existing.get("broker_order_id"),
                idempotency_key=idempotency_key,
                ticker=proposal.ticker,
                action=proposal.action,
                shares=verdict.approved_shares,
                detail=f"order already {existing['status']} for this idempotency key - not resubmitting",
            )

        reserved = self.idempotency_store.try_reserve(
            idempotency_key,
            payload={
                "correlation_id": correlation_id,
                "ticker": proposal.ticker,
                "action": proposal.action,
                "shares": verdict.approved_shares,
                "mode": self._mode,
            },
        )
        if not reserved:
            # Lost a race to a concurrent submitter for the same key.
            existing = self.idempotency_store.get(idempotency_key) or {}
            metrics.BROKER_ORDERS_TOTAL.labels(mode=self._mode, status="duplicate_suppressed").inc()
            return ExecutionResult(
                status="duplicate_suppressed",
                broker_order_id=existing.get("broker_order_id"),
                idempotency_key=idempotency_key,
                ticker=proposal.ticker,
                action=proposal.action,
                shares=verdict.approved_shares,
                detail="lost idempotency-key race to a concurrent submission",
            )

        try:
            raw = self._client.submit_market_order(
                symbol=proposal.ticker,
                qty=verdict.approved_shares,
                side=proposal.action,
                client_order_id=idempotency_key,
            )
            self.idempotency_store.mark_submitted(idempotency_key, raw["id"])
            self.audit.log_execution(
                correlation_id=correlation_id,
                event="submitted",
                detail={"mode": self._mode, **raw},
            )
            metrics.BROKER_ORDERS_TOTAL.labels(mode=self._mode, status="submitted").inc()
            return ExecutionResult(
                status="submitted",
                broker_order_id=raw["id"],
                idempotency_key=idempotency_key,
                ticker=proposal.ticker,
                action=proposal.action,
                shares=verdict.approved_shares,
                detail=f"mode={self._mode} status={raw['status']}",
            )
        except Exception as exc:  # noqa: BLE001 - broker errors are heterogeneous
            self.idempotency_store.mark_failed(idempotency_key, str(exc))
            self.audit.log_execution(
                correlation_id=correlation_id,
                event="failed",
                detail={"error": str(exc)},
            )
            metrics.BROKER_ORDERS_TOTAL.labels(mode=self._mode, status="failed").inc()
            return ExecutionResult(
                status="failed",
                idempotency_key=idempotency_key,
                ticker=proposal.ticker,
                action=proposal.action,
                shares=verdict.approved_shares,
                detail=str(exc),
            )
