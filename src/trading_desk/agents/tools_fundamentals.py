from __future__ import annotations
from langchain_core.tools import tool

from agents.market_data import _seeded_rng

def _yf_info(ticker: str) -> dict | None:
    try:
        import yfinance as yf
        info=yf.ticker(ticker.upper()).info
        return info if info else None
    except Exception:
        return None

@tool
def get_valuation_metrics(ticker: str) -> dict:
    """Get valuation metrics for a ticker: trailing/forward P/E, P/B,
    EV/EBITDA, PEG ratio."""

    info = _yf_info(ticker)
    if info:
        return {
            "ticker": ticker.upper(),
            "source": "live",
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_boo": info.get("priceToBook"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "peg_ratio": info.get("pegRatio"),
        }

    rng = _seeded_rng(ticker, "valuation")
    return {
        "ticker": ticker.upper(),
        "source": "mock",
        "trailing_pe": round(rng.uniform(10, 40), 1),
        "forward_pe": round(rng.uniform(9, 35), 1),
        "price_to_book": round(rng.uniform(1, 15), 1),
        "ev_to_ebitda": round(rng.uniform(6, 25), 1),
        "peg_ratio": round(rng.uniform(0.8, 3.0), 2),
    }

@tool
def get_profitability_metrics(ticker: str) -> dict:
    """Get profitability metrics for a ticker: gross/operating/net margin,
    ROE, ROA."""

    info = _yf_info(ticker)
    if info:
        return {
            "ticker": ticker.upper(),
            "source": "live",
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "met_margin": info.get("profitMargins"),
            "return_on_equity": info.get("returnOnEquity"),
            "return_on_assets": info.get("returnOnAssets")
        }
  
    rng=_seeded_rng(ticker, "profitability")
    return {
        "ticker": ticker.upper(),
        "source": "mock",
        "gross_margin": round(rng.uniform(0.25, 0.7), 3),
        "operating_margin": round(rng.uniform(0.05, 0.35), 3),
        "net_margin": round(rng.uniform(0.02, 0.28), 3),
        "return_on_equity": round(rng.uniform(0.05, 0.4), 3),
        "return_on_assets": round(rng.uniform(0.02, 0.2), 3),
    }

@tool
def get_debt_metrics(ticker: str) -> dict:
    """Get debt/leverage metrics for a ticker: debt-to-equity, current
    ratio, quick ratio, interest coverage."""
    info =_yf_info(ticker)
    if info:
        return {
            "ticker": ticker.upper(),
            "source": "live",
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio")
        }

    rng = _seeded_rng(ticker, "debt")
    return {
        "ticker": ticker.upper(),
        "source": "mock",
        "debt_to_equity": round(rng.uniform(0.1, 2.5), 2),
        "current_ratio": round(rng.uniform(0.8, 3.0), 2),
        "quick_ratio": round(rng.uniform(0.5, 2.5), 2),
    }


FUNDAMENTALS_TOOLS = [get_valuation_metrics, get_profitability_metrics, get_debt_metrics]
