"""Offline integration receipt: fictional fixtures through all seven real detectors."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_strategy_routing import (pullback_input,method_input,opening_input,opening_continuation_input,
    mean_input,rehash,shifted,competitor_fixture,METHOD_NOW)
from datetime import timedelta
from market_radar_ai.agents.candidate_packages import canonical, digest
from market_radar_ai.agents.strategy_registry import ALL, OFFLINE, evaluate, PROTOCOL_ID
from market_radar_ai.agents.strategy_knowledge import Retriever, summary
from market_radar_ai.agents.strategy_pair import prepare, run, PROTOCOL_ID as PAIR_ID
from market_radar_ai.agents.strategy_routing_live import evaluate_batch


def verify(library):
    retriever=Retriever(library);rows=[];fake_calls=0
    fixtures={'trend_pullback_reclaim_v1':pullback_input,'trend_continuation_20bar_v1':pullback_input,
        'opening_continuation_30m_v1':opening_continuation_input,'opening_range_15m_shadow_v1':opening_input,
        'session_open_avwap_reclaim_v1':method_input,OFFLINE:mean_input,
        'competitor_strength_breakout_shadow_v1':lambda:(rehash(shifted(competitor_fixture())),METHOD_NOW+timedelta(days=10))}
    for strategy in ALL:
        source,now=fixtures[strategy]();tick=perf_counter();result=evaluate(source,strategy,now=now)
        if not result['eligible']:raise ValueError('offline_fixture_failed:'+strategy+':'+','.join(result['blockers']))
        row={'strategy_id':strategy,'detector_eligible':True,'offline_only':result['offline_only'],
            'planned_loss_eur':result['plan']['planned_loss_eur'],'result_id':result['result_id']}
        if strategy!=OFFLINE:
            pair=prepare(result,source,retriever,now=now)
            def ask(arm,prompt,schema,key):
                return {'data':{'verdict':'MORE_EVIDENCE_REQUIRED','rationale':'Synthetic integration fixture, not a market decision.',
                    'source_ids':[prompt['packet']['source_ids'][0]],'concerns':[]},'usage':{'synthetic':True,'paid_ai_cost_eur':'0'}}
            proof=run(pair,retriever,ask=ask,clock=lambda:now)
            assert proof['state']=='complete' and proof['trade_authorized'] is False
            fake_calls+=proof['model_calls']
            row.update(paired_harness_state=proof['state'],knowledge_bytes=pair['knowledge_bytes'],
                cases_retrieved=len(pair['arms']['knowledge']['reference_knowledge']['cases']))
        row['evaluation_seconds']=round(perf_counter()-tick,6);rows.append(row)
    s,now=pullback_input();overlap=evaluate_batch([s],library,now=now)
    assert overlap['additional_eligible_core_setups']>=1
    return {'schema_version':'strategy-routing-offline-receipt-v2','verified_at':datetime.now(UTC).isoformat(),
        'routing_protocol_id':PROTOCOL_ID,'paired_protocol_id':PAIR_ID,'library':summary(library),'fixtures':rows,
        'dataset_kind':'synthetic_future_fixtures_not_forward_evidence','synthetic_review_invocations':fake_calls,
        'model_calls':0,'paid_ai_cost_eur':'0','trade_authorized':False,'performance_claim':None,
        'overlap_proof':overlap['single_label_baseline']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',type=Path,default=Path('knowledge/strategy-library-20261113.json'))
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=verify(json.loads(args.library.read_text()));args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(canonical(result)+'\n');print(canonical(result))


if __name__=='__main__':main()
