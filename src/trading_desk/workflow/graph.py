from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.lead_agent import generate_trade_proposal
from agents.market_data import get_market_snapshot
from execution.paper_broker import PaperBroker
from observability import metrics
from observability.audit import AuditLogger
from risk_engine.engine import RiskLimits, validate_proposal
from risk_engine.portfolio_state import PortfolioState
from schemas import ExecutionResult, MarketSnapshot, RiskVerdict, TradeProposal
from workflow.state import TradingDeskState

def build_graph(
    *,
    lead_agent,
    broker: PaperBroker,
    audit: AuditLogger,
    portfolio_state_path: str,
    risk_limits: RiskLimits | None=None,
    checkpointer
):
    risk_limits = risk_limits or RiskLimits()

    def run_analyst_team(state: TradingDeskState)->dict:
        correlation_id = state["correlation_id"]
        audit.log_agent_step(correlation_id, 
                            "run_analyst_team",  
                            {
                                "phase": "start", 
                                "ticker": state["ticker"]
                            }
                        )

        proposal: TradeProposal=generate_trade_proposal(
            lead_agent,
            thread_id=f"{correlation_id}:analyst-team",
            ticker=state["ticker"],
            question=state["user_request"]
        )
        
        audit.log_agent_step(
            correlation_id, "run_analyst_team", 
            {
                "phase": "complete",
                "proposal": proposal.model_dump()
            }
        )

        metrics.PROPOSAL_TOTAL.labels(ticker=proposal.ticker, action=proposal.action).inc()
        return {
                "proposal": proposal.model_dump(), 
                "status": "risk_review"
            }

    def risk_check(state: TradingDeskState) -> dict:
        correlation_id=state["correlation_id"]
        proposal=TradeProposal.model_validate(state["proposal"])

        market: MarketSnapshot =get_market_snapshot(proposal.ticker)
        portfolio = PortfolioState.load(portfolio_state_path)

        verdict: RiskVerdict = validate_proposal(proposal, portfolio, market, risk_limits)
        audit.log_risk_verdict(correlation_id, verdict.model_dump())

        metrics.RISK_VERDICTS_TOTAL.labels(approved=str(verdict.approved), resized=str(verdict.resized)).inc()
        if not verdict.approved:
            metrics.RISK_REJECTIONS_TOTAL.labels(ticker=proposal.ticker).inc()

        return {
            "risk_verdict": verdict.model_dump(),
            "status": "pending_approval" if verdict.approved else "rejected",
        }

    def human_approval(state: TradingDeskState) -> dict:
        correlation_id = state["correlation_id"]
        proposal=state["proposal"]
        verdict = state["risk_verdict"]

        decision: dict[str, Any]=interrupt(
            {
                "type": "trade_approval_requirer",
                "correlation_id": correlation_id,
                "proposal": proposal,
                "risk_verdict": verdict,
                "instructions": "Resume this thread with {'decision': 'approve'|'reject', "
                "'approver': '<name>', 'notes': '<optional>'}",
            }
        )

        audit.log_human_decision(
            correlation_id,
            decision.get("decision", "unknown"),
            decision.get("approver"),
            decision.get("notes", "")
        )

        metrics.HUMAN_DECISIONS_TOTAL.labels(decision.get("decision", "unknown")).inc()
        _observe_approval_latency(correlation_id)

        return {
                "human_decision": decision, 
                "status": "approved" if decision.get("decision") == "approve" else "rejected"
            }

    def _observe_approval_latency(correlation_id: str)-> None:
        try:
            risk_event=next(
                e for e in audit.get_trail(correlation_id) if e["event_type"] == "risk_verdict"
            )
            risk_time =risk_event["created_at"]
            if isinstance(risk_time, str):
                risk_time = datetime.fromisoformat(risk_time)
            if risk_time.tzinfo is None:
                risk_time=risk_time.replace(tzinfo=timezone.utc)

            elapsed=(datetime.now(timezone.utc) - risk_time).total_seconds()
            if elapsed >=0:
                metrics.APPROVAL_LATENCY_SECONDS.observe(elapsed)
        except StopIteration:
            pass

    def execute_trade(state: TradingDeskState) -> dict:
        correlation_id = state["correlation_id"]
        proposal = TradeProposal.model_validate(state["proposal"])
        verdict = RiskVerdict.model_validate(state["risk_verdict"])
        result: ExecutionResult =broker.submit_order(proposal, verdict, correlation_id)
        return {
            "execution_result": result.model_dump(), 
            "status": "executed"
        }

    def risk_gate(state: TradingDeskState) -> str:
        return "human_approval" if state["risk_verdict"]["approved"] else END
        
    def approval_gate(state: TradingDeskState) -> str:
        return "execute_trade" if state["human_decision"]["decision"] == "approve" else END

    graph = StateGraph(TradingDeskState)
    graph.add_node("run_analyst_team", run_analyst_team)
    graph.add_node("risk_check", risk_check)
    graph.add_node("human_approval", human_approval)
    graph.add_node("execute_trade", execute_trade)

    graph.add_edge(START, "run_analyst_team")
    graph.add_edge("run_analyst_team", "risk_check")
    graph.add_conditional_edges("risk_check", risk_gate, {"human_approval": "human_approval", END: END})
    graph.add_conditional_edges("human_approval", approval_gate, {"execute_trade": "execute_trade", END: END})
    graph.add_edge("execute_trade", END)

    return graph.compile(checkpointer=checkpointer)

def new_correlation_id() -> str:
    return str(uuid.uuid4())
