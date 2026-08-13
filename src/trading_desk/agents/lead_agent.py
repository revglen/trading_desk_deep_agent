from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from langchain.chat_models import init_chat_model
from config import Settings, SKILLS_DIR

try:
    from deepagents import SubAgent, create_deep_agent
except ImportError:
    from deepagents import create_agent
    from deepagents.middleware.subagents import SubAgent

from agents.tools_fundamentals import FUNDAMENTALS_TOOLS
from agents.tools_macro_news import MACRO_NEWS_TOOLS
from agents.tools_technical import TECHNICAL_TOOLS
from schemas import TradeProposal

LEAD_SYSTEM_PROMPT = """\
You are the lead analyst on a trading research desk.Your job is to REASON \
and PROPOSE - you have no ability to execute trades, move money, or modify \
risk limits, and you must never claim otherwise. Actual execution only over \
happens after a separate, deterministic risk engine and an explicit human \
approval step outside your control.

For every research request:
1. Use 1write_todos` to lay out your research pain before diving in.
2. Delegate domain research to your sub-agents via task tools:
  - technical-analyst: price/volume/momentum
  - fundamental-analyst: valuation, profitability, debt
  - macro-news-analyst: recent news and macro context
Do not try to answer technical, fundamental, or macro questions \
yourself with guessed numbers - delegate and use the tool-returned data.
3. Check whether the "earnings-risk" skill applies (upcoming earnings /
   stale or volatile fundamentals) and the "research-brief" skill for how
   to structure your final written rationale. Read a skill's Skill.md via 
   the filesystem tools when you decide it applies - do not assume its 
   contents from the name alone.
5. Write a scratch draft of your brief to the virtual filesystem (e.g. 
   `draft_brief.md`) before finalising, so your reasoning is inspectable.
5. Produce your final answer as a TradeProposal: ticker, action (buy/sell), 
   shares, rationale, confidence (0-1), and a concrete, non-empty list of 
   your risks, `confidence` should reflect actual agreement/disagreement across 
   your subagents' findings' not a default value.
6. Never state or imply that a trade has been placed, sized against a 
   portfolio or approved - those are downstream, deterministic steps you 
   do not perform and cannot see the outcome of.
"""

TECHNICAL_SUBAGENT_PROMPT = """\
You are a technical analyst. Use the price/volume/momentum tools to \
characterise trend, moving-average posture, RSI, and recent momentum for \ 
the requested ticker. Report specific number, not vague impressions. You \
never propose trade yourself - you hand findings back to the load analyst.
"""

FUNDAMENTALS_SUBAGENT_PROMPT = """\
You are the fundamentals analyst. Use your valuation/profitability/debt \
tools to assess whether the requested ticker looks cheap/expensive and \
financially healthy relative to typical ranges. Report specific numbers. \
You never propose trades yourself - you hand findings back to the lead \
analyst.
"""

MACRO_NEWS_SUBAGENT_PROMPT = """\
You are the macro/news analyst. Use your news and macro-snapshot tools to \
surface anything - recent headlines, macro regime - that could move the \
requested ticker in the near term. Flag if data returned is mock/synthetic \
so the lead analyst can weight it appropriately in confidence. You never \
propose trades yourself - you hand findings back to the lead analyst.
"""

def _skill_paths() -> list[str]:
  return [
    str(SKILLS_DIR / "research-brief"),
    str(SKILLS_DIR / "earnings-risk")
  ]

def build_trading_desk_agent(
        settings: Settings,
        checkpointer: BaseCheckpointSaver | None = None,
        store: BaseStore | None=None
    ):

    technical_subagent =SubAgent(
        name="technical-analyst",
        description=(
            "Delegate to this sub-agent for price/volume/momentum analysis of a "
            "ticker (moving averages, RSI, momentum)."
        ),
        system_prompt = TECHNICAL_SUBAGENT_PROMPT,
        tools=TECHNICAL_TOOLS
    )

    fundamental_subagent = SubAgent(
        name = "fundamental-analyst",
        description=(
                "Delegate to this sub-agent for valuation, profitability, and debt/"
                "leverage analysis of a ticker."
            ),
        system_prompt=FUNDAMENTALS_SUBAGENT_PROMPT,
        tools=FUNDAMENTALS_TOOLS
    )

    macro_news_subagent = SubAgent(
    name="macro-news-analyst",
    description=(
                "Delegate to this sub-agent for recent news and macro/regime context "
                "relevant to a ticker."
            ),
    system_prompt=MACRO_NEWS_SUBAGENT_PROMPT,
    tools = MACRO_NEWS_TOOLS
    )

    model = init_chat_model(
        model=settings.model_name,
        model_provider="google_genai",
        api_key=settings.model_api_key,
    )

    agent = create_deep_agent(
        model=model,
        system_prompt=LEAD_SYSTEM_PROMPT,
        subagents = [technical_subagent, fundamental_subagent, macro_news_subagent],
        skills = _skill_paths(),
        response_format=TradeProposal,
        checkpointer = checkpointer,
        store =store,
        name="trading-desk-lead-analyst",
    )

    return agent

def generate_trade_proposal (agent, *, thread_id: str, ticker: str, question: str) -> TradeProposal:

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"Research {ticker} and produce a trade proposal. Context: {question}",
                }
            ]
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    structured = result.get("structured_response")
    if structured is None:
        raise RuntimeError(
            "Lead agent did not produce a structured_response. This should be impossible with "
            "response_format=TradeProposal set - treat as a bug, not something to work around by "
            "parsing free text."
        )

    if isinstance(structured, TradeProposal):
        return structured

    return TradeProposal.model_validate(structured)