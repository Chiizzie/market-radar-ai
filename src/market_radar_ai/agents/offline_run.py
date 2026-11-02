"""One-command synthetic integration run. No network, model spend or live orders."""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .roles import AgentRole
from .paper_team import ResearchInput, PaperPlan, SimulatedAgent
from .model_gateway import ModelGateway, ModelReply, MockTransport
from .spending import SpendingLedger
from .debate import DebateCoordinator, Adjudication, Rebuttal
from .debate_store import DebateStore, run_recorded_debate
from .paper_outcomes import Quote, record_replay
from .reporting import export_run, outcome_summary


def run_offline(directory, scenario='supported'):
    if scenario not in ('supported','objection'): raise ValueError('Unknown scenario')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    now=datetime(2026,11,2,15,tzinfo=ZoneInfo('Europe/Dublin'))
    run_id=f'synthetic-v1-{scenario}'
    snapshot=ResearchInput(candidate_id=run_id,symbol='FICTIONAL',observed_at=now,
        asset_class='equity',broker='trading212_invest',broker_verified_until=now+timedelta(hours=1),
        quality_passed=True,source_ids=('synthetic-fixture',),facts=('Synthetic integration fixture; not market data.',))
    plan=PaperPlan(entry=100,stop=99,target=102,quantity=10,costs_eur=1,
        invalidation='Synthetic support failure',exit_by=now.replace(hour=22))
    objection=scenario=='objection'
    replies=[ModelReply(SimulatedAgent(role,stance='support',source='synthetic-fixture',
        objections=('Catalyst unverified',) if objection and role==AgentRole.DEVILS_ADVOCATE else ()
        ).analyse(snapshot).model_dump_json()) for role in AgentRole]
    if objection:
        replies.append(ModelReply(Rebuttal(objection_id='O1',responder=AgentRole.TECHNICAL_ANALYST,
            explanation='Fixture has no independent catalyst verification',source_ids=('synthetic-fixture',)).model_dump_json()))
    replies.append(ModelReply(Adjudication(snapshot_id=snapshot.digest(),verdict='reject' if objection else 'support',
        rationale='Synthetic protocol test only',unresolved_ids=('O1',) if objection else ()).model_dump_json()))
    transport=MockTransport(replies)
    ledger=SpendingLedger(directory/'budget.sqlite3',100)
    coordinator=DebateCoordinator(ModelGateway(transport,ledger))
    store=DebateStore(directory/'audit.sqlite3')
    _,accepted=run_recorded_debate(coordinator,snapshot,plan=plan,run_id=run_id,now=now,store=store)
    if accepted:
        quotes=[Quote(observed_at=now,bid='99.9',ask='100'),
                Quote(observed_at=now+timedelta(minutes=1),bid='102',ask='102.1')]
        record_replay(store,run_id,quotes,entry_expires_at=now+timedelta(minutes=5))
    report=export_run(store,run_id)
    report_path=directory/f'{run_id}.json'
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    return {'run_id':run_id,'mode':'SIMULATED_RESEARCH','mock_requests_this_invocation':len(transport.requests),
            'report_path':str(report_path),'report':report,'summary':outcome_summary(store)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default='artifacts/offline-demo')
    parser.add_argument('--scenario',choices=['supported','objection'],default='objection')
    args=parser.parse_args()
    print(json.dumps(run_offline(args.output_dir,args.scenario),indent=2))


if __name__=='__main__': main()
