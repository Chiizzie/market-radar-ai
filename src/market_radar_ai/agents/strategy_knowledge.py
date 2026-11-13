"""Version-two playbooks and partitioned histories; leaves the first experiment immutable."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field
from .candidate_packages import digest, canonical
from .knowledge_cases import Strict, Features, Outcome, features, validate_library as validate_v1
from .knowledge_playbooks import playbook as core_book
from .paper_comparison import aware
from .strategy_registry import CORE, METHODS, OFFLINE, ALL, PROTOCOL, source_protocol, source_policy
from .mean_reversion import RULES as REVERSION_RULES

VERSION='strategy-knowledge-v2'
CUTOFF='2026-11-13T21:17:12+00:00'
MAX_BYTES=9000
DESCRIPTIONS={
    'session_open_avwap_reclaim_v1':('Session-open anchored VWAP reclaim',
        'Complete regular-session anchor, rising daily and completed fifteen-minute trends, bullish AVWAP reclaim with participation.',
        'The anchor cannot move to fit a truncated capture. Bar-derived IEX AVWAP is partial-market evidence.'),
    'opening_range_15m_shadow_v1':('Fifteen-minute opening-range breakout',
        'Define the first three completed five-minute bars; admit only 15–30 minutes after the regular open.',
        'The three-range target cap is a projection, not observed resistance. No late retry after a completed-bar breakout.'),
    'competitor_strength_breakout_shadow_v1':('Competitor-strength breakout',
        'A timestamped source-company headline, supported relationship and aligned post-news relative performance plus a chart breakout.',
        'The current relationship map is restricted to NVDA/AMD/INTC. A headline does not prove its direction or the competitor thesis.'),
    OFFLINE:('Intraday range mean reversion: offline prototype',
        'A low-efficiency earlier range, stretched close and bullish recovery toward the pre-signal mean.',
        'The baseline excludes both signal bars. This is an unproven offline hypothesis; do not activate on historical fit.'),
}


def playbook(strategy):
    if strategy in CORE:
        body={**core_book(strategy),'version':VERSION}
        body.pop('source_id')
    else:
        title,setup,limitation=DESCRIPTIONS[strategy]
        rules=REVERSION_RULES if strategy==OFFLINE else METHODS[strategy][1]['rules']
        body={'version':VERSION,'strategy_id':strategy,'title':title,'setup':setup,'rules':rules,
            'invalidation':'Expired or stale inputs, stop failure before trigger, excessive spread/gap, missing news/context or insufficient cost-adjusted target room.',
            'limitations':[limitation,'Historical reference-price simulations are not broker fills or proof of an edge.'],
            'requirements':['Current quote, FX, market and catalogue checks; completed bounded news check.',
                'Cost-inclusive planned risk <= EUR20; net reward/risk >= 2; same-day exit; entry before 22:00 Dublin.']}
    body.update(source_protocol_id=source_protocol(strategy),historical_source_policy=source_policy(strategy),
                offline_only=strategy==OFFLINE)
    return {'source_id':'playbook:'+digest(body),**body}


CATALOGUE_ID=digest([playbook(s) for s in ALL])


class HistoricalCase(Strict):
    case_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_setup_id: str = Field(pattern=r'^[a-zA-Z0-9:_-]{1,150}$')
    source_event_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    input_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    strategy_id: str
    source_protocol_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_policy: str
    candidate_id: str = Field(pattern=r'^stocks:[A-Z0-9.\-]{1,20}$')
    enrolled_at: AwareDatetime
    known_at: AwareDatetime
    features: Features
    code_only: Outcome
    ai_reviewed: Outcome
    rejected_counterfactual_only: bool


def case_identity(row):
    return digest({k:row[k] for k in ('source_protocol_id','source_setup_id','source_event_id')})


def imported_v1(library):
    validate_v1(library)
    rows=[]
    for c in library['cases']:
        s=c['features']['strategy']
        if s not in CORE: raise ValueError('unsupported_base_case_strategy')
        row={'source_setup_id':c['setup_id'],'source_event_id':c['enrol_event_id'],
            'input_sha256':c['packet_id'],'strategy_id':s,'source_protocol_id':source_protocol(s),
            'source_policy':source_policy(s),'candidate_id':c['candidate_id'],'enrolled_at':c['enrolled_at'],
            'known_at':c['known_at'],'features':c['features'],'code_only':c['code_only'],'ai_reviewed':c['ai_reviewed'],
            'rejected_counterfactual_only':c['rejected_counterfactual_only']}
        rows.append({'case_id':case_identity(row),**row})
    return rows


def compact_features(inputs, result):
    p=inputs['reference_checks']['payload']; q=p.get('quotes',{}).get('quotes',{}).get(inputs['symbol'],{})
    measured={**result['features'],'strategy_id':result['strategy_id']}
    if 'relative_volume_3_vs_prior15' in measured:
        measured['relative_volume_5_vs_15']=measured['relative_volume_3_vs_prior15']
    return features({'assembled_at':result['assembled_at'],'technical_checks':measured,
        'reference_checks':{'indicative_bid_eur':q.get('bp'),'indicative_ask_eur':q.get('ap')}}).model_dump(mode='json')


def seal(cases, *, base_library_id, built_at, manifests):
    rows=[HistoricalCase.model_validate(c).model_dump(mode='json') for c in cases]
    body={'schema_version':VERSION,'training_cutoff':CUTOFF,'built_at':aware(built_at).isoformat(),
        'catalogue_id':CATALOGUE_ID,'base_library_id':base_library_id,'source_manifests':manifests,
        'cases':sorted(rows,key=lambda c:c['case_id']),'trade_authorized':False,'model_calls':0}
    result={'library_id':digest(body),**body};validate(result);return result


def validate(library):
    fields={'schema_version','training_cutoff','built_at','catalogue_id','base_library_id','source_manifests',
            'cases','trade_authorized','model_calls','library_id'}
    if (set(library)!=fields or library['library_id']!=digest({k:v for k,v in library.items() if k!='library_id'})
            or library['schema_version']!=VERSION or library['catalogue_id']!=CATALOGUE_ID
            or aware(library['training_cutoff'])!=aware(CUTOFF) or aware(library['built_at'])<aware(CUTOFF)
            or library['trade_authorized'] is not False or library['model_calls']!=0
            or len(library['cases'])>5000 or len(canonical(library).encode())>10_000_000):
        raise ValueError('invalid_strategy_library')
    seen=set()
    for raw in library['cases']:
        c=HistoricalCase.model_validate(raw)
        if (c.case_id in seen or c.case_id!=case_identity(raw) or c.strategy_id not in ALL
                or c.strategy_id!=c.features.strategy or c.source_protocol_id!=source_protocol(c.strategy_id)
                or c.source_policy!=source_policy(c.strategy_id) or not c.enrolled_at<=c.known_at<=aware(CUTOFF)
                or any((a.state=='closed') != (a.net_pnl_eur is not None) for a in (c.code_only,c.ai_reviewed))):
            raise ValueError('invalid_strategy_case')
        seen.add(c.case_id)
    return library


def summary(library):
    validate(library)
    return {'library_id':library['library_id'],'built_at':library['built_at'],'training_cutoff':CUTOFF,
        'cases':len(library['cases']),'by_strategy':{s:sum(c['strategy_id']==s for c in library['cases']) for s in ALL},
        'code_states':dict(Counter(c['code_only']['state'] for c in library['cases'])),
        'model_calls':0,'trade_authorized':False}


class Retriever:
    def __init__(self, library):
        from copy import deepcopy
        self.library=deepcopy(validate(library));self.groups=defaultdict(list)
        for c in self.library['cases']: self.groups[c['strategy_id']].append(c)

    def retrieve(self, result, inputs, *, as_of):
        at=aware(as_of);assembled=aware(result['assembled_at'])
        if assembled>at or min(at,assembled)<aware(self.library['built_at']) or assembled<=aware(CUTOFF):
            raise ValueError('strategy_knowledge_unavailable_at_decision')
        if digest(inputs)!=result['input_sha256'] or result['strategy_id'] not in ALL:
            raise ValueError('invalid_strategy_retrieval_query')
        s=result['strategy_id'];target=compact_features(inputs,result);ranked=[]
        day=assembled.astimezone(ZoneInfo('America/New_York')).date()
        for c in self.groups[s]:
            if (c['source_protocol_id']!=result['source_protocol_id'] or aware(c['known_at'])>at
                    or aware(c['enrolled_at']).astimezone(ZoneInfo('America/New_York')).date()>=day
                    or c['input_sha256']==result['input_sha256']):continue
            matches=[k for k in ('phase','volume','spread','momentum') if target[k] not in ('unknown','outside') and c['features'][k]==target[k]]
            score=sum({'phase':4,'volume':3,'spread':2,'momentum':1}[k] for k in matches)
            ranked.append((-score,c['case_id'],c,matches))
        context={'schema_version':'strategy-extract-v2','library_id':self.library['library_id'],
            'playbook':playbook(s),'eligible_cases':len(ranked),'cases':[],
            'warning':'Historical simulated evidence only. Each case retains its original quote/exit policy; different policies are not comparable performance. Unfilled is not proof the price never crossed. No historical case supplies current facts.'}
        used=set()
        for score,_,c,matches in sorted(ranked):
            group=(c['candidate_id'],aware(c['enrolled_at']).date())
            if group in used or len(context['cases'])>=3:continue
            item={'source_id':'case:'+digest(c),**c,'match_score':-score,'matched_features':matches}
            proposed={**context,'cases':context['cases']+[item]}
            if len(canonical(proposed).encode())>MAX_BYTES:continue
            context=proposed;used.add(group)
        if len(canonical(context).encode())>MAX_BYTES:raise ValueError('strategy_context_capacity')
        return context
