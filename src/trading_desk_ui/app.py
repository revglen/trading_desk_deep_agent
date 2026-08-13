from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Deep Agent Trading Research Desk", layout="wide", page_icon="📈")

st.markdown(
    """
    <style>
    .td-card {border: 1px solid rgba(128,128,128,0.25); border-radius: 10px;
               padding: 1rem 1.25rem; margin-bottom: 0.75rem;}
    .td-badge {display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px;
                font-size: 0.78rem; font-weight: 600; letter-spacing: 0.02em;}
    .td-badge-green {background: rgba(34,197,94,0.15); color: #16a34a;}
    .td-badge-red {background: rgba(239,68,68,0.15); color: #dc2626;}
    .td-badge-amber {background: rgba(245,158,11,0.15); color: #b45309;}
    .td-badge-gray {background: rgba(128,128,128,0.15); color: #6b7280;}
    .td-badge-blue {background: rgba(59,130,246,0.15); color: #2563eb;}
    .td-label {font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
                color: rgba(128,128,128,0.9); margin-bottom: 0.15rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# API client - parses the {"error": {"code","message","request_id","details"}}
# envelope the server returns on every failure and turns it into a clean,
# readable Streamlit error instead of a raw response dump.
# ---------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, request_id: str | None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id
        self.details = details or []


def _parse_error(resp: requests.Response) -> ApiError:
    try:
        body = resp.json()
        err = body.get("error", {})
        return ApiError(
            status_code=resp.status_code,
            code=err.get("code", "unknown_error"),
            message=err.get("message", resp.text or "Unknown error"),
            request_id=err.get("request_id") or resp.headers.get("X-Request-ID"),
            details=err.get("details"),
        )
    except (ValueError, AttributeError):
        return ApiError(
            status_code=resp.status_code,
            code="unparseable_error",
            message=resp.text or f"HTTP {resp.status_code}",
            request_id=resp.headers.get("X-Request-ID"),
        )


def _show_api_error(err: ApiError) -> None:
    st.error(f"**{err.message}**")
    meta_bits = [f"code: `{err.code}`", f"status: {err.status_code}"]
    if err.request_id:
        meta_bits.append(f"request id: `{err.request_id}`")
    st.caption(" · ".join(meta_bits))
    if err.details:
        with st.expander("Details"):
            for d in err.details:
                st.write(f"- **{d.get('field', '?')}**: {d.get('issue', '')}")


def _api_get(path: str, **params) -> Any:
    resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
    if resp.status_code >= 400:
        raise _parse_error(resp)
    return resp.json()


def _api_post(path: str, json_body: dict) -> Any:
    resp = requests.post(f"{API_BASE_URL}{path}", json=json_body, timeout=180)
    if resp.status_code >= 400:
        raise _parse_error(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Presentation helpers - these replace the old st.json() dumps.
# ---------------------------------------------------------------------------

def _badge(text: str, color: str) -> str:
    return f'<span class="td-badge td-badge-{color}">{text}</span>'


def _action_badge(action: str | None) -> str:
    if action == "buy":
        return _badge("BUY", "green")
    if action == "sell":
        return _badge("SELL", "red")
    return _badge(str(action or "unknown").upper(), "gray")


def _status_badge(status_value: str | None) -> str:
    mapping = {
        "pending_approval": ("AWAITING APPROVAL", "amber"),
        "approved": ("APPROVED", "green"),
        "rejected": ("REJECTED", "red"),
        "executed": ("EXECUTED", "blue"),
        "research": ("RESEARCHING", "gray"),
        "risk_review": ("RISK REVIEW", "amber"),
    }
    label, color = mapping.get(status_value or "", (str(status_value or "unknown").upper(), "gray"))
    return _badge(label, color)


def _fmt_time(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value)


def render_proposal_card(proposal: dict) -> None:
    st.markdown('<div class="td-card">', unsafe_allow_html=True)
    top = st.columns([1.2, 1, 1, 1.3])
    with top[0]:
        st.markdown('<div class="td-label">Ticker / action</div>', unsafe_allow_html=True)
        st.markdown(
            f"### {proposal.get('ticker', '?')} &nbsp; {_action_badge(proposal.get('action'))}",
            unsafe_allow_html=True,
        )
    with top[1]:
        st.metric("Shares requested", proposal.get("shares", "—"))
    with top[2]:
        confidence = proposal.get("confidence")
        st.metric("Confidence", f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—")
    with top[3]:
        if isinstance(proposal.get("confidence"), (int, float)):
            st.progress(min(max(proposal["confidence"], 0.0), 1.0))

    st.markdown('<div class="td-label">Rationale</div>', unsafe_allow_html=True)
    st.write(proposal.get("rationale", "—"))

    risks = proposal.get("risks") or []
    if risks:
        st.markdown('<div class="td-label">Risks flagged</div>', unsafe_allow_html=True)
        for r in risks:
            st.markdown(f"- {r}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_verdict_card(verdict: dict) -> None:
    approved = verdict.get("approved")
    resized = verdict.get("resized")
    color = "green" if approved and not resized else ("amber" if approved else "red")
    label = "APPROVED" if approved and not resized else ("APPROVED (RESIZED)" if approved else "REJECTED")

    st.markdown('<div class="td-card">', unsafe_allow_html=True)
    st.markdown(f"### Risk verdict &nbsp; {_badge(label, color)}", unsafe_allow_html=True)

    cols = st.columns(3)
    cols[0].metric("Requested shares", verdict.get("original_shares", "—"))
    cols[1].metric("Approved shares", verdict.get("approved_shares", "—"))
    cols[2].metric("Resized?", "Yes" if resized else "No")

    st.markdown('<div class="td-label">Reason</div>', unsafe_allow_html=True)
    st.write(verdict.get("reason", "—"))

    risk_metrics = verdict.get("risk_metrics") or {}
    if risk_metrics:
        with st.expander("Risk metrics"):
            st.table(
                {"metric": list(risk_metrics.keys()), "value": [str(v) for v in risk_metrics.values()]}
            )
    st.markdown("</div>", unsafe_allow_html=True)


def render_execution_card(result: dict) -> None:
    status_value = result.get("status")
    color = {"submitted": "green", "duplicate_suppressed": "amber", "failed": "red", "skipped": "gray"}.get(
        status_value, "gray"
    )
    st.markdown('<div class="td-card">', unsafe_allow_html=True)
    st.markdown(f"### Execution &nbsp; {_badge(str(status_value or 'unknown').upper(), color)}", unsafe_allow_html=True)
    cols = st.columns(3)
    cols[0].metric("Ticker", result.get("ticker", "—"))
    cols[1].metric("Action", str(result.get("action", "—")).upper())
    cols[2].metric("Shares", result.get("shares", "—"))
    if result.get("broker_order_id"):
        st.caption(f"Broker order id: `{result['broker_order_id']}`")
    if result.get("detail"):
        st.caption(result["detail"])
    st.markdown("</div>", unsafe_allow_html=True)


def render_audit_event(event: dict) -> None:
    icons = {
        "agent_step": "🧠",
        "risk_verdict": "🛡️",
        "human_decision": "✅",
        "execution_submitted": "📤",
        "execution_duplicate_suppressed": "♻️",
        "execution_failed": "⚠️",
        "tool_call": "🔧",
    }
    event_type = event.get("event_type", "event")
    icon = icons.get(event_type, "•")
    header = f"{icon} **{event_type}** — {event.get('actor', 'unknown')} — {_fmt_time(event.get('created_at'))}"
    with st.expander(header):
        payload = event.get("payload_json")
        if isinstance(payload, str):
            import json as _json
            try:
                payload = _json.loads(payload)
            except ValueError:
                pass
        st.json(payload if payload is not None else {})


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f"**API:** `{API_BASE_URL}`")
    try:
        health_resp = requests.get(f"{API_BASE_URL}/healthz", timeout=5)
        if health_resp.status_code >= 400:
            raise _parse_error(health_resp)
        st.success(f"API status: {health_resp.json().get('status', 'unknown')}")
    except ApiError as err:
        _show_api_error(err)
    except requests.RequestException as exc:
        st.error(f"API unreachable: {exc}")
    st.caption(
        "Reasoning is a proposal only. Every trade still passes through the "
        "deterministic risk engine and requires an explicit human approval "
        "before PaperBroker ever submits an order."
    )

st.title("📈 Deep Agent Trading Research Desk")

tab_new, tab_review, tab_audit = st.tabs(["🆕 New research", "✅ Review & approve", "🧾 Audit trail"])

# ---------------------------------------------------------------------------
# Tab 1: kick off new research
# ---------------------------------------------------------------------------
with tab_new:
    st.subheader("Research a ticker")
    with st.form("propose_form"):
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        question = st.text_area(
            "Research question / context",
            value="Evaluate for a potential position.",
        )
        submitted = st.form_submit_button("Run analyst team", type="primary")

    if submitted and ticker:
        try:
            with st.spinner(f"Researching {ticker} (technical + fundamentals + macro/news sub-agents)..."):
                outcome = _api_post("/proposals", {"ticker": ticker, "question": question})
        except ApiError as err:
            _show_api_error(err)
        else:
            st.session_state["last_thread_id"] = outcome["thread_id"]

            if outcome["state"] == "pending_approval":
                st.success(f"Proposal ready for review. Thread ID: `{outcome['thread_id']}`")
                col1, col2 = st.columns(2)
                with col1:
                    render_proposal_card(outcome["interrupt"]["proposal"])
                with col2:
                    render_verdict_card(outcome["interrupt"]["risk_verdict"])
                st.info("Switch to the **Review & approve** tab to accept or reject this trade.")
            else:
                st.warning(f"Risk engine rejected this proposal outright (state: {outcome['state']}).")
                result = outcome.get("result") or {}
                if result.get("risk_verdict"):
                    render_verdict_card(result["risk_verdict"])
    elif submitted:
        st.warning("Enter a ticker first.")

# ---------------------------------------------------------------------------
# Tab 2: list + approve/reject pending proposals
# ---------------------------------------------------------------------------
with tab_review:
    st.subheader("Recent proposals")
    limit = st.slider("How many to show", min_value=5, max_value=100, value=20, step=5)
    if st.button("🔄 Refresh list"):
        st.rerun()

    proposals: list[dict] = []
    try:
        proposals = _api_get("/proposals", limit=limit)
    except ApiError as err:
        _show_api_error(err)

    if not proposals:
        st.caption("No proposals yet — submit one from the **New research** tab.")
    else:
        st.dataframe(
            proposals,
            use_container_width=True,
            hide_index=True,
            column_config={
                "correlation_id": st.column_config.TextColumn("Thread ID"),
                "ticker": st.column_config.TextColumn("Ticker"),
                "latest_event": st.column_config.TextColumn("Latest event"),
                "last_activity_at": st.column_config.DatetimeColumn("Last activity"),
            },
        )

    default_thread = st.session_state.get("last_thread_id", "")
    thread_id = st.text_input("Thread ID to review", value=default_thread)

    if thread_id:
        detail = None
        try:
            detail = _api_get(f"/proposals/{thread_id}")
        except ApiError as err:
            _show_api_error(err)

        if detail:
            state = detail["state"]
            st.markdown(f"**Status:** {_status_badge(state.get('status'))}", unsafe_allow_html=True)

            proposal = state.get("proposal")
            verdict = state.get("risk_verdict")
            human_decision = state.get("human_decision")
            execution_result = state.get("execution_result")

            if proposal:
                render_proposal_card(proposal)
            if verdict:
                render_verdict_card(verdict)
            if execution_result:
                render_execution_card(execution_result)

            awaiting_approval = bool(verdict and verdict.get("approved") and not human_decision)
            if awaiting_approval:
                st.markdown("---")
                st.markdown("**Approve or reject this trade**")
                with st.form("approve_form"):
                    approver = st.text_input("Your name")
                    notes = st.text_area("Notes (optional)")
                    c1, c2 = st.columns(2)
                    do_approve = c1.form_submit_button("✅ Approve", type="primary")
                    do_reject = c2.form_submit_button("🚫 Reject")

                if (do_approve or do_reject) and approver.strip():
                    decision = "approve" if do_approve else "reject"
                    try:
                        with st.spinner("Submitting decision..."):
                            result = _api_post(
                                f"/proposals/{thread_id}/approve",
                                {"decision": decision, "approver": approver, "notes": notes},
                            )
                    except ApiError as err:
                        _show_api_error(err)
                    else:
                        st.success(f"Decision recorded: **{decision}**. New state: {_status_badge(result['state'])}")
                        st.markdown(_status_badge(result["state"]), unsafe_allow_html=True)
                        exec_result = (result.get("result") or {}).get("execution_result")
                        if exec_result:
                            render_execution_card(exec_result)
                elif (do_approve or do_reject) and not approver.strip():
                    st.warning("Enter your name before approving/rejecting.")
            elif human_decision:
                st.info(
                    f"Already decided: **{human_decision.get('decision')}** "
                    f"by **{human_decision.get('approver')}**"
                    + (f" — _{human_decision.get('notes')}_" if human_decision.get("notes") else "")
                )

# ---------------------------------------------------------------------------
# Tab 3: audit trail as a readable timeline instead of a raw dataframe
# ---------------------------------------------------------------------------
with tab_audit:
    st.subheader("Audit trail")
    audit_thread_id = st.text_input("Thread ID", value=st.session_state.get("last_thread_id", ""), key="audit_tid")
    if audit_thread_id:
        try:
            detail = _api_get(f"/proposals/{audit_thread_id}")
        except ApiError as err:
            _show_api_error(err)
        else:
            trail = detail["audit_trail"]
            if not trail:
                st.caption("No audit events for this thread.")
            else:
                st.caption(f"{len(trail)} event(s), oldest first")
                for event in trail:
                    render_audit_event(event)

st.caption(f"Page rendered at {datetime.now(timezone.utc).isoformat()} UTC")