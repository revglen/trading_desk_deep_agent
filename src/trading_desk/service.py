from __future__ import annotations
from contextlib import ExitStack
from typing import Any
from langgraph.types import Command

from agents.lead_agent import *
from config import Settings
from execution.idempotency import IdempotencyStore
from execution.paper_broker import PaperBroker
from memory.store import *
from observability.audit import AuditLogger
from observability.logging_config import *
from persistence.checkpointer import *
from persistence.db import DB_Engine
from workflow.graph import build_graph, new_correlation_id

class Service:
    def __init__(self):
        self.db_engine=DB_Engine()

    def _open_graph(self, settings: Settings, stack: ExitStack):
        checkpointer = stack.enter_context(get_checkpointer(settings))
        store = stack.enter_context(get_memory_store(settings))

        engine = self.db_engine.make_engine(settings)
        audit = AuditLogger(engine)
        lead_agent = build_trading_desk_agent(settings, checkpointer=checkpointer, store=store)
        idempotency_store = IdempotencyStore(engine)
        broker = PaperBroker(
            idempotency_store=idempotency_store,
            audit=audit,
            api_key=settings.alpaca_api_key,
            secret_key = settings.alpaca_secret_key
        )

        graph=build_graph(
            lead_agent=lead_agent,
            broker = broker,
            audit = audit,
            portfolio_state_path=settings.portfolio_state_path,
            checkpointer=checkpointer,
        )

        return graph, audit

    def propose_trade(self, settings: Settings, ticker: str, question: str) -> dict[str, Any]:
        correlation_id = new_correlation_id()
        StructuredLog.set_correlation_id(correlation_id)

        with ExitStack() as stack:
            graph, _audit = self._open_graph(settings, stack)
            config = {"configurable": {"thread_id": correlation_id}}
            result = graph.invoke(
                {
                    "correlation_id": correlation_id,
                    "ticker": ticker.upper(),
                    "user_request": question,
                    "status": "research"
                },
                config=config
            )

        if "__interrupt__" in result:
            payload=result["__interrupt__"][0].value

            if "__interrupt__" in result:
                payload = result["__interrupt__"][0].value
                return {"thread_id": correlation_id, 
                        "state": "pending_approval", 
                        "interrupt": payload}

        return {"thread_id": correlation_id, 
                "state": result.get("status", "unknown"), 
                "result": result}


    def approve_trade(self, settings: Settings, thread_id: str, decision: str, approver: str, notes: str = "") -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ValueError("Decsion must be Approved")

        StructuredLog.set_correlation_id(thread_id)

        with ExitStack() as stack:
            graph, audit=self._open_graph(settings, stack)
            config = {"configurable": {"thread_id": thread_id}}
            result = graph.invoke(
                Command(resume={"decision": decision, "approver": approver, "notes": notes}),
                  config= config
            )

        return {"thread_id": thread_id, "state": result.get("status", "unknown"), "result":result}


    def get_status(self, settings: Settings, thread_id: str) -> dict[str, Any] | None:
        with get_checkpointer(settings) as checkpointer:
            snapshot=checkpointer.get_tuple({"configurable": {"thread_id": thread_id}})
            if snapshot is None:
                return None
            state =snapshot.checkpoint.get("channel_values", {})

        engine = self.db_engine.make_engine(settings)
        audit=AuditLogger(engine)
        return {"thread_id": thread_id, "state": state, "audit_trail": audit.get_trail(thread_id)}

    def list_recent_proposals(self, settings: Settings, limit: int = 50) -> list[dict[str, Any]]:
        engine = self.db_engine.make_engine(settings)
        audit = AuditLogger(engine)
        return audit.list_recent(limit=limit)
