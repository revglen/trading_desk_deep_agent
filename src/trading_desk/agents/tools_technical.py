from __future__ import annotations
from langchain_core.tools import tool

from agents.market_data import get_price_history

def _closes(ticker: str, period: str) -> list[float]:
    return [row["close"] for row in get_price_history(ticker, period)]

@tool
def get_recent_price_history(ticker: str, period: str="6mo") -> list[dict]:
    """Fetch recent OHLCV price history for a ticker. period examples:
    '1mo', '3mo', '6mo', '1y'. Returns a list of daily bars."""
    return get_price_history(ticker, period)

@tool
def compute_moving_averages(ticker: str) -> dict:
    """Compute simple moving averages (20/50/200-day) and whether price is
    above/below each, for a ticker."""

    closes = _closes(ticker, "1y")
    if not closes:
        return {"ticker": ticker, "error": "no price data available"}

    def sma(n: int)->float | None:
        if len(closes) < n:
            return None
    
        return round(sum(closes[-n:]) / n, 2)

    last=closes[-1]
    sma20, sma50, sma200 = sma(20), sma(50), sma(200)

    return {
        "ticker": ticker.upper(),
        "last_close": last,
        "sma_20": sma20,
        "sma_50": sma50,
        "sma_200": sma200,
        "above_sma_20": (last> sma20) if sma20 else None,
        "above_sma_50": (last > sma50) if sma50 else None,
        "above_sma_200": (last > sma200) if sma200 else None,
    }

@tool
def compute_rsi(ticker: str, period: int = 14) -> dict:
    """Compute the Relative Strength Index (RSI) over `period` days for a
    ticker. RSI > 70 conventionally indicates overbought, < 30 oversold."""

    closes = _closes(ticker, "3mo")
    if len(closes) <= period:
        return {"ticker": ticker, "error": "insufficient price history for RSI"}

    gains, losses =[], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains .append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain=sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100/(1+rs))

    return {
        "ticker": ticker.upper(),
        "rsi": round(rsi, 2),
        "period": period,
        "signal": "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral",
    }

@tool
def compute_momentum(ticker: str, lookback_days: int=20)-> dict:
    """Compute simple price momentum (% return) over the trailing
    `lookback_days` trading days."""

    closes = _closes(ticker, "3mo")
    if len(closes) <= lookback_days:
        return {"ticker": ticker, "error": "insufficient price history for momentum"}

    start, end = closes[-lookback_days - 1], closes[-1]
    pct_return = (end - start)/start if start else 0.0
    return {
            "ticker": ticker.upper(),
            "lookback_days": lookback_days,
            "pct_return": round(pct_return, 4),
            "direction": "up" if pct_return > 0 else "down" if pct_return < 0 else "flat",
        }


TECHNICAL_TOOLS = [get_recent_price_history, compute_moving_averages, compute_rsi, compute_momentum]