from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from langgraph.checkpoint.base import BaseCheckpointSaver
from config import Settings

@contextmanager
def get_checkpointer(settings: Settings) -> Iterator[BaseCheckpointSaver]:
    
    if settings.using_postgres:
        from langgraph.checkpoint.postgres import PostgresSaver
        with PostgresSaver.from_conn_string(settings.database_url) as saver:
            saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.sqlite import SqliteSaver   # was: langgraph.checkpoints.sqlite import SqliteServer
        path = Path(settings.sqlite_checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(path)) as saver:   # was: SqliteServer
            saver.setup()
            yield saver
      