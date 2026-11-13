"""Exercise retrieval on explicitly synthetic future queries without models/network."""
import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
from time import perf_counter

from market_radar_ai.agents.candidate_packages import canonical, digest
from market_radar_ai.agents.knowledge_cases import library_summary, retrieve, MAX_EXTRACT_BYTES
from market_radar_ai.agents.knowledge_pair import PROTOCOL_ID
from market_radar_ai.agents.knowledge_playbooks import RULES
from market_radar_ai.agents.paper_comparison import GUARDED_PROTOCOL


def verify(path):
    library=json.loads(path.read_text())
    result={'schema_version':'knowledge-offline-receipt-v1','protocol_id':PROTOCOL_ID,
        'verified_at':datetime.now(UTC).isoformat(),'library':library_summary(library),
        'source_partitions':library['partitions'], 'query_dataset':'synthetic_future_queries_not_forward_evidence',
        'model_calls':0,'paid_ai_cost_eur':'0','trade_authorized':False,'queries':[],'performance_claim':None}
    for strategy in sorted(RULES):
        at=datetime(2026,11,16,15,0,tzinfo=UTC)
        body={'candidate_id':'stocks:SYNTHETIC','symbol':'SYNTHETIC','assembled_at':at.isoformat(),
            'quote_observation_policy':GUARDED_PROTOCOL['quote_observation_policy'],
            'technical_checks':{'strategy_id':strategy,'relative_volume_5_vs_15':'1.6',
                'relative_volume_3_vs_prior':'1.6','momentum_20_bars_pct':'1.5','momentum_window_pct':'1.5'},
            'reference_checks':{'indicative_bid_eur':'99.99','indicative_ask_eur':'100'}}
        packet={'packet_id':digest(body),'packet':body}
        tick=perf_counter();context=retrieve(packet,library,as_of=at);seconds=perf_counter()-tick
        assert len(context['cases'])<=3 and len(canonical(context).encode())<=MAX_EXTRACT_BYTES
        assert context==retrieve(packet,library,as_of=at)
        result['queries'].append({'strategy':strategy,'retrieved':len(context['cases']),
            'eligible_cases':context['eligible_cases'],'extract_bytes':len(canonical(context).encode()),
            'retrieval_seconds':round(seconds,6), 'case_source_ids':[c['source_id'] for c in context['cases']]})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,default=Path('knowledge/library-20261113.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=verify(args.library)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(canonical(result)+'\n')
    print(canonical(result))


if __name__=='__main__':main()
