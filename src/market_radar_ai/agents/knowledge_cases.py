"""Point-in-time, outcome-blind matching over a frozen, auditable case library."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from .candidate_packages import canonical, digest
from .knowledge_playbooks import CATALOGUE_ID, playbook
from .paper_comparison import GUARDED_PROTOCOL, aware

VERSION = 'past-case-library-v1'
MAX_CASES = 5000
MAX_EXTRACT_BYTES = 7200


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Features(Strict):
    strategy: str = Field(pattern=r'^[a-z0-9_]{1,80}$')
    phase: Literal['opening', 'middle', 'late', 'outside']
    volume: Literal['unknown', 'below_baseline', 'normal', 'elevated', 'high']
    spread: Literal['unknown', 'tight', 'moderate', 'wide']
    momentum: Literal['unknown', 'nonpositive', 'small', 'medium', 'large']


class Outcome(Strict):
    state: str = Field(pattern=r'^[a-z_]{1,40}$')
    reason: str | None = Field(default=None, pattern=r'^[a-z0-9_]{1,120}$')
    net_pnl_eur: Decimal | None = Field(default=None, allow_inf_nan=False)
    observations_available: int | None = Field(default=None, ge=0)
    simulated: Literal[True] = True


class Case(Strict):
    setup_id: str = Field(pattern=r'^paper-final-attempt-v1:[a-f0-9]{64}$')
    packet_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    enrol_event_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    candidate_id: str = Field(pattern=r'^stocks:[A-Z0-9.\-]{1,20}$')
    enrolled_at: AwareDatetime
    known_at: AwareDatetime
    features: Features
    code_only: Outcome
    ai_reviewed: Outcome
    rejected_counterfactual_only: bool


def features(body):
    t, r = body['technical_checks'], body['reference_checks']
    local = aware(body['assembled_at']).astimezone(ZoneInfo('America/New_York'))
    minutes = local.hour * 60 + local.minute
    phase = ('outside' if not 570 <= minutes < 960 else 'opening' if minutes < 630
             else 'middle' if minutes < 840 else 'late')
    def number(value):
        try:
            result = Decimal(str(value))
            return result if result.is_finite() else None
        except (ValueError, ArithmeticError):
            return None
    vol = number(t.get('relative_volume_3_vs_prior') if t.get('strategy_id') == 'opening_continuation_30m_v1'
                 else t.get('relative_volume_5_vs_15'))
    momentum = number(t.get('momentum_window_pct') if t.get('strategy_id') == 'opening_continuation_30m_v1'
                      else t.get('momentum_20_bars_pct'))
    bid, ask = number(r.get('indicative_bid_eur')), number(r.get('indicative_ask_eur'))
    spread = (ask-bid)/((ask+bid)/2)*10000 if bid and ask and 0 < bid <= ask else None
    return Features(strategy=t.get('strategy_id', 'legacy_unspecified'), phase=phase,
        volume='unknown' if vol is None else 'below_baseline' if vol < 1 else 'normal' if vol < 1.5 else 'elevated' if vol < 3 else 'high',
        spread='unknown' if spread is None else 'tight' if spread <= 5 else 'moderate' if spread <= 20 else 'wide',
        momentum='unknown' if momentum is None else 'nonpositive' if momentum <= 0 else 'small' if momentum < 1 else 'medium' if momentum < 3 else 'large')


def outcome(arm):
    o = arm.get('outcome') or {}
    # Never infer zero returns from a rejection, unfilled plan or unresolved exit.
    return Outcome(state=arm['state'], reason=o.get('reason'),
                   net_pnl_eur=o.get('net_pnl_eur') if arm['state'] == 'closed' else None,
                   observations_available=arm.get('observations_available'))


def seal_library(cases, *, cutoff, built_at, partitions):
    cutoff, built_at = aware(cutoff), aware(built_at)
    if built_at < cutoff or len(cases) > MAX_CASES:
        raise ValueError('invalid_library_clock_or_capacity')
    normalized = [Case.model_validate(c).model_dump(mode='json') for c in cases]
    body = {'schema_version': VERSION, 'training_cutoff': cutoff.isoformat(),
            'built_at': built_at.isoformat(), 'source_protocol_id': digest(GUARDED_PROTOCOL),
            'playbook_catalogue_id': CATALOGUE_ID, 'dataset_kind': 'forward_archive',
            'partitions': partitions, 'cases': sorted(normalized, key=lambda c:c['setup_id']),
            'model_calls': 0, 'trade_authorized': False}
    library = {'library_id': digest(body), **body}
    validate_library(library)
    return library


def validate_library(library):
    expected = {'library_id', 'schema_version', 'training_cutoff', 'built_at', 'source_protocol_id',
                'playbook_catalogue_id', 'dataset_kind', 'partitions', 'cases', 'model_calls', 'trade_authorized'}
    if (set(library) != expected or library['library_id'] != digest({k:v for k,v in library.items() if k != 'library_id'})
            or library['schema_version'] != VERSION or library['source_protocol_id'] != digest(GUARDED_PROTOCOL)
            or library['playbook_catalogue_id'] != CATALOGUE_ID or library['dataset_kind'] != 'forward_archive'
            or library['trade_authorized'] is not False or library['model_calls'] != 0
            or len(library['cases']) > MAX_CASES or len(canonical(library).encode()) > 8_000_000):
        raise ValueError('invalid_case_library')
    cutoff, built = aware(library['training_cutoff']), aware(library['built_at'])
    if built < cutoff:
        raise ValueError('invalid_library_clock')
    seen = set()
    for row in library['cases']:
        c = Case.model_validate(row)
        if (c.setup_id in seen or not c.enrolled_at <= c.known_at <= cutoff
                or any(a.net_pnl_eur is not None and a.state != 'closed' for a in (c.code_only, c.ai_reviewed))
                or any(a.state == 'closed' and a.net_pnl_eur is None for a in (c.code_only, c.ai_reviewed))):
            raise ValueError('invalid_case_clock_identity_or_outcome')
        seen.add(c.setup_id)
    return library


def library_summary(library):
    validate_library(library)
    return {'library_id':library['library_id'], 'training_cutoff':library['training_cutoff'],
        'built_at':library['built_at'], 'cases':len(library['cases']),
        'strategies':dict(Counter(c['features']['strategy'] for c in library['cases'])),
        'code_only_states':dict(Counter(c['code_only']['state'] for c in library['cases'])),
        'ai_reviewed_states':dict(Counter(c['ai_reviewed']['state'] for c in library['cases'])),
        'scope':'Code-qualified stock cohorts only; excludes earlier screening rejects and legacy quote policies.',
        'model_calls':0, 'trade_authorized':False}


def retrieve(packet, library, *, as_of, max_cases=3):
    validate_library(library)
    at = aware(as_of)
    body = packet['packet']
    if packet['packet_id'] != digest(body):
        raise ValueError('invalid_query_hash')
    if not 0 <= max_cases <= 3:
        raise ValueError('invalid_retrieval_capacity')
    if (aware(library['built_at']) > at or aware(library['training_cutoff']) >= at
            or aware(body['assembled_at']) < aware(library['built_at'])):
        raise ValueError('knowledge_not_available_at_decision')
    if body.get('quote_observation_policy') != GUARDED_PROTOCOL['quote_observation_policy']:
        raise ValueError('knowledge_quote_policy_mismatch')
    target = features(body).model_dump()
    book = playbook(target['strategy'])
    if book is None:
        raise ValueError('unsupported_knowledge_strategy')
    ranked = []
    query_day = aware(body['assembled_at']).astimezone(ZoneInfo('America/New_York')).date()
    for c in library['cases']:
        if (c['features']['strategy'] != target['strategy'] or c['packet_id'] == packet['packet_id']
                or aware(c['known_at']) > at
                or aware(c['enrolled_at']).astimezone(ZoneInfo('America/New_York')).date() >= query_day):
            continue
        # Outcome, approval, symbol and money never enter scoring or tie-breaking.
        matches = [k for k in ('phase', 'volume', 'spread', 'momentum')
                   if target[k] not in ('unknown', 'outside') and c['features'][k] == target[k]]
        score = sum({'phase':4, 'volume':3, 'spread':2, 'momentum':1}[k] for k in matches)
        ranked.append((-score, c['setup_id'], c, matches))
    context = {'schema_version':'knowledge-extract-v1', 'library_id':library['library_id'],
        'training_cutoff':library['training_cutoff'], 'playbook':book, 'cases':[],
        'warning':'Historical simulated observations only. Not current evidence, proof of an edge or representative win rates.',
        'eligible_cases':len(ranked), 'max_cases':max_cases}
    used = set()
    for negative_score, _, c, matches in sorted(ranked):
        group = (c['candidate_id'], aware(c['enrolled_at']).astimezone(ZoneInfo('America/New_York')).date())
        if group in used or len(context['cases']) >= max_cases:
            continue
        item = {'source_id':'case:'+digest(c), **c, 'match_score':-negative_score, 'matched_features':matches}
        proposal = {**context, 'cases':context['cases']+[item]}
        if len(canonical(proposal).encode()) > MAX_EXTRACT_BYTES:
            continue
        context = proposal
        used.add(group)
    if len(canonical(context).encode()) > MAX_EXTRACT_BYTES:
        raise ValueError('playbook_exceeds_context_budget')
    return context
