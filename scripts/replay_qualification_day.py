"""Offline, timestamp-faithful admission replay; no providers, AI or trades.

Uses each retained capture and original evaluation time. Reports eligible setups,
not hypothetical returns. Missing evidence and failed captures remain explicit.
"""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter
from market_radar_ai.agents.qualification import qualify
from market_radar_ai.agents.paper_review_prompts import VERSION

p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
index=json.loads((args.input/'index.json').read_text());runs=[];old_counts=Counter();new_counts=Counter();old_ready=set();new_ready=set()
for item in sorted(index,key=lambda x:x['run']):
 folder=args.input/str(item['run']);required=['enriched-capture.json','news.json','qualification.json']
 if any(not (folder/f).exists() for f in required):
  runs.append({'run':item['run'],'state':'missing_capture_or_qualification','files':item.get('files')});continue
 try:
  old=json.loads((folder/'qualification.json').read_text());now=datetime.fromisoformat(old['evaluated_at']);doc=json.loads((folder/'enriched-capture.json').read_text());feed=json.loads((folder/'news.json').read_text());new=qualify(doc,feed,now=now)
  previous=[r for r in old['candidates'] if r['market']=='stocks'];current=[r for r in new['candidates'] if r['market']=='stocks']
  a={r['symbol'] for r in previous if r.get('eligible_for_paper_review')};b={r['symbol'] for r in current if r.get('eligible_for_paper_review')}
  old_ready.update(a);new_ready.update(b)
  old_counts.update(b for r in previous for b in r.get('paper_blockers',[]));new_counts.update(b for r in current for b in r.get('paper_blockers',[]))
  # One-factor ablations on the actual old rejection records, not a hindsight buy list.
  news_only=sum(not(set(r.get('paper_blockers',[]))-{'current_symbol_linked_news_missing'}) for r in previous)
  volume_only=sum(not(set(r.get('paper_blockers',[]))-{'relative_volume_below_1_5'}) for r in previous)
  runs.append({'run':item['run'],'evaluated_at':old['evaluated_at'],'state':'replayed','stock_rows':len(current),
   'old_ready':sorted(a),'new_ready':sorted(b),'new_strategies':dict(Counter(r['technical_checks'].get('strategy_id') for r in current if r.get('eligible_for_paper_review'))),
   'remove_news_gate_only_upper_bound':news_only,'remove_volume_gate_only_upper_bound':volume_only,
   'input_sha256':{f:hashlib.sha256((folder/f).read_bytes()).hexdigest() for f in required}})
 except (ValueError,KeyError,TypeError) as e:runs.append({'run':item['run'],'state':'invalid_saved_evidence','reason':type(e).__name__})
replayed=[r for r in runs if r['state']=='replayed']
result={'schema_version':'offline-admission-replay-v1','policy':VERSION,'dataset_kind':'historical_diagnostic_not_forward_performance',
 'runs_requested':len(index),'runs_replayed':len(replayed),'runs_unavailable':len(index)-len(replayed),
 'old_ready_observations':sum(len(r['old_ready']) for r in replayed),'new_ready_observations':sum(len(r['new_ready']) for r in replayed),
 'old_unique_symbols':sorted(old_ready),'new_unique_symbols':sorted(new_ready),
 'old_blocker_observations':dict(old_counts),'new_blocker_observations':dict(new_counts),'runs':runs,
 'model_calls':0,'orders':0,'profitability_established':False,
 'limitations':['Repeated symbol/run observations are not independent trades.','No unseen symbols or prices reconstructed.','Ablations are upper bounds, not proposed removal of all news or volume checks.','No AI approvals or entry/exit fills inferred; no P/L attributed to the new policy.','Rules were informed by this day; future sessions are the holdout.']}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('runs','old_blocker_observations','new_blocker_observations')}))
