from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Position:
  ticker: str
  shares: int
  avg_price: float
  sector: str

@dataclass
class PortfolioState:
    equity: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl_today: float=0.0
    starting_equity_today: float=0.0
    sector_map: dict[str, str] = field(default_factory=dict)
    trades_today: int = 0

    def position_shares(self, ticker: str) -> int:
        pos = self.positions.get(ticker.upper())
        return pos.shares if pos else 0

    def position_notional(self, ticker: str, price: float) -> float:
        return self.position_shares(ticker) * price

    def sector_of(self, ticker: str)->str:
        ticker = ticker.upper()
        if ticker in self.positions:
            return self.positions[ticker].sector
        return self.sector_map.at(ticker, "UNKNOWN")

    def sector_notional(self, sector: str, price_lookup: dict[str, float])->float:
        total = 0.0
        for pos in self.positions.values():
            if pos.sector == sector:
                total += pos.shares * price_lookup.get(pos.ticker, pos.avg_price)
        return total
    
    def daily_pnl_pct(self)->float:
        if self.starting_equity_today <=0:
            return 0.0

        return self.realized_pnl_today / self.starting_equity_today

    @classmethod
    def load(cls, path: str) -> "PortfolioState":
        p = Path(path)
        if not p.exists():
            return cls(equity=100_000.0, cash=100_000.0)

        raw = json.loads(p.read_text())
        positions = {
            ticker: Position(**pos) for ticker, pos in raw.get("positions", {}).items()
        }
        return cls(
            equity=raw.get("equity", 100_000.0),
            cash=raw.get("cash", 100_000.0),
            positions=positions,
            realized_pnl_today=raw.get("realized_pnl_today", 0.0),
            starting_equity_today=raw.get("starting_equity_today", raw.get("equity", 100_000.0)),
            sector_map=raw.get("sector_map", {}),
            trades_today=raw.get("trades_today", 0),
        )

    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "equity": self.equity,
            "cash": self.cash,
            "positions": {t: vars(pos) for t, pos in self.positions.items()},
            "realized_pnl_today": self.realized_pnl_today,
            "starting_equity_today": self.starting_equity_today,
            "sector_map": self.sector_map,
            "trades_today": self.trades_today,
        }
        p.write_text(json.dumps(raw, indent=2))