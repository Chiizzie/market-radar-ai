"""Code-qualified paper verdicts. No order API; model access is injected explicitly."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from pydantic import Field
from .paper_team import Frozen
from .roles import AgentRole
from .candidate_packages import digest, canonical
from .setup_checks import validate_paper_plan
from .paper_review_prompts import instruction, VERSION as REVIEW_POLICY_VERSION

STAGES = [r.value for r in AgentRole]+['debate','conclusion']


class VerdictReview(Frozen):
    stage: str
    packet_id: str
    verdict: Literal['APPROVE_PAPER','REJECT','MORE_EVIDENCE_REQUIRED']
    rationale: str = Field(min_length=1,max_length=600)
    source_ids: tuple[str,...] = Field(min_length=1,max_length=4)
    concerns: tuple[str,...] = Field(max_length=3)
    reviewed_stages: tuple[str,...]


def paper_gate(row, *, now):
    """Eligibility to spend on a simulation, not live trading permission."""
    blocks=[]
    checks=row['reference_checks']; tech=row['technical_checks']
    # Robinhood eligibility is not inferred from Kraken data.
    if row['market']=='crypto' and (checks.get('catalogue_candidate')!='PASS' or checks.get('catalogue_scope')!='public_europe_support_list_not_account_verification'): blocks.append('crypto_broker_catalogue_not_connected')
    for name in ('catalogue_candidate','market_session','reference_quote','fx'):
        if checks.get(name)!='PASS': blocks.append(name+'_not_confirmed')
    plan=row['conditional_paper_plan']
    if plan is not None and plan.get('symbol')!=row['symbol']:blocks.append('plan_symbol_mismatch')
    if plan is not None:
        try:
            ask=Decimal(str(checks.get('indicative_ask_eur')))
            if not ask.is_finite() or ask<=0:raise ValueError('invalid_ask')
            if ask>=Decimal(plan['entry_eur']):blocks.append('entry_trigger_already_reached_rebuild')
            if ask<=Decimal(plan['stop_eur']):blocks.append('setup_invalidated_before_entry')
        except (ValueError,ArithmeticError):blocks.append('reference_ask_eur_missing')
    risk=validate_paper_plan(plan,now=now,exit_deadline=checks.get('exit_deadline'))
    if risk['state']!='PASS':blocks.extend(risk['failures'])
    if not checks.get('exit_deadline'): blocks.append('session_exit_missing')
    if tech.get('state')!='MEASURED':blocks.append('technical_measurements_missing')
    else:
        early=tech.get('strategy_id')=='opening_continuation_30m_v1'
        if Decimal(tech['momentum_window_pct'] if early else tech['momentum_20_bars_pct'])<=0: blocks.append('nonpositive_momentum')
        if Decimal(tech['relative_volume_3_vs_prior'] if early else tech['relative_volume_5_vs_15'])<Decimal('1.5'):blocks.append('relative_volume_below_1_5')
        if tech['close_above_rolling_vwap'] is not True:blocks.append('below_rolling_vwap')
        if tech['trigger_state']!='WAITING_FOR_TRIGGER':blocks.append('conditional_entry_already_passed')
    if not row.get('current_news_source_ids'):blocks.append('current_symbol_linked_news_missing')
    return {'eligible_for_paper_review':not blocks,'paper_blockers':sorted(set(blocks)),
            'live_trade_authorized':False,
            'assumptions':['Catalogue match is paper availability evidence, not live account order permission.',
                           'IEX stock or Kraken crypto reference prices, not broker execution quotes.',
                           'Fictional EUR 500 allocation and assumed 40 bps round-trip costs, including FX/slippage allowance.',
                           'News attribution is evidence for the reviewers; catalyst strength is not pre-approved.']}


def build_packets(document, feed, *, now):
    from .qualification import qualify
    report=qualify(document,feed,now=now)
    packets=[]
    for row in report['candidates']:
        gate=paper_gate(row,now=now)
        if not gate['eligible_for_paper_review']:continue
        body={'schema_version':'paper-review-packet-v1','assembled_at':now.isoformat(),
              'review_deadline':(now+timedelta(minutes=10)).isoformat(),
              'candidate_id':row['candidate_id'],'symbol':row['symbol'],
              'plan':row['conditional_paper_plan'],'technical_checks':row['technical_checks'],
              'reference_checks':row['reference_checks'],
              'sources':row['review_sources'],'source_ids':list(row['review_sources']),
              'assumptions':gate['assumptions'],'live_trade_authorized':False}
        packets.append({'packet_id':digest(body),'packet':body})
    return {'packets':packets,'qualification':report,'model_calls':0,'trade_authorized':False}


def review(packet, document, feed, ask, *, clock):
    """Six independent specialists, then debate/conclusion; never a live order."""
    started=clock()
    rebuilt=build_packets(document,feed,now=datetime.fromisoformat(packet['packet']['assembled_at']))
    if canonical(packet) not in [canonical(p) for p in rebuilt['packets']]:
        raise ValueError('paper_packet_does_not_reproduce')
    body=packet['packet']; deadline=datetime.fromisoformat(body['review_deadline'])
    if not datetime.fromisoformat(body['assembled_at'])<=started<datetime.fromisoformat(body['plan']['expires_at']):
        raise ValueError('paper_packet_expired_before_review')
    reports=[]; previous=started
    for stage in STAGES:
        at=clock()
        if not previous<=at<deadline:raise ValueError('paper_review_deadline')
        peers=deepcopy(reports) if stage in ('debate','conclusion') else []
        prompt={'packet':deepcopy(body),'packet_id':packet['packet_id'],'stage':stage,'peer_reviews':peers,
                'instruction':instruction(stage)}
        answer=VerdictReview.model_validate(ask(stage,prompt,VerdictReview.model_json_schema()))
        finished=clock()
        if not at<=finished<deadline:raise ValueError('paper_review_deadline')
        if (answer.stage!=stage or answer.packet_id!=packet['packet_id']
            or len(set(answer.source_ids))!=len(answer.source_ids)
            or not set(answer.source_ids)<=set(body['source_ids'])
            or list(answer.reviewed_stages)!=[p['stage'] for p in peers]):
            raise ValueError('paper_review_identity_or_citations')
        reports.append(answer.model_dump(mode='json'));previous=finished
    return {'schema_version':'paper-ai-review-v1','packet_id':packet['packet_id'],
            'completed_at':finished.isoformat(),'reviews':reports,'model_calls':8,
            'trade_authorized':False}


def finalize(packet, audit, fresh_document, fresh_feed, *, now):
    """Rebuild fresh checks after AI; an old quote can never authorize a paper entry."""
    body=packet['packet'];blocks=[]
    if digest(body)!=packet['packet_id'] or audit['packet_id']!=packet['packet_id']:
        raise ValueError('paper_decision_identity')
    reports=[VerdictReview.model_validate(r) for r in audit['reviews']]
    if [r.stage for r in reports]!=STAGES:raise ValueError('incomplete_paper_team')
    for i,r in enumerate(reports):
        if (r.packet_id!=packet['packet_id'] or not set(r.source_ids)<=set(body['source_ids'])
            or len(set(r.source_ids))!=len(r.source_ids)
            or list(r.reviewed_stages)!=(STAGES[:i] if i>=6 else [])):
            raise ValueError('invalid_paper_review_chain')
    completed=datetime.fromisoformat(audit['completed_at'])
    if not datetime.fromisoformat(body['assembled_at'])<=completed<=now<datetime.fromisoformat(body['review_deadline']):
        blocks.append('review_expired_or_future')
    # Every specialist retains a veto through REJECT or MORE_EVIDENCE_REQUIRED.
    # APPROVE_PAPER concerns are disclosed caveats, not an implicit second verdict.
    if any(r.verdict!='APPROVE_PAPER' for r in reports):
        blocks.append('team_did_not_clear_setup')
    fresh=build_packets(fresh_document,fresh_feed,now=now)['packets']
    matches=[p for p in fresh if p['packet']['candidate_id']==body['candidate_id']]
    plan=None
    if len(matches)!=1:blocks.append('fresh_setup_no_longer_qualified')
    else:
        current=matches[0]['packet']
        # Renew freshness only for identical economics and source evidence. Any
        # changed strategy/levels/news requires a new review, not recycled approval.
        oldplan={k:v for k,v in body['plan'].items() if k!='expires_at'}
        newplan={k:v for k,v in current['plan'].items() if k!='expires_at'}
        if oldplan!=newplan:blocks.append('plan_changed_since_review')
        if stable_evidence(body['sources'])!=stable_evidence(current['sources']):blocks.append('evidence_changed_since_review')
        if not blocks:plan=current['plan']
    return {'schema_version':'paper-final-decision-v1','candidate_id':body['candidate_id'],
            'packet_id':packet['packet_id'],'evaluated_at':now.isoformat(),
            'verdict':'PAPER_WATCH_FOR_ENTRY' if not blocks else 'NO_ACTION',
            'paper_only':True,'trade_authorized':False,'live_orders_enabled':False,
            'blockers':blocks,'plan':plan,'assumptions':body['assumptions'],
            'note':'Conditional simulated entry only. No position opened and no live trading permission granted.'}


def stable_evidence(sources):
    """Compare validated evidence content, not collection bookkeeping.

    Raw records and their hashes remain in the audit packet. The freshly built
    packet independently validates freshness, integrity, quotes and risk before
    this comparison. Unknown fields remain significant (fail closed).
    """
    metadata = {
        'market': {'retrieved_at', 'validated_at', 'original_capture_sha256', 'reference_quote'},
        'calendar': {'retrieved_at', 'original_calendar_sha256'},
        'catalogue': {'retrieved_at'},
        'news': {'retrieved_at', 'publication_age_seconds'},
    }
    values=[]
    for source_id, source in sources.items():
        kind=source_id.split(':', 1)[0]
        value={k:v for k,v in source.items() if k not in metadata.get(kind, set())}
        values.append(canonical({'kind':kind,'content':value}))
    return sorted(values)

def run_metered(client, packet, document, feed, *, path, clock, enabled=False):
    """Explicit opt-in adapter; no automatic scheduler activation."""
    import json
    from pathlib import Path
    from .openai_pilot import OpenAIPilot
    from .github_budget import GitHubSpendingLedger
    if enabled is not True or type(client) is not OpenAIPilot or type(client.ledger) is not GitHubSpendingLedger:
        raise ValueError('metered_paper_review_not_enabled')
    path=Path(path)
    if path.exists():raise ValueError('preserve_existing_review')
    calls=[]
    def save(result=None):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'review_policy_version':REVIEW_POLICY_VERSION,
                                   'calls':calls,'result':result,'trade_authorized':False},indent=2)+'\n')
    def ask(stage,prompt,schema):
        calls.append({'stage':stage,'state':'attempting'});save()
        # Identity and peer bookkeeping belong to the orchestrator. The model
        # supplies only its assessment and citations from the supplied evidence.
        model_schema=deepcopy(schema)
        metadata=('stage','packet_id','reviewed_stages')
        for field in metadata: model_schema['properties'].pop(field)
        model_schema['required']=[f for f in model_schema['required'] if f not in metadata]
        model_schema['properties']['source_ids']['items']['enum']=list(prompt['packet']['source_ids'])
        instructions=prompt['instruction']+' Return only verdict, rationale, source_ids and concerns. Cite distinct IDs from the supplied source_ids list. The application supplies stage, packet identity and reviewed-stage bookkeeping.'
        reply=client.call(prompt=canonical(prompt),schema=model_schema,
            request_id='paper-final-v1:'+packet['packet_id']+':'+stage,now=clock(),
            max_output_tokens=1024,reasoning_effort='none',instructions=instructions)
        calls[-1].update(state='received', assessment=reply.data);save()
        from jsonschema import Draft202012Validator
        Draft202012Validator(model_schema).validate(reply.data)
        return {**reply.data,'stage':stage,'packet_id':packet['packet_id'],
                'reviewed_stages':[r['stage'] for r in prompt['peer_reviews']]}
    try:
        result=review(packet,document,feed,ask,clock=clock)
    except Exception:
        if calls:
            calls[-1]['state']='failed_review';save()
        raise
    save(result)
    return result


PAPER_REVIEW_COOLDOWN_SECONDS = 15 * 60


def paper_attempt_id(packet, *, now):
    from zoneinfo import ZoneInfo
    body=packet['packet']
    identity={'day':now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat(),
              'candidate_id':body['candidate_id'],
              'plan':{k:v for k,v in body['plan'].items() if k!='expires_at'},
              'evidence':stable_evidence(body['sources'])}
    return 'paper-final-attempt-v1:'+digest(identity)


def choose_unreviewed_packet(packets, entries, *, now):
    """Skip paid duplicates and recent candidates without starving other setups.

    Cooldown timestamps live in durable zero-cost ledger marker keys. The
    scheduled workflow serializes budget users; reservations use compare-and-swap.
    A failed attempt also cools down, so errors cannot trigger paid retry loops.
    """
    if now.tzinfo is None:raise ValueError('aware_clock_required')
    skipped=[]
    for packet in packets:
        body=packet['packet'];candidate=body['candidate_id']
        attempt=paper_attempt_id(packet,now=now)
        if attempt in entries:
            skipped.append({'candidate_id':candidate,'reason':'paper_setup_already_attempted'})
            continue
        prefix='paper-cooldown-v1:'+digest(candidate)+':'
        stamps=[]
        for key in entries:
            if key.startswith(prefix):
                stamp=key[len(prefix):]
                if not stamp.isdigit() or len(stamp)!=10:
                    raise ValueError('invalid_paper_cooldown_marker')
                stamps.append(int(stamp))
        if stamps and now.timestamp()-max(stamps)<PAPER_REVIEW_COOLDOWN_SECONDS:
            skipped.append({'candidate_id':candidate,'reason':'paper_review_cooldown'})
            continue
        return packet,attempt,prefix+str(int(now.timestamp())),skipped
    return None,None,None,skipped


def run_pipeline(document, feed, *, client, root, refresh, deliver, clock, enabled=False, comparison=None):
    """Complete backend path with injected refresh/delivery and durable spending.

    Refresh receives the reviewed symbol and must return newly collected capture/news. Delivery receives a paper
    decision only after finalization. Failed attempts are never paid-replayed.
    The scheduled workflow remains disabled separately.
    """
    import json
    from pathlib import Path
    from .github_budget import GitHubSpendingLedger
    from .openai_pilot import OpenAIPilot
    if enabled is not True or type(client) is not OpenAIPilot or type(client.ledger) is not GitHubSpendingLedger:
        raise ValueError('metered_paper_pipeline_not_enabled')
    root=Path(root)
    if root.exists():raise ValueError('preserve_existing_paper_attempt')
    root.mkdir(parents=True)
    def save(name,value):
        (root/name).write_text(json.dumps(value,indent=2)+'\n')
    now=clock()
    batch=build_packets(document,feed,now=now)
    save('qualification.json',batch['qualification'])
    from .paper_comparison import cohort_snapshot
    save('comparison-cohort.json', cohort_snapshot(batch['packets'], now=now))
    if comparison is not None:
        for qualified_packet in batch['packets']:
            comparison.enrol(qualified_packet, now=now)
    if not batch['packets']:
        result={'state':'no_qualified_candidate_zero_cost','model_calls':0,'trade_authorized':False}
        save('status.json',result);return result
    state,_=client.ledger.store.load()
    packet,attempt,cooldown,skipped=choose_unreviewed_packet(batch['packets'],state['entries'],now=now)
    save('review-selection.json',{'skipped':skipped,
         'selected_candidate_id':packet['packet']['candidate_id'] if packet else None,
         'cooldown_seconds':PAPER_REVIEW_COOLDOWN_SECONDS,'model_calls':0})
    if packet is None:
        reason='paper_review_cooldown' if any(s['reason']=='paper_review_cooldown' for s in skipped) else 'paper_setup_already_attempted'
        result={'state':reason,'model_calls':0,'trade_authorized':False,'skipped':skipped}
        save('status.json',result);return result
    body=packet['packet']
    from zoneinfo import ZoneInfo
    day=now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
    # Fail before any paid call if the complete review lacks minimum headroom.
    for period,cap in state['limits_microeur'].items():
        entries=[e for e in state['entries'].values() if period=='lifetime'
                 or period=='daily' and e['day']==day
                 or period=='monthly' and e['day'][:7]==day[:7]]
        if cap-sum(e['reserved'] if e['actual'] is None else e['actual'] for e in entries)<150000:
            result={'state':'budget_deferred','model_calls':0,'trade_authorized':False}
            save('status.json',result);return result
    client.ledger.reserve(cooldown,1,now);client.ledger.settle(cooldown,0)
    client.ledger.reserve(attempt,1,now);client.ledger.settle(attempt,0)
    save('packet.json',packet)
    if comparison is not None:
        comparison.begin_review(packet, now=clock())
    try:
        audit=run_metered(client,packet,document,feed,path=root/'review.json',clock=clock,enabled=True)
    finally:
        if comparison is not None:
            comparison.reconcile_cost(packet, client.ledger.store.load()[0], now=clock())
    current,current_feed=refresh(body['symbol'])
    save('fresh-capture.json',current);save('fresh-news.json',current_feed)
    decision=finalize(packet,audit,current,current_feed,now=clock())
    save('decision.json',decision)
    if comparison is not None:
        comparison.record_review(packet, audit, decision, now=clock())
    if decision['verdict'] == 'PAPER_WATCH_FOR_ENTRY':
        from .paper_tracking import PaperTracker
        tracker = PaperTracker(root/'paper-journal.sqlite')
        tracker.register(decision)
        save('paper-tracking.json', tracker.report(now=clock()))
    archive=export_archive(packet,audit,decision)
    save("dashboard-archive.json",archive)
    receipt=deliver(archive)
    save('delivery.json',receipt)
    status={'state':'paper_decision_completed','model_calls':8,
            'verdict':decision['verdict'],'trade_authorized':False}
    save('status.json',status)
    return status


def export_archive(packet,audit,decision):
    return {'schema_version':'paper-decision-archive-v1','trade_authorized':False,'plan':None,
            'candidate_id':decision['candidate_id'],'completed_at':decision['evaluated_at'],
            'evidence_expires_at':decision['plan']['expires_at'] if decision['plan'] else decision['evaluated_at'],
            'packet_id':packet['packet_id'],'packet_json':canonical(packet['packet']),
            'decision':decision,'review':audit}


def main():
    """Zero-cost packet preview, used by the collector. Never dispatches models."""
    import argparse,json
    from pathlib import Path
    from datetime import timezone
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=build_packets(json.loads(args.capture.read_text()),json.loads(args.evidence.read_text()),now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'paper_review_ready':len(result['packets']),'model_calls':0,'trade_authorized':False}))


if __name__=='__main__':main()
