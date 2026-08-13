from __future__ import annotations
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine
from sqlalchemy.engine import Engine

from config import Settings

class DB_Engine:
    def __init__(self):
        self.metadata = MetaData()
        self.audit_log = Table(
            "audit_log",
            self.metadata,
            Column("id", Integer, primary_key=True),
            Column("correlation_id", String(64), nullable=False, index=True),
            Column("event_type", String(64), nullable=False, index=True),
            Column("actor", String(128), nullable=False),
            Column("payload_json", Text, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False)
        )

        self.idempotent_orders = Table(
            "idempotent_orders",
            self.metadata,
            Column("idempotency_key", String(64), primary_key=True),
            Column("status", String(32), nullable=False),
            Column("broker_order_id", String(128), nullable=True),
            Column("payload_json", Text, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

    def make_engine(self, settings: Settings) -> Engine:
        url = settings.database_url or f"sqlite:///{settings.app_db_path}"
        if url.startswith("SQLite"):
            from pathlib import Path            
            db_file=url.split("SQLite:///", 1)[-1]
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
            connect_args={"check_same_thread": False}
        else:
            connect_args={}

        engine=create_engine(url, connect_args=connect_args, future=True)
        self.metadata.create_all(engine)
        return engine

    def get_audit_log(self):
        return self.audit_log

    def get_idempotency_orders(self):
        return self.idempotent_orders