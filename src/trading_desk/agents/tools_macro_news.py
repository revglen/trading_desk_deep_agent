from __future__ import annotations
from langchain_core.tools import tool

from agents.market_data import _seeded_rng
from config import get_settings

_MOCK_HEADLINE_TEMPLATES = [
    "{ticker} announces expanded share buyback program",
    "Analysts split on {ticker} after mixed guidance commentary",
    "{ticker} supplier repots shipments delays, watch for margin impact",
    "Sector rotation narrative weighs on names including {ticker}",
    "{ticker} included in latest institutional 13F accumulation screen"
]

@tool
def get_recent_news(ticker: str, max_articles: int=5) -> list[dict]:
    """Get recent news headlines relevant to a ticker, with source and
        published date where available."""

    settings = get_settings()
    if settings.news_api_key:
        try:
            import requests
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": ticker,
                    "sortBy": "publishedAt",
                    "pageSize": max_articles,
                    "apiKey": settings.news_api_key
                },
                timeout=10
            )

            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            return [
                {
                    "title": a.get("title"),
                    "source": (a.get("source") or {}).get("name"),
                    "published_at": a.get("publishedAt"),
                    "url": a.get("url"),
                }
                for a in articles[:max_articles]
            ]
        except Exception:
            pass
            
    rng = _seeded_rng(ticker, "news")
    return [
        {
            "title": tmpl.format(ticker=ticker.upper()),
            "source": "MOCK_NEWSWIRE",
            "published_at": None,
            "url": None,
            "note": "SYNTHETIC MOCK DATA - NEWSAPI_KEY not configured or request failed",
        }
        for tmpl in rng.sample(_MOCK_HEADLINE_TEMPLATES, k=min(max_articles, len(_MOCK_HEADLINE_TEMPLATES)))
    ]


@tool
def get_macro_snapshot() -> dict:
    """Get a snapshot of current macro indicators relevant to equity
        positioning: 10y treasury yield, VIX level, and a qualitative
        regime label."""

    settings = get_settings()
    rng = _seeded_rng("MACRO", "snapshot")
    vix = round(rng.uniform(12,28),1)
    return {
            "ten_year_yield_pct": round(rng.uniform(3.5, 5.0), 2),
            "vix": vix,
            "regime": "risk-off" if vix > 22 else "risk-on" if vix < 16 else "neutral",
            "source": "mock",
            "note": "SYNTHETIC MOCK DATA - wire in FRED/vendor API for production macro data",
        }


MACRO_NEWS_TOOLS = [get_recent_news, get_macro_snapshot]