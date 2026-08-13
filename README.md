# Trading Desk Deep Agent — Architecture

An AI-assisted trading research desk. An LLM-driven analyst team researches a
ticker and drafts a trade proposal; a deterministic risk engine sizes or
rejects it; a human must explicitly approve it; only then does a paper
broker submit the order. No step in this pipeline can move money (even
simulated money) without a human in the loop.

## 1. Functional flow

What happens, in plain terms, from a research request to a filled (paper)
order.

```mermaid
flowchart TD
    A([User asks: research this ticker]) --> B[Lead agent delegates research]

    B --> B1[Technical analyst]
    B --> B2[Fundamentals analyst]
    B --> B3[Macro / news analyst]

    B1 --> C[Trade Proposal<br/>ticker, action, shares, rationale, confidence, risks]
    B2 --> C
    B3 --> C

    C --> D{Risk engine review<br/>deterministic, no LLM}
    D -->|Approved as-is| E[["Pause — wait for a human"]]
    D -->|Approved, resized| E
    D -->|Rejected| Z([Workflow ends — no trade])

    E --> F{Human decision}
    F -->|Approve| G[Paper broker submits order]
    F -->|Reject| Z

    G --> H([Order filled — paper trading only])

    C -.logged.-> AUDIT[(Audit log)]
    D -.logged.-> AUDIT
    F -.logged.-> AUDIT
    G -.logged.-> AUDIT
```

**Key guardrail:** the LLM only ever produces steps B → C. It has no path
to G — order submission — without passing through the deterministic risk
engine (D) *and* an explicit human decision (F).

## 2. Technical flow

How that functional flow maps onto the actual codebase — layers, modules,
and where each piece lives.

```mermaid
flowchart TD
    subgraph Interface["Interface layer"]
        API["api/main.py<br/>(FastAPI + exception handlers)"]
        CLI["cli.py<br/>(Typer)"]
    end

    Service["service.py<br/>(Service class — opens the graph, wires dependencies)"]

    subgraph Orchestration["Orchestration layer — workflow/graph.py"]
        direction LR
        N1["run_analyst_team"] --> N2["risk_check"]
        N2 --> N3["human_approval<br/>(interrupt — pauses here)"]
        N3 --> N4["execute_trade"]
    end

    subgraph Agent["Agent layer — agents/"]
        LEAD["lead_agent.py<br/>(deepagents lead agent)"]
        TECH["tools_technical.py"]
        FUND["tools_fundamentals.py"]
        MACRO["tools_macro_news.py"]
        MKT["market_data.py"]
        LEAD --> TECH
        LEAD --> FUND
        LEAD --> MACRO
        TECH --> MKT
        FUND --> MKT
        MACRO --> MKT
    end

    subgraph Domain["Domain layer — deterministic, no LLM"]
        RISK["risk_engine/engine.py"]
        PORT["risk_engine/portfolio_state.py"]
        BROKER["execution/paper_broker.py<br/>(Alpaca paper / DryRunClient)"]
        IDEM["execution/idempotency.py"]
        RISK --> PORT
        BROKER --> IDEM
    end

    subgraph Persistence["Persistence"]
        CKPT["persistence/checkpointer.py<br/>(LangGraph state — SQLite/Postgres)"]
        DB["persistence/db.py<br/>(audit_log, idempotent_orders tables)"]
        MEM["memory/store.py<br/>(agent long-term memory)"]
    end

    subgraph Observability["Observability"]
        LOG["observability/logging_config.py<br/>(structlog + correlation id)"]
        METRICS["observability/metrics.py<br/>(Prometheus counters/histograms)"]
        AUDIT["observability/audit.py<br/>(AuditLogger — writes to DB)"]
    end

    API --> Service
    CLI --> Service
    Service --> Orchestration
    Orchestration --> CKPT

    N1 --> LEAD
    N2 --> RISK
    N4 --> BROKER

    N1 -.-> AUDIT
    N2 -.-> AUDIT
    N3 -.-> AUDIT
    N4 -.-> AUDIT
    AUDIT --> DB
    Service --> MEM

    API -.-> LOG
    API -.-> METRICS

    ERR["Exception-handling layer<br/>400 / 404 / 409 / 422 / 500 / 502 / 503<br/>+ X-Request-ID on every response"]
    API --> ERR
```

**Notes on the layering:**

- **Interface** (`api/main.py`, `cli.py`) is intentionally thin — both just
  call into `Service`; all real logic lives below.
- **Orchestration** (`workflow/graph.py`) is a LangGraph `StateGraph`. The
  `human_approval` node calls `interrupt()`, which durably pauses the graph
  via the checkpointer — approval can arrive seconds or days later, even
  across a process restart.
- **Agent** and **Domain** are deliberately separate: the agent layer can
  only *propose*; the domain layer (`risk_engine`, `execution`) is plain,
  deterministic Python with no LLM calls, and is what actually gates and
  submits an order.
- **Persistence** backs three distinct concerns on one engine: LangGraph
  checkpoints (pause/resume state), the audit trail, and the idempotency
  ledger that stops a retried request from ever double-submitting an order.
- **Error handling** in `api/main.py` maps every failure — validation,
  business-rule, missing-thread, DB-down, upstream-timeout, or truly
  unexpected — to a consistent `{"error": {"code", "message",
  "request_id"}}` envelope, with a `request_id` on every response for log
  correlation.
- Due to time pressure this document has been created with the help of Claude

