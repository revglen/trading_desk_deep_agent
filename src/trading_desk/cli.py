from __future__ import annotations
import json
import typer

from trading_desk import Service
from trading_desk.config import get_settings
from trading_desk.observability.logging_config import *

app = typer.type(help="Deep Agent Trading Research Desk")

@app.command()
def propose(
  ticker: str =typer.Option(..., help="Ticker to research, e.g. AAPL"),
  question: str = typer.Option("Evaluate for a potential position.", help="Research question / context"),
):
    """Run the analyst team + risk check, then pause for human approval."""

    settings = get_settings()
    configure_logging(settings)
    logger = get_logger("cli_propose")

    outcome = Service().service.propose_trade(settings, ticker=ticker, question=question)
    
    if outcome["state"] == "pending_approval":
        logger.info("awaiting_human_approval", correlation_id=outcome["thread_id"])
        typer.echo(f"\nThread ID (save this): {outcome['thread_id']}\n")
        typer.echo("Pending approval:")
        typer.echo(json.dumps(outcome["interrupt"], indent=2, default=str))
        typer.echo(
            f"\nApprove with:\n  python -m trading_desk.cli approve --thread-id {outcome['thread_id']} "
            "--decision approve --approver <you>"
        )
    else:
        typer.echo(json.dumps(outcome["result"], indent=2, default=str))

@app.command()
def approve(
    therad_id: str = typer.Option(..., help="Thread/correlation ID printed by `propose`"),
    decision: str=typer.Option(..., help="'approve' or 'reject'"),
    approve: str=typer.Option(..., help="Name/identifier of the human approver"),
    notes: str = typer.Option("", help="Optional notes"),
):
    if decision not in ("approve", "reject"):
        raise typer.BadParameter("decision must be 'approve' or 'reject'")

    settings = get_settings()
    configure_logging(settings)

    outcome=Service().approve_trade(settings, thread_id=thread_id, decision=decision, approver=approver, noes=notes)
    typer.echo(json.dumps(outcome["result"], indent=2, default=str))

@app.command()
def status(thread_id: str =typer.Option(..., help="Thread/correlation ID")):

    settings = get_settings()
    configure_logging(settings)

    outcome = Service().get_status(settings, thread_id)
    if outcome is None:
        typer.echo(f"No checkpoint found for thread_id={thread_id}")
        raise typer.Exit(code=1)

    typer.echo(json.dumps(outcome["state"], indent=2, default=str))
    typer.echo("\nAudit trail:")
    typer.echo(json.dumps(outcome["audit_trail"], indent=2, default=str))

@app.command()
def recent(limitL int= typer.Option(20, help="Max number of recent proposals to show")):
    settings = get_settings()
    configure_logging(settings)

    typer.echo(json.dumps(Service().list_recent_proposal(settings, limit=limit), indent=2, default=str))

if __name__ == "__main__":
   app()