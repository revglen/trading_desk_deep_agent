"""
Idempotency store for order submission, backed by SQLAlchemy Core so the
same code targets SQLite (local dev) or Postgres (DATABASE_URL set, see
persistence/db.py).

Guarantees that retried/duplicate submission attempts for the same logical
order (same correlation_id + ticker + action + approved_shares) never result
in two broker orders. Uses the table's primary-key constraint as the source
of truth rather than a check-then-act race.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from persistence.db import DB_Engine #idempotent_orders


class DuplicateSubmissionError(Exception):
    """Raised internally when a race is caught by the primary-key constraint."""


class IdempotencyStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def make_key(correlation_id: str, ticker: str, action: str, shares: int) -> str:
        raw = f"{correlation_id}:{ticker.upper()}:{action}:{shares}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, idempotency_key: str) -> dict | None:
        idempotent_orders = DB_Engine().get_idempotency_orders()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(idempotent_orders).where(idempotent_orders.c.idempotency_key == idempotency_key)
            ).mappings().first()
            return dict(row) if row else None

    def try_reserve(self, idempotency_key: str, payload: dict) -> bool:
        """Atomically claim this idempotency key. Returns True if this call
        won the race and should proceed to submit an order; False if the
        key already existed (a prior attempt already owns it)."""
        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(idempotent_orders).values(
                        idempotency_key=idempotency_key,
                        status="pending",
                        payload_json=json.dumps(payload),
                        created_at=now,
                        updated_at=now,
                    )
                )
            return True
        except IntegrityError:
            return False

    def mark_submitted(self, idempotency_key: str, broker_order_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(idempotent_orders)
                .where(idempotent_orders.c.idempotency_key == idempotency_key)
                .values(
                    status="submitted",
                    broker_order_id=broker_order_id,
                    updated_at=datetime.now(timezone.utc),
                )
            )

    def mark_failed(self, idempotency_key: str, error: str) -> None:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(idempotent_orders.c.payload_json).where(
                    idempotent_orders.c.idempotency_key == idempotency_key
                )
            ).first()
            payload = json.loads(row[0]) if row else {}
            payload["error"] = error
            conn.execute(
                update(idempotent_orders)
                .where(idempotent_orders.c.idempotency_key == idempotency_key)
                .values(
                    status="failed",
                    payload_json=json.dumps(payload),
                    updated_at=datetime.now(timezone.utc),
                )
            )
