"""Opt-in bounded research orchestration using the existing metered pilot client.

No orders or paper plans. Activation is deliberately absent from CI schedules.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
from typing import Annotated, Literal
import re
from pydantic import Field, AfterValidator, ValidationError
from .paper_team import Frozen
from .combined_input import CombinedResearchInput
from .crypto_input import CryptoResearchInput
from .crypto_news_input import CryptoNewsResearchInput
from .roles import AgentRole
from .live_prompts import live_instruction, VERSION as INSTRUCTION_VERSION
from .openai_pilot import OpenAIPilot


def checked_prose(value):
    # Deliberately conservative: numbers belong in checked claims, execution
    # quality belongs in a fixed unknown field, not unconstrained prose.
    if (value != value.strip() or value[-1:] not in ('.', '!', '?')
            or value.endswith(('...', '…')) or any(c.isdigit() for c in value)
            or any(ord(c) > 127 and c not in '’“”–—' for c in value)
            or re.search(r"\b(liquid\w*|illiquid\w*|spread\w*|depth|slippage|execution)\b", value, re.I)
            or "','" in value or '\n' in value):
        raise ValueError('research_prose_quality_failed')
    return value


Prose = Annotated[str, AfterValidator(checked_prose)]
Concern = Annotated[Prose, Field(min_length=1, max_length=240)]


class MetricClaim(Frozen):
    metric: Literal['window_high', 'window_low', 'first_close', 'last_close']
    value: str = Field(max_length=40, pattern=r'^\d+(?:\.\d+)?$')
    quote_currency: str
    source_id: str


class GroundedResponse(Frozen):
    metric_claims: tuple[MetricClaim, ...] = Field(max_length=4)
    execution_quality: Literal['UNKNOWN_NO_SPREAD_OR_DEPTH']


def market_metrics(packet):
    rows = packet.market.candles
    return {key: str(value) for key, value in {
        'window_high': max(row.high for row in rows),
        'window_low': min(row.low for row in rows),
        'first_close': rows[0].close, 'last_close': rows[-1].close,
    }.items()}


def validate_claims(parsed, packet, metrics):
    from decimal import Decimal
    seen = set()
    for claim in parsed.metric_claims:
        if (claim.metric in seen or claim.source_id != packet.market.source_id()
                or claim.source_id not in parsed.source_ids
                or claim.quote_currency != packet.market.quote_currency
                or Decimal(claim.value) != Decimal(metrics[claim.metric])):
            raise ValueError('research_metric_mismatch')
        seen.add(claim.metric)


class ResearchAssessment(GroundedResponse):
    role: AgentRole
    snapshot_id: str
    summary: Prose = Field(min_length=1, max_length=500)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    concerns: tuple[Concern, ...] = Field(max_length=3)


class ReviewedResponse(GroundedResponse):
    reviewed_concern_ids: tuple[str, ...] = Field(max_length=18)
    acknowledged_missing_data: tuple[str, ...] = Field(max_length=16)


def validate_review(parsed, payload):
    expected = [item['id'] for item in payload['unresolved_concerns']]
    if (len(parsed.reviewed_concern_ids) != len(expected)
            or set(parsed.reviewed_concern_ids) != set(expected)):
        raise ValueError('concern_review_mismatch')
    gaps = payload['mandatory_missing_data']
    if (len(parsed.acknowledged_missing_data) != len(gaps)
            or set(parsed.acknowledged_missing_data) != set(gaps)):
        raise ValueError('missing_data_review_mismatch')


class ResearchDebate(ReviewedResponse):
    snapshot_id: str
    discussion: Prose = Field(min_length=1, max_length=1200)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class ResearchConclusion(ReviewedResponse):
    snapshot_id: str
    verdict: Literal['MORE_RESEARCH_NEEDED', 'INSUFFICIENT_EVIDENCE']
    rationale: Prose = Field(min_length=1, max_length=600)
    decisive_concern_ids: tuple[str, ...] = Field(max_length=3)
    counterargument: Prose = Field(min_length=1, max_length=240)
    next_evidence: tuple[Concern, ...] = Field(min_length=1, max_length=3)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


def normalized_narrative(text):
    return ' '.join(re.findall(r"[a-z]+", text.casefold()))


def validate_synthesis(parsed, payload):
    known = {c['id'] for c in payload['unresolved_concerns']}
    selected = parsed.decisive_concern_ids
    if (known and not selected) or len(set(selected)) != len(selected) or not set(selected) <= known:
        raise ValueError('decisive_concern_mismatch')
    rationale = normalized_narrative(parsed.rationale)
    if rationale == normalized_narrative(payload['debate']['discussion']):
        raise ValueError('copied_debate_rationale')
    if normalized_narrative(parsed.counterargument) == rationale:
        raise ValueError('repeated_counterargument')
    if len({normalized_narrative(x) for x in parsed.next_evidence}) != len(parsed.next_evidence):
        raise ValueError('duplicate_next_evidence')


def preflight(packet, *, now):
    if type(packet) not in (CombinedResearchInput,CryptoResearchInput,CryptoNewsResearchInput):
        raise ValueError('Unsupported research packet')
    packet=type(packet).model_validate(packet.model_dump(mode='json'))
    if now.tzinfo is None or not 0 <= (now-packet.assembled_at).total_seconds() <= 600:
        raise ValueError('stale_research_packet')
    news_items=packet.news.evidence if packet.news is not None else ()
    stamps=[packet.market.retrieved_at, *(item.retrieved_at for item in news_items)]
    if any(not 0 <= (now-stamp).total_seconds() <= 900 for stamp in stamps):
        raise ValueError('stale_research_sources')
    if not 300 <= (now-packet.market.candles[-1].timestamp).total_seconds() <= 900:
        raise ValueError('stale_market_candles')
    return packet


def run_research(client, packet, *, path, clock, enabled=False):
    if enabled is not True or type(client) is not OpenAIPilot:
        raise ValueError('Live research disabled or unsupported client')
    # The production entry point requires the durable shared ledger, not a new
    # scratch SQLite allowance that could reset on every worker invocation.
    from .github_budget import GitHubSpendingLedger
    if type(client.ledger) is not GitHubSpendingLedger:
        raise ValueError('Durable shared budget required')
    path=Path(path)
    if path.exists():
        raise ValueError('Existing research report must be preserved')
    report={'version':'live-research-v4','instruction_version':INSTRUCTION_VERSION,'analysis_quality':'requires_human_review','state':'preflight','trade_authorized':False,
            'calls':[],'assessments':[],'debate':None,'conclusion':None,
            'unresolved_concerns':[],'mandatory_missing_data':list(packet.missing_data)}
    def save():
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_name(path.name+'.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n')
        temporary.replace(path)
    save()
    try:
        packet=preflight(packet,now=clock())
        digest=packet.digest()
        metrics=market_metrics(packet)
        report['computed_metrics']={'values':metrics,'quote_currency':packet.market.quote_currency,
                                    'source_id':packet.market.source_id()}
        report['snapshot_id']=digest
        report['state']='running';save()
        def ask(stage,payload,schema,role=None):
            now=clock()
            preflight(packet,now=now)  # before every reservation and paid request
            request_id=f'live-research-v1:{digest}:{stage}'
            call={'request_id':request_id,'state':'attempting'}
            report['calls'].append(call);save()
            trusted=live_instruction(role,stage=stage)
            payload={**payload,'computed_metrics':report['computed_metrics'],
                     'risk_policy':{'currency':'EUR','maximum_planned_loss_eur':'20',
                         'overnight_positions_allowed':False,'entry_cutoff_dublin':'22:00',
                         'evaluated_at_dublin':now.astimezone(ZoneInfo('Europe/Dublin')).isoformat(),
                         'entry_cutoff_passed':now.astimezone(ZoneInfo('Europe/Dublin')).hour>=22,
                         'broker_eligibility':'unverified','trade_plan':'not_supplied',
                         'trade_authorized':False}}
            response_schema=schema.model_json_schema()
            response_schema['properties']['source_ids']['items']['enum']=list(packet.source_ids)
            response_schema['$defs']['MetricClaim']['properties']['source_id']['enum']=[packet.market.source_id()]
            response_schema['$defs']['MetricClaim']['properties']['quote_currency']['enum']=[packet.market.quote_currency]
            reply=client.call(prompt=json.dumps(payload,separators=(',',':')),
                schema=response_schema,request_id=request_id,now=now,
                instructions=trusted,max_output_tokens=1024,reasoning_effort='none')
            # Preserve usage before semantic validation; a rejected reply still costs money.
            call.update(state='received',response_id=reply.response_id,
                cost_usd=str(reply.cost_usd),estimated_cost_microeur=reply.estimated_cost_microeur)
            save()
            try:
                parsed=schema.model_validate(reply.data)
                if parsed.snapshot_id!=digest:
                    raise ValueError('snapshot_identity_mismatch')
                if any(source not in packet.source_ids for source in parsed.source_ids):
                    raise ValueError('unknown_response_citation')
                if role is not None and parsed.role!=role:
                    raise ValueError('specialist_role_mismatch')
                validate_claims(parsed,packet,metrics)
                if isinstance(parsed,ReviewedResponse):
                    validate_review(parsed,payload)
                if isinstance(parsed,ResearchConclusion):
                    validate_synthesis(parsed,payload)
            except ValueError as error:
                # Only local validation diagnostics: never exception text from
                # transport/providers, which may contain credentials or URLs.
                if isinstance(error, ValidationError):
                    call['validation_details']=[
                        {'field':list(item['loc']), 'type':item['type']}
                        for item in error.errors(include_input=False,include_context=False,
                                                 include_url=False)[:20]]
                else:
                    code=str(error)
                    field={'snapshot_identity_mismatch':'snapshot_id',
                           'unknown_response_citation':'source_ids',
                           'specialist_role_mismatch':'role',
                           'research_metric_mismatch':'metric_claims',
                           'concern_review_mismatch':'reviewed_concern_ids',
                           'missing_data_review_mismatch':'acknowledged_missing_data',
                           'decisive_concern_mismatch':'decisive_concern_ids',
                           'copied_debate_rationale':'rationale',
                           'repeated_counterargument':'counterargument',
                           'duplicate_next_evidence':'next_evidence'}[code]
                    call['validation_details']=[{'field':[field],'type':code}]
                # Quarantine as untrusted JSON, never an accepted assessment or
                # peer input. Bound storage independently of provider limits.
                encoded=json.dumps(reply.data,ensure_ascii=True)
                call['rejected_response']={
                    'status':'untrusted_rejected_draft','trade_authorized':False,
                    'data':reply.data if len(encoded.encode('utf-8'))<=32768 else None,
                    'omitted_for_size':len(encoded.encode('utf-8'))>32768}
                call['state']='rejected'
                call['validation_error']='response_quality_or_metric_validation_failed'
                save()
                raise
            call['state']='validated';save()
            return parsed
        for role in AgentRole:
            # Independent first passes: no peer output in this payload.
            response=ask(role.value,{'snapshot':packet.model_dump(mode='json'),
                'snapshot_id':digest,'role':role.value},ResearchAssessment,role)
            report['assessments'].append(response.model_dump(mode='json'))
            report['unresolved_concerns'].extend({'id':f'{role.value}:{i}', 'role':role.value,'concern':c}
                                                  for i,c in enumerate(response.concerns,1))
            save()
        payload={'snapshot':packet.model_dump(mode='json'),'snapshot_id':digest,
                 'assessments':report['assessments'],'unresolved_concerns':report['unresolved_concerns'],
                 'mandatory_missing_data':report['mandatory_missing_data']}
        report['debate']=ask('debate',payload,ResearchDebate).model_dump(mode='json');save()
        report['conclusion']=ask('conclusion',{**payload,'debate':report['debate']},ResearchConclusion).model_dump(mode='json')
        report['state']='completed';save()
    except Exception:
        report['state']='blocked_or_failed';save()
        raise RuntimeError('Research stopped; inspect report and shared budget before retrying') from None
    return report
