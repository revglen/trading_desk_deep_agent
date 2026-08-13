from __future__ import annotations

import math
from dataclasses import dataclass

from risk_engine.portfolio_state import PortfolioState
from schemas import MarketSnapshot, RiskVerdict, TradeProposal

@dataclass(frozen=True)
class RiskLimits:
    max_position_size_pct: float = 0.05
    max_ticker_exposure_pct: float = .10
    max_sector_exposure_pct: float = 0.25
    daily_loss_limit_pct: float = 0.03
    risk_per_trade_pct: float = 0.01
    max_daily_trades: int = 20
    allow_short: bool = False

def _vol_adjusted_max_shares(
    equity: float, price: float, daily_volatility_pct: float, limits: RiskLimits) -> int:
    vol = max(daily_volatility_pct, 0.001)
    dollar_risk_budget =equity * limits.risk_per_trade_pct
    per_share_risk = price * vol
    if per_share_risk <= 0:
        return 0

    return math.floor(dollar_risk_budget / per_share_risk)

def validate_proposal(
  proposal: TradeProposal,
  portfolio: PortfolioState,
  market: MarketSnapshot,
  limits: RiskLimits | None=None
) -> RiskVerdict:
    limits = limits or RiskLimits()

    if proposal.ticker != market.ticker:
        raise ValueError(
                f"market snapshot ticker {market.ticker!r} does not match proposal ticker {proposal.ticker!r}"
            )

    original_shares = proposal.shares
    metrics: dict = {
        "price": market.price,
        "equity": portfolio.equity,
        "daily_volatility_pct": market.daily_volatility_pct,
    }

    if original_shares <= 0:
        return _reject(original_shares, "shares must be positive", metrics)

    if portfolio.trades_today >= limits.max_daily_trades:
        return _reject(original_shares, f"max_daily_trades limit reached ({limits.max_daily_trades})", metrics)

    # ---- 1. Daily loss limit halts new risk-increasing BUYs ----
    daily_pnl_pct = portfolio.daily_pnl_pct()
    metrics["daily_pnl_pct"] = daily_pnl_pct
    if proposal.action == "buy" and daily_pnl_pct <= -abs(limits.daily_loss_limit_pct):
        return _reject(
                    original_shares,
                    f"daily loss limit breached ({daily_pnl_pct:.2%} <= -{limits.daily_loss_limit_pct:.2%}); "
                    "new buy orders are blocked for the rest of the trading day",
                    metrics,
                )

    # ---- 2. Sells: cannot exceed held shares unless shorting is allowed ----
    if proposal.action == "sell":
        held = proposal.position_shares(proposal.ticker)
        metrics["held_shares"] = held
        if held <=0  and not limits.allow_short:
            return _reject(original_shares, f"no position to sell in {proposal.ticker} and shorting is disabled", metrics)

        if original_shares > held and not limits.allow_short:
            shares = held
            if shares <= 0:
                return _reject(original_shares, f"no position to sell in {proposal.ticker} and shorting is disabled", metrics)

            return _approve(
                        original_shares, shares,
                        f"sell size capped to current holdings ({held} shares); shorting disabled",
                        metrics,
                    )

        return _approve(original_shares, original_shares, "sell approved at requested size", metrics)

    shares=original_shares
    reasons: list[str] = []

    # ---- 3. Max single-order position size vs equity ----
    max_notional=portfolio.equity * limits.max_position_size_pct
    max_shares_by_position = math.floor(max_notional / market.price) if market.price > 0 else 0
    metrics["max_shares_by_position_limit"] = max_shares_by_position
    if shares > max_shares_by_position:
        shares = max_shares_by_position

    reasons.append(
                f"resized to respect max_position_size_pct={limits.max_position_size_pct:.1%} of equity"
            )

    # ---- 4. Max post-trade exposure to this ticker ----
    existing_notional = portfolio.position_notional(proposal.ticker, market.price)
    max_ticker_notional = portfolio.equity * limits.max_ticker_exposure_pct
    from_notional = max(max_ticker_notional - existing_notional, 0.0)
    max_shares_by_ticker_exposure = math.floor(from_notional /market.price) if market.price > 0 else 0
    metrics["max_shares_ticker_exposure"] = max_shares_by_ticker_exposure
    metrics["existing_ticker_notional"] = existing_notional
    if shares > max_shares_by_ticker_exposure:
        shares = max_shares_by_ticker_exposure
        reasons.append(
            f"resized to respect max_ticker_exposure_pct={limits.max_ticker_exposure_pct:.1%} of equity "
            f"(existing exposure ${existing_notional:,.0f})"
        )

    # ---- 5. Max post-trade exposure to this sector ----
    sector = market.sector or portfolio.sector_of(proposal.ticker)
    price_lookup = {proposal.ticker: market.price}
    existing_sector_notional = portfolio.sector_notional(sector, price_lookup)
    max_sector_notional = portfolio.equity * limits.max_sector_exposure_pct
    sector_room_notional = max(max_sector_notional - existing_sector_notional, 0.0)
    max_shares_by_sector = math.floor(sector_room_notional / market.price) if market.price > 0 else 0
    metrics["sector"] = sector
    metrics["existing_sector_notional"] = existing_sector_notional
    metrics["max_shares_by_sector_exposure"] = max_shares_by_sector
    if shares > max_shares_by_sector:
        shares = max_shares_by_sector
        reasons.append(
            f"resized to respect max_sector_exposure_pct={limits.max_sector_exposure_pct:.1%} of equity "
            f"for sector {sector!r} (existing exposure ${existing_sector_notional:,.0f})"
        )

    # ---- 6. Volatility-adjusted position sizing ----
    vol_max_shares = _vol_adjusted_max_shares(portfolio.equity, market.price, market.daily_volatility_pct, limits)
    metrics["volatility_adjusted_max_shares"]=vol_max_shares
    if shares > vol_max_shares:
        shares = vol_max_shares
        reasons.append(
            f"resized for volatility-adjusted sizing (daily_volatility={market.daily_volatility_pct:.2%}, "
            f"risk_per_trade_pct={limits.risk_per_trade_pct:.1%})"
        )

    if shares <= 0:
        combined = ", ".join(reasons) if reasons else "no capacity remains under current risk limits"
        return _reject(original_shares, f"rejected - {combined}", metrics)

    if shares < original_shares:
        return _approve(original_shares, shares, "; ".join(reasons), metrics)

    return _approve(original_shares, shares, "approved at requested size - within all limits", metrics)

def _approve(original_shares:int,
            approved_shares: int,
            reason: str,
            metrics: dict) -> RiskVerdict:
    return RiskVerdict(
                approved=True,
                original_shares = original_shares,
                approved_shares = approved_shares,
                resized=approved_shares != original_shares,
                reason=reason,
                risk_metrics=metrics
    )
  
def _reject(original_shares: int, reason: str, metrics: dict) -> RiskVerdict:
    return RiskVerdict(
        approved=False,
        original_shares=original_shares,
        approved_shares=0,
        resized=False,
        reason=reason,
        risk_metrics=metrics,
    )