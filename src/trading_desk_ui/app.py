from __future__ import annotations

import os
from datetime import datetime, timezone

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Deep Agent Trading Research Desk", layout="wide")


def _api_get(path: str, **params):
    resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _api_post(path: str, json_body: dict):
    resp = requests.post(f"{API_BASE_URL}{path}", json=json_body, timeout=180)
    if resp.status_code >= 400:
        st.error(f"API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp.json()


# ---- sidebar: connection status ----
with st.sidebar:
    st.markdown(f"**API:** `{API_BASE_URL}`")
    try:
        health = requests.get(f"{API_BASE_URL}/healthz", timeout=5).json()
        st.success(f"API status: {health.get('status', 'unknown')}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"API unreachable: {exc}")
    st.caption(
        "Reasoning is a proposal only. Every trade still passes through the "
        "deterministic risk engine and requires an explicit human approval "
        "before PaperBroker ever submits an order."
    )

st.title("Deep Agent Trading Research Desk")

tab_new, tab_review, tab_audit = st.tabs(["New research", "Review & approve", "Audit trail"])

# ---- tab 1: kick off new research ----
with tab_new:
    st.subheader("Research a ticker")
    with st.form("propose_form"):
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        question = st.text_area(
            "Research question / context",
            value="Evaluate for a potential position.",
        )
        submitted = st.form_submit_button("Run analyst team")

    if submitted and ticker:
        with st.spinner(f"Researching {ticker} (technical + fundamentals + macro/news sub-agents)..."):
            outcome = _api_post("/proposals", {"ticker": ticker, "question": question})

        st.session_state["last_thread_id"] = outcome["thread_id"]

        if outcome["state"] == "pending_approval":
            st.success(f"Proposal ready for review. Thread ID: `{outcome['thread_id']}`")
            proposal = outcome["interrupt"]["proposal"]
            verdict = outcome["interrupt"]["risk_verdict"]
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Proposal (from the lead agent)**")
                st.json(proposal)
            with col2:
                st.markdown("**Risk verdict (deterministic)**")
                st.json(verdict)
            st.info("Switch to the 'Review & approve' tab to accept or reject this trade.")
        else:
            st.warning(f"Risk engine rejected this proposal outright (state: {outcome['state']}).")
            st.json(outcome.get("result", {}))

# ---- tab 2: list + approve/reject pending proposals ----
with tab_review:
    st.subheader("Recent proposals")
    limit = st.slider("How many to show", min_value=5, max_value=100, value=20, step=5)
    if st.button("Refresh list"):
        st.rerun()

    try:
        proposals = _api_get("/proposals", limit=limit)
    except Exception as exc:  # noqa: BLE001
        proposals = []
        st.error(f"Could not load proposals: {exc}")

    if not proposals:
        st.caption("No proposals yet - submit one from the 'New research' tab.")
    else:
        st.dataframe(proposals, use_container_width=True, hide_index=True)

    default_thread = st.session_state.get("last_thread_id", "")
    thread_id = st.text_input("Thread ID to review", value=default_thread)

    if thread_id:
        try:
            detail = _api_get(f"/proposals/{thread_id}")
        except Exception as exc:  # noqa: BLE001
            detail = None
            st.error(f"Could not load thread {thread_id}: {exc}")

        if detail:
            state = detail["state"]
            st.markdown(f"**Status:** `{state.get('status', 'unknown')}`")

            proposal = state.get("proposal")
            verdict = state.get("risk_verdict")
            human_decision = state.get("human_decision")
            execution_result = state.get("execution_result")

            if proposal:
                st.markdown("**Proposal**")
                st.json(proposal)
            if verdict:
                st.markdown("**Risk verdict**")
                st.json(verdict)
            if execution_result:
                st.markdown("**Execution result**")
                st.json(execution_result)

            awaiting_approval = bool(verdict and verdict.get("approved") and not human_decision)
            if awaiting_approval:
                st.markdown("---")
                st.markdown("**Approve or reject this trade**")
                with st.form("approve_form"):
                    approver = st.text_input("Your name")
                    notes = st.text_area("Notes (optional)")
                    c1, c2 = st.columns(2)
                    do_approve = c1.form_submit_button("Approve", type="primary")
                    do_reject = c2.form_submit_button("Reject")

                if (do_approve or do_reject) and approver:
                    decision = "approve" if do_approve else "reject"
                    with st.spinner("Submitting decision..."):
                        result = _api_post(
                            f"/proposals/{thread_id}/approve",
                            {"decision": decision, "approver": approver, "notes": notes},
                        )
                    st.success(f"Decision recorded: {decision}. New state: {result['state']}")
                    st.json(result["result"])
                elif (do_approve or do_reject) and not approver:
                    st.warning("Enter your name before approving/rejecting.")
            elif human_decision:
                st.info(f"Already decided: {human_decision.get('decision')} by {human_decision.get('approver')}")

# ---- tab 3: raw audit trail for a thread ----
with tab_audit:
    st.subheader("Audit trail")
    audit_thread_id = st.text_input("Thread ID", value=st.session_state.get("last_thread_id", ""), key="audit_tid")
    if audit_thread_id:
        try:
            detail = _api_get(f"/proposals/{audit_thread_id}")
            trail = detail["audit_trail"]
            if trail:
                st.dataframe(trail, use_container_width=True, hide_index=True)
            else:
                st.caption("No audit events for this thread.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load audit trail: {exc}")

st.caption(f"Page rendered at {datetime.now(timezone.utc).isoformat()} UTC")
