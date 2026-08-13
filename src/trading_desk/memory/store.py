from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from langgraph.store.base import BaseStore
from config import Settings

SECTOR_NOTES_NS = "sector_notes"
TRADE_LESSONS_NS = "trade_lessons"
PAST_RATIONALE_NS = "past_rationale"

@contextmanager
def get_memory_store(settings: Settings) -> Iterator[BaseStore]:
    if settings.using_postgres:
        from langgraph.store.postgres import PostgresStore
        with PostgresStore.from_conn_string(settings.database_url) as store:
            store.setup()
            yield store
    else:
        from langgraph.store.sqlite import SqliteStore

        path = Path(settings.sqlite_memory_store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with SqliteStore.from_conn_string(str(path)) as store:
            store.setup()
            yield store

def record_trade_lesson(store: BaseStore, ticker: str, lesson: str) -> None:
    import uuid

    store.put(
        (TRADE_LESSONS_NS, ticker.upper()),
        str(uuid.uuid4()),
        {"lesson": lesson},
    )

def get_sector_notes(store: BaseStore, sector: str) -> list[dict]:
    items = store.search((SECTOR_NOTES_NS, sector.upper()))
    return [item.value for item in items]