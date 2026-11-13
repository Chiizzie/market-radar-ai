"""Read-only, credential-free usage aggregates; never an OpenAI credit balance."""
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ..agents.github_budget import GitHubBudgetStore, validate_state

DUBLIN = ZoneInfo('Europe/Dublin')
PERIODS = ('daily', 'monthly', 'lifetime')


class Period(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    settled_microeur: int = Field(ge=0, le=2**53-1)
    reserved_microeur: int = Field(ge=0, le=2**53-1)
    limit_microeur: int = Field(gt=0, le=2**53-1)
    remaining_microeur: int = Field(ge=0, le=2**53-1)
    completed_calls: int = Field(ge=0, le=2**53-1)
    unsettled_reservations: int = Field(ge=0, le=2**53-1)


class Summary(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['ai-usage-v1']
    status: Literal['available', 'unavailable']
    currency: Literal['EUR']
    source: Literal['github_spending_ledger']
    as_of: str
    budget_day: str
    periods: dict[str, Period] | None


def validate_summary(raw, *, now):
    result = Summary.model_validate(raw).model_dump(mode='json')
    at = datetime.fromisoformat(result['as_of'])
    if (now.tzinfo is None or at.tzinfo is None
            or not -30 <= (now-at).total_seconds() <= 300
            or result['budget_day'] != at.astimezone(DUBLIN).date().isoformat()):
        raise ValueError('Invalid usage clock')
    periods = result['periods']
    if result['status'] == 'unavailable':
        if periods is not None:
            raise ValueError('Unavailable usage must not contain amounts')
        return result
    if periods is None or set(periods) != set(PERIODS):
        raise ValueError('Invalid usage periods')
    for p in periods.values():
        if p['remaining_microeur'] != max(0, p['limit_microeur']-p['settled_microeur']-p['reserved_microeur']):
            raise ValueError('Invalid remaining budget')
    for field in ('settled_microeur', 'reserved_microeur', 'completed_calls', 'unsettled_reservations'):
        if not periods['daily'][field] <= periods['monthly'][field] <= periods['lifetime'][field]:
            raise ValueError('Inconsistent usage periods')
    return result


def summarize(state, *, now):
    state = validate_state(state)
    day = now.astimezone(DUBLIN).date().isoformat()
    if any(date.fromisoformat(e['day']) > date.fromisoformat(day) for e in state['entries'].values()):
        raise ValueError('Future ledger day')
    periods = {}
    for name in PERIODS:
        rows = [e for e in state['entries'].values() if name == 'lifetime'
                or (name == 'daily' and e['day'] == day)
                or (name == 'monthly' and e['day'][:7] == day[:7])]
        settled = sum(e['actual'] for e in rows if e['actual'] is not None)
        held = sum(e['reserved'] for e in rows if e['actual'] is None)
        limit = state['limits_microeur'][name]
        periods[name] = dict(settled_microeur=settled, reserved_microeur=held,
            limit_microeur=limit, remaining_microeur=max(0, limit-settled-held),
            completed_calls=sum(e['actual'] is not None and e['usage'] is not None for e in rows),
            unsettled_reservations=sum(e['actual'] is None for e in rows))
    return validate_summary({**unavailable(now), 'status':'available', 'periods':periods}, now=now)


def unavailable(now):
    if now.tzinfo is None:
        raise ValueError('Aware clock required')
    return dict(schema_version='ai-usage-v1', status='unavailable', currency='EUR',
        source='github_spending_ledger', as_of=now.isoformat(),
        budget_day=now.astimezone(DUBLIN).date().isoformat(), periods=None)


def read_summary(token, *, clock, store_factory=GitHubBudgetStore):
    """Uses only load(); missing/unreadable accounting is never presented as zero."""
    if not token:
        return unavailable(clock())
    try:
        state, _ = store_factory(token).load()
        return summarize(state, now=clock())
    except Exception:
        # Do not export ledger IDs, provider response bodies, keys or exception text.
        return unavailable(clock())
