from __future__ import annotations
import json
from datetime import datetime, timezone

from sqlalchemy import func, insert, select
from sqlalchemy import Engine

from observability.logging_config import StructuredLog   #get_logger
from persistence.db import DB_Engine # audit_log

class AuditLogger:
    _logger=StructuredLog.get_logger("audit")

    def __init__(self, engine:Engine):
        self.engine=engine
        self.db_engine = DB_Engine()

    def _write(self, correlation_id: str, event_type: str, actor: str, payload: dict) -> None:
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(
                insert(self.db_engine.get_audit_log()).values(
                    correlation_id=correlation_id,
                    event_type=event_type,
                    actor=actor,
                    payload_json=json.dumps(payload, default=str),
                    created_at=now
                )
            )

        AuditLogger._logger.info(event_type, actor=actor, correlation_id=correlation_id, **payload)

    def log_agent_step(self, correlation_id: str, node: str, detail: dict) -> None:
        self._write(correlation_id, "agent_step", node, detail)

    def log_tool_call(self, correlation_id: str, tool_name: str, args: dict, result_summary: str) -> None:
        self.write(
            correlation_id, "tool_call", 
            tool_name, 
            {
                "args": args, 
                "result_summary": result_summary 
            }
        )

    def log_risk_verdict(self, correlation_id: str, verdict: dict) -> None:
        self._write(correlation_id, "risk_verdict", "risk_engine", verdict)

    def log_human_decision(self, correlation_id: str, decision: str, approver: str | None, notes: str) -> None:
        self._write(
            correlation_id,
            "human_decision",
            approver or "unknown",
            {
                "decision": decision, 
                "notes": notes
            },
        )

    def log_execution(self, correlation_id: str, event: str, detail: dict) -> None:
        self._write(correlation_id, f"execution_{event}", "broker", detail)

    def get_trail(self, correlation_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows= conn.execute(
                select (self.db_engine.get_audit_log())
                .where(self.db_engine.get_audit_log().c.correlation_id == correlation_id)
                .order_by(self.db_engine.get_audit_log().c.id.asc())
            ).mappings().all()

        return [dict(r) for r in rows]

    def list_recent(self, limit: int=50) -> list[dict]:
        with self.engine.connect() as conn:
            recent_ids =conn.execute(
                select(self.db_engine.get_audit_log().c.correlation_id, func.max(self.db_engine.get_audit_log().c.created_at).label("last_at"))
                .group_by(self.db_engine.get_audit_log().c.correlation_id)
                .order_by(func.max(self.db_engine.get_audit_log().c.created_at).desc())
                .limit(limit)
            ).mappings().all()

        summaries=[]
        for row in recent_ids:
            correlation_id = row["correlation_id"]
            trail = self.get_trail(correlation_id)
            ticker=None
            for event in trail:
                if event["event_type"] == "agent_step":
                    payload = json.loads(event["payload_json"])
                    if payload.get("phase") == "start" and payload.get("ticker"):
                        ticker = payload["ticker"]
                        break   
    
            latest_event = trail[-1]["event_type"] if trail else "unknown"
            summaries.append(
                {
                    "correlation_id": correlation_id,
                    "ticker": ticker,
                    "latest_event": latest_event,
                    "last_activity_at": row["last_at"],
                }
            )

        return summaries