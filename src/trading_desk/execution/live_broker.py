"""
LiveBroker - REAL MONEY execution path. STUBBED OUT. DISABLED BY DEFAULT.

This class is intentionally non-functional. Two independent gates must both
be satisfied before it will even construct, and its submit_order method
always raises NotImplementedError regardless - see the module docstring
in README.md ("Going live") for what real implementation would require and
why each step is dangerous.

Gate 1: env var ENABLE_LIVE_TRADING=true
Gate 2: LIVE_TRADING_API_KEY / LIVE_TRADING_SECRET_KEY set - these are
        DELIBERATELY separate env vars from ALPACA_API_KEY/ALPACA_SECRET_KEY
        so that paper credentials can never be silently reused for live
        trading and vice versa.

Even with both gates satisfied, submit_order() still raises
NotImplementedError. Someone must deliberately write and review a real
implementation (with its own additional review, limits, and sign-off) before
this path can move a single dollar.
"""
from __future__ import annotations

from config import Settings
from schemas import ExecutionResult, RiskVerdict, TradeProposal

class LiveTradingDisabledError(RuntimeError):
    pass

class LiveBroker:
    def __init__(self, settings: Settings):
        if not settings.enable_live_trading:
            raise LiveTradingDisabledError(
                "Live trading is disabled. Set ENABLE_LIVE_TRADING=true to even construct "
                "LiveBroker, and understand that submit_order() will still raise "
                "NotImplementedError until a reviewed live-execution implementation exists."
            )
        if not (settings.live_trading_api_key and settings.live_trading_secret_key):
            raise LiveTradingDisabledError(
                "LIVE_TRADING_API_KEY / LIVE_TRADING_SECRET_KEY are not both set. These must be "
                "distinct, dedicated live-trading credentials - paper credentials are never "
                "reused here."
            )
        self._settings = settings

    def submit_order(
        self,
        proposal: TradeProposal,
        verdict: RiskVerdict,
        correlation_id: str,
    ) -> ExecutionResult:
        raise NotImplementedError(
            "Live order execution is intentionally not implemented in this codebase. "
            "Moving to live trading requires: a real broker client with production "
            "credentials, an independent second risk review layer, mandatory dual human "
            "approval, real-time position reconciliation against the broker (not just the "
            "local PortfolioState file), and a kill switch. See README.md 'Going live'."
        )
