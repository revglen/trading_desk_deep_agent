from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT=Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env",
                                       extra="ignore")

    # model_name: str = Field(default="anthropic:claude-sonnet-4-5",
    #                         alias="MODEL_NAME")

    # Paper Broker
    alpaca_api_key: str | None = Field(default=None,
                                       alias="ALPACA_API_KEY")
    alpaca_secret_key: str | None = Field(default=None,
                                           alias="ALPACA_SECRET_KEY")
    alpaca_paper_base_url: str | None = Field(
        default="https://paper-api.alpaca.markets",
        alias="ALPACA_PAPER_BASE_URL"
    )

    # --- Live trading gate (see execution/live_broker.py - disabled by default) ---
    enable_live_trading: bool = Field(default=False,  alias="ENABLE_LIVE_TRADING")
    live_trading_api_key: str | None = Field(default=None, alias="LIVE_TRADING_API_KEY")
    live_trading_secret_key: str | None = Field(default=None, alias="LIVE_TRADING_SECRET_KEY")

    news_api_key: str | None = Field(default=None, alias="NEWSAPI_KEY")

    # -- Persistence ---
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    sqlite_checkpoint_path: str = Field(
        default="./data/checkpoints.sqlite", alias="SQLITE_CHECKPOINT_PATH"
    )
    sqlite_memory_store_path: str = Field(
        default="./data/memory_store.sqlite", alias="SQLITE_MEMORY_STORE_PATH"
    )

    # --- Risk-engine-owned state
    portfolio_state_path: str = Field(
        default="./data/portfolio_state.json", alias="PORTFOLIO_STATE_PATH"
    )

    app_db_path: str = Field(default="./data/app.sqlite", alias="APP_DB_PATH")

    # --- Observability ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="deep-trading-desk", alias="LANGSMITH_PROJECT")

    # --- API / UI ---
    api_host: str = Field(default="localhost", alias="TRADEBOT_API_HOST")
    api_port: int = Field(default=8000, alias="TRADEBOT_API_PORT")
    api_base_url:str = Field(default=f"http://{api_host}:{api_port}", alias="API_BASE_URL")

    # -- Model Name --
    model_name: str = Field(
        default_factory=lambda: os.getenv("GEMINI_MODEL_NAME"), alias="GEMINI_MODEL_NAME")
    model_api_key : str | None = Field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY"), alias="GOOGLE_API_KEY")    

    @property
    def using_postgres(self) -> bool:
        return bool(self.database_url)


def get_settings() -> Settings:
    return Settings()