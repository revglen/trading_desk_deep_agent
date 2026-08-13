from __future__ import annotations
import hashlib
import random

from schemas import MarketSnapshot

_SECTOR_MAP = {
    "AAPL": "TECH", "MSFT": "TECH", "GOOGL": "TECH", "NVDA": "TECH", "META": "TECH",
    "AMZN": "CONSUMER_DISCRETIONARY", "TSLA": "CONSUMER_DISCRETIONARY",
    "JPM": "FINANCIALS", "BAC": "FINANCIALS", "GS": "FINANCIALS",
    "XOM": "ENERGY", "CVX": "ENERGY",
    "JNJ": "HEALTHCARE", "UNH": "HEALTHCARE", "PFE": "HEALTHCARE",
}

def _seeded_rng(ticker: str, salt: str="") -> random.Random:
    seed = int(hashlib.sha256(f"{ticker}:{salt}".encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)

def _mock_price(ticker: str) -> float:
    rng = _seeded_rng(ticker, "price")
    return round(rng.uniform(20, 500), 2)

def _mock_daily_volatility_pct(ticker: str) -> float:
  rng = _seeded_rng(ticker, "vol")
  return round(rng.uniform(0.012, 0.05), 4)

def get_market_snapshot(ticker:str) -> MarketSnapshot:
    ticker = ticker.upper()
    try:
        import yfinance as yf
        
        hist = yf.ticker(ticker).history(period="1mo")
        if hist is None or hist.empty:
            raise ValueError("empty history")

        price = float(hist["Close"].iloc[-1])
        daily_returns = hist["Close"].pct_change().dropna()

        daily_vol = float(daily_returns.std()) if len(daily_returns) > 1 else 0.02
        sector = _SECTOR_MAP.get(ticker, "unknown")
        return MarketSnapshot(
                    ticker=ticker, price=price, daily_volatility_pct=abs(daily_vol), sector=sector, source="live"
                )
    except Exception:
        return MarketSnapshot(
            ticker=ticker,
            price = _mock_price(ticker),
            daily_volatility_pct = _mock_daily_volatility_pct(ticker),
            sector=_SECTOR_MAP.get(ticker, "UNKNOWN"),
            source="mock",
        )

def get_price_history(ticker: str, period: str="6mo") -> list[dict]:
    ticker = ticker.upper()
    try:
        import yfinance as yf
        
        hist = yf.ticker(ticker).history(period=period)
        if hist is None or hist.empty:
            raise ValueError("Empty History")

        rows = []
        for idx, row in hist.iterrows():
            rows.append(
                {
                    "date": str(idx.date()),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                }
            )
        return rows
    except Exception:
        rng = _seeded_rng(ticker, "history")
        price = _mock_price(ticker)
        rows = []
        for i in range(30):
            drift = rng.uniform(-0.02, 0.02)
            price = max(price * (1 + drift), 1.0)
            rows.append(
                {
                    "date": f"mock-day-{i}",
                    "open": round(price * 0.995, 2),
                    "high": round(price * 1.01, 2),
                    "low": round(price * 0.99, 2),
                    "close": round(price, 2),
                    "volume": rng.randint(1_000_000, 20_000_000),
                    "note": "SYNTHETIC MOCK DATA - yfinance unavailable/offline",
                }
            )
        return rows