"""Bounded free strategy research: fresh market reads, immutable artifacts, no AI/orders."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from .candidate_packages import canonical, digest
from .chart_news import checked_source
from .news_input import build_news_input
from .knowledge_shadow import bounded_json
from .strategy_registry import route, baseline_strategy, ALL, CORE, OFFLINE, PROTOCOL_ID
from .strategy_knowledge import Retriever, summary as library_summary
from .strategy_pair import prepare as prepare_pair, VALIDATION_START
from .paper_comparison import aware
from ..market_data.limits import STOCK_RESEARCH_LIMIT


def permitted(now):
    now=aware(now);ny=now.astimezone(ZoneInfo('America/New_York'));dublin=now.astimezone(ZoneInfo('Europe/Dublin'))
    return now>=aware(VALIDATION_START) and ny.weekday()<5 and (9,30)<=(ny.hour,ny.minute)<(16,0) and dublin.hour<22


def collect_inputs(capture,feed,discovery,manifest,*,env,clock):
    from ..market_data.providers.alpaca_batch import fetch_histories, discover_snapshots
    from ..market_data.stock_checks import collect
    symbols=list(dict.fromkeys(c['requested_symbol'] for c in capture['captures'] if c['market']=='stocks'))
    if len(symbols)>STOCK_RESEARCH_LIMIT:raise ValueError('routing_universe_capacity')
    contexts={r['payload']['symbol']:r for r in capture.get('stock_context',[])}
    links=discovery.get('catalyst_links',{}).get('rows',[])
    histories={};snapshots={};prior={r['symbol']:r for r in manifest.get('symbols',[]) if r.get('snapshot_status')=='fresh'}
    def histories_before_quotes():
        histories.update(fetch_histories(symbols,env=env,clock=clock))
        linked=sorted({r['source_symbol'] for r in links}|{r['symbol'] for r in links})
        if linked:
            if len(linked)>3:raise ValueError('competitor_universe_capacity')
            snapshots.update(discover_snapshots(linked,env=env,now=clock(),clock=clock,prior_snapshots=prior)['symbol_evidence'])
    refs=collect(symbols,env=env,clock=clock,before_quotes=histories_before_quotes,
                 catalogue_record=capture.get('stock_reference_checks')) if symbols else None
    now=aware(clock());batch=[];missing=[]
    for symbol in symbols:
        try:
            bars=histories[symbol]
            if bars.status!='ok':raise ValueError('missing_history')
            ctx=contexts.get(symbol);context={}
            if ctx and digest(ctx['payload'])==ctx['payload_sha256']:context=deepcopy(ctx['payload'])
            p=deepcopy(refs['payload']);p['symbols']=[symbol]
            p['catalogue_candidates']={symbol:p.get('catalogue_candidates',{}).get(symbol,[])}
            p['quotes']={'currency':'USD','quotes':{symbol:p.get('quotes',{}).get('quotes',{}).get(symbol,{})}}
            news=None
            try:news=build_news_input(feed,symbol=symbol,now=now).model_dump(mode='json')
            except (ValueError,TypeError,KeyError):pass
            batch.append({'symbol':symbol,'candles':[b.model_dump(mode='json') for b in bars.candles],
                'bars_received_at':bars.retrieved_at.isoformat(),'daily':context.get('daily',{}).get('bars',[]),
                'context':context,'news_check':checked_source(feed,symbol=symbol,now=now),'news_input':news,
                'reference_checks':{'payload':p,'payload_sha256':digest(p)},
                'competitor_evidence':{'links':[r for r in links if r['symbol']==symbol],'snapshots':snapshots}})
        except (ValueError,TypeError,KeyError,AttributeError):missing.append(symbol)
    return batch,now,{'selected_symbols':symbols,'source_missing_symbols':missing}


def evaluate_batch(inputs,library,*,now,include_offline=False):
    tick=monotonic();now=aware(now);retriever=Retriever(library);rows=[];pairs=[];overlaps=[];baseline=[]
    if len(inputs)>STOCK_RESEARCH_LIMIT or len({i['symbol'] for i in inputs})!=len(inputs):raise ValueError('routing_batch_identity_or_capacity')
    for source in inputs:
        variants=route(source,now=now,include_offline=include_offline);rows.extend(variants)
        selected=baseline_strategy(source,now=now)
        baseline.append({'candidate_id':'stocks:'+source['symbol'],'original_selected_strategy':selected,
            'additional_eligible_core_strategies':[r['strategy_id'] for r in variants if r['eligible'] and r['strategy_id'] in CORE and r['strategy_id']!=selected]})
        eligible=[r for r in variants if r['eligible'] and not r['offline_only']]
        if len(eligible)>1:overlaps.append({'candidate_id':'stocks:'+source['symbol'],
            'strategies':[r['strategy_id'] for r in eligible],'alternative_plans_not_additive_positions':True})
        for result in eligible:
            pairs.append(prepare_pair(result,source,retriever,now=now))
    return {'schema_version':'strategy-routing-report-v2','routing_protocol_id':PROTOCOL_ID,'as_of':now.isoformat(),
        'library':library_summary(library),'symbols_evaluated':len(inputs),'strategy_evaluations':len(rows),
        'eligible_by_strategy':{s:sum(r['strategy_id']==s and r['eligible'] for r in rows) for s in ALL},
        'blockers':dict(Counter(b for r in rows for b in r['blockers'])), 'overlap_groups':overlaps,
        'single_label_baseline':baseline,'additional_eligible_core_setups':sum(len(b['additional_eligible_core_strategies']) for b in baseline),
        'rows':rows,'pairs':pairs,'research_pairs':len(pairs),'evaluation_seconds':round(monotonic()-tick,6),
        'model_calls':0,'trade_authorized':False,'performance_claim':None,
        'note':'Multiple strategies on one stock are overlapping alternatives, not independent positions. No outcomes inferred from qualification.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--news',type=Path,required=True)
    p.add_argument('--discovery',type=Path);p.add_argument('--manifest',type=Path)
    p.add_argument('--library',type=Path,default=Path('knowledge/strategy-library-20261113.json'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True);now=datetime.now(UTC)
    library=bounded_json(args.library,10_000_000)
    if not permitted(now):
        # Still verify the installed library without market/provider/model access.
        result={'state':'outside_strategy_validation_or_session','as_of':now.isoformat(),
                'library':library_summary(library),'routing_protocol_id':PROTOCOL_ID,'model_calls':0,'trade_authorized':False}
    else:
        capture=bounded_json(args.capture,4_000_000);feed=bounded_json(args.news,2_000_000)
        discovery=bounded_json(args.discovery,4_000_000) if args.discovery and args.discovery.is_file() else {}
        manifest=bounded_json(args.manifest,4_000_000) if args.manifest and args.manifest.is_file() else {}
        sources,at,coverage=collect_inputs(capture,feed,discovery,manifest,env=os.environ,clock=lambda:datetime.now(UTC))
        (args.output/'frozen-inputs.json').write_text(canonical({'as_of':at.isoformat(),'inputs':sources,'coverage':coverage})+'\n')
        result=evaluate_batch(sources,library,now=at);result['coverage']=coverage;result['state']='research_prepared'
        pairs=result.pop('pairs');(args.output/'paired-inputs.json').write_text(canonical(pairs)+'\n')
    (args.output/'report.json').write_text(canonical(result)+'\n')
    print(canonical({k:v for k,v in result.items() if k not in ('rows','library')}))


if __name__=='__main__':main()
