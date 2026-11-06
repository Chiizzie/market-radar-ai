"""Deterministic EUR quote replay. No broker orders or claim of executable fills."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from pydantic import AwareDatetime, Field
from .paper_team import Frozen, PaperPlan


class Quote(Frozen):
    observed_at: AwareDatetime
    bid: Decimal = Field(gt=0, allow_inf_nan=False)
    ask: Decimal = Field(gt=0, allow_inf_nan=False)


class PaperOutcome(Frozen):
    status: Literal['not_filled', 'closed', 'unresolved']
    reason: str
    entry_at: AwareDatetime | None = None
    exit_at: AwareDatetime | None = None
    entry_fill: Decimal | None = None
    exit_fill: Decimal | None = None
    net_pnl_eur: Decimal | None = None
    simulated: Literal[True] = True


def replay_long(plan: PaperPlan, quotes: list[Quote], *, decision_at: datetime,
                entry_expires_at: datetime, entry_mode: Literal['limit', 'breakout'] = 'limit',
                exit_window_seconds: int = 0) -> PaperOutcome:
    """Limit-entry long simulation, using asks for entry and bids for exit.

    First eligible ask at/below entry fills at the ask. A stop gap exits at the
    observed bid (never the more favourable stop). Deadline exits require an exact
    deadline quote; later data does not retroactively prove an intraday exit.
    Breakout mode instead requires ask >= trigger, rejects invalidation before
    entry and skips trigger gaps whose projected stop loss exceeds EUR20.
    Estimated round-trip costs are deducted once. No volume/queue/slippage model.
    """
    if type(exit_window_seconds) is not int or not 0 <= exit_window_seconds <= 30:
        raise ValueError('Invalid scheduled exit window')
    if entry_mode not in ('limit', 'breakout'):
        raise ValueError('Unknown entry mode')
    from zoneinfo import ZoneInfo
    plan = PaperPlan.model_validate(plan.model_dump())
    if decision_at.tzinfo is None or entry_expires_at.tzinfo is None:
        raise ValueError('Aware clocks required')
    local = decision_at.astimezone(ZoneInfo('Europe/Dublin'))
    deadline = plan.exit_by.astimezone(ZoneInfo('Europe/Dublin'))
    if (not decision_at < entry_expires_at <= plan.exit_by or plan.planned_loss > 20
            or local.hour >= 22 or deadline.date() != local.date()
            or deadline > deadline.replace(hour=22,minute=0,second=0,microsecond=0)):
        raise ValueError('Invalid paper risk or intraday window')
    rows = [Quote.model_validate(q.model_dump()) for q in quotes]
    if any(q.bid > q.ask for q in rows): raise ValueError('Crossed quote')
    if any(b.observed_at <= a.observed_at for a,b in zip(rows,rows[1:])):
        raise ValueError('Quotes must be strictly ordered without duplicates')
    entry = None
    exit_start = plan.exit_by - timedelta(seconds=exit_window_seconds)
    for q in rows:
        if q.observed_at < decision_at: continue
        if q.observed_at > plan.exit_by: break
        if entry is None:
            if exit_window_seconds and q.observed_at >= exit_start:
                break  # Never open a new simulation during its scheduled exit window.
            if q.observed_at >= entry_expires_at: break
            if entry_mode == 'breakout':
                # Invalidate before trigger; never buy a breakout below its trigger.
                if q.bid <= plan.stop:
                    return PaperOutcome(status='not_filled', reason='entry_already_invalidated')
                if q.ask < plan.entry: continue
                if (q.ask-plan.stop)*plan.quantity+plan.costs_eur > 20:
                    return PaperOutcome(status='not_filled', reason='trigger_gap_exceeds_risk_budget')
            elif q.ask > plan.entry: continue
            if q.ask <= plan.stop:
                return PaperOutcome(status='not_filled', reason='entry_already_invalidated')
            entry = q
        reason = ('stop' if q.bid <= plan.stop else 'target' if q.bid >= plan.target
                  else 'deadline' if q.observed_at == plan.exit_by
                  else 'scheduled_exit' if exit_window_seconds and q.observed_at >= exit_start else None)
        if reason:
            return PaperOutcome(status='closed', reason=reason, entry_at=entry.observed_at,
                exit_at=q.observed_at, entry_fill=entry.ask, exit_fill=q.bid,
                net_pnl_eur=(q.bid-entry.ask)*plan.quantity-plan.costs_eur)
    if entry is None:
        return PaperOutcome(status='not_filled',reason='no_observed_eligible_fill')
    return PaperOutcome(status='unresolved',reason='no_observed_exit_by_deadline',
                        entry_at=entry.observed_at,entry_fill=entry.ask)


def record_replay(store, run_id, quotes, *, entry_expires_at, entry_mode='limit'):
    """Evaluate only an accepted stored plan; preserve quote evidence with outcome."""
    import json
    import sqlite3
    record = store.inspect(run_id)
    if record['state'] != 'completed' or not record['result']['plan']:
        raise ValueError('No accepted recorded paper plan')
    plan = PaperPlan.model_validate(record['result']['plan'])
    result = replay_long(plan, quotes,
        decision_at=datetime.fromisoformat(record['request']['now']),
        entry_expires_at=entry_expires_at, entry_mode=entry_mode)
    payload = json.dumps({'entry_expires_at':entry_expires_at.isoformat(),
        'quotes':[q.model_dump(mode='json') for q in quotes],
        'outcome':result.model_dump(mode='json')},sort_keys=True)
    if entry_mode != 'limit':
        document = json.loads(payload)
        document['entry_mode'] = entry_mode
        payload = json.dumps(document, sort_keys=True)
    with sqlite3.connect(store.path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS paper_replays (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM paper_replays WHERE run_id=?',(run_id,)).fetchone()
        if row and row[0] != payload: raise ValueError('Replay already recorded with different evidence')
        if not row: db.execute('INSERT INTO paper_replays VALUES(?,?)',(run_id,payload))
    return result
