"""Read-only import of three existing method journals; never reinterpret old fills."""
import argparse
from datetime import UTC, datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .candidate_packages import digest, canonical
from .comparison_live import EventClient, event_id, restore_event_timestamp
from .knowledge_cases import outcome
from .method_shadow import MethodShadow, KINDS
from .paper_comparison import aware
from .strategy_registry import METHODS, source_policy
from .strategy_knowledge import imported_v1, compact_features, case_identity, seal, summary, CUTOFF


def checked(raw, strategy, day, after):
    experiment=digest(METHODS[strategy][1]);e=restore_event_timestamp(experiment,raw)
    if (type(e['seq']) is not int or e['seq']<=after or e['experiment_id']!=experiment or e['day']!=day
            or aware(e['occurred_at']).date().isoformat()!=day or e['kind'] not in KINDS
            or event_id(experiment,e)!=e['event_id']):raise ValueError('invalid_method_history_event')
    aware(e['received_at']);return e


def download(client, path, *, strategy, day):
    after=0;count=0
    with gzip.open(path,'wt') as out:
        for _ in range(2000):
            page=client.read(digest(METHODS[strategy][1]),day,after)
            if not page['events']:return
            for raw in page['events']:
                e=checked(raw,strategy,day,after);after=e['seq'];count+=1
                if count>100000:raise ValueError('method_history_capacity')
                out.write(canonical(e)+'\n')
            if page['next']!=after:raise ValueError('method_history_cursor')
    raise ValueError('method_history_page_capacity')


def replay(path, *, strategy, day):
    h=hashlib.sha256();count=accepted=excluded=after=0;original={}
    with TemporaryDirectory() as tmp:
        worker=MethodShadow(tmp,client=None,day=day,early_opening=strategy=='opening_range_15m_shadow_v1',
                            competitor=strategy=='competitor_strength_breakout_shadow_v1')
        with gzip.open(path,'rb') as source:
            for line in source:
                if len(line)>2_000_000 or count>=100000:raise ValueError('method_history_capacity')
                h.update(line);e=checked(json.loads(line),strategy,day,after);after=e['seq'];count+=1
                if max(aware(e['occurred_at']),aware(e['received_at']))>aware(CUTOFF):excluded+=1;continue
                p=json.loads(e['payload_json'])
                if e['kind']=='quote' and aware(p['received_at'])>aware(CUTOFF):excluded+=1;continue
                worker.apply(e);accepted+=1
                if e['kind']=='method_enrol':original.setdefault(p['setup_id'],(p['inputs'],p['scenario'],e['event_id']))
        rows=[]
        for r in worker.outcomes(aware(CUTOFF)):
            inputs,scenario,enrol_event=original[r['setup_id']]
            c={'source_setup_id':r['setup_id'],'source_event_id':enrol_event,'input_sha256':digest(inputs),
                'strategy_id':strategy,'source_protocol_id':worker.experiment,'source_policy':source_policy(strategy),
                'candidate_id':r['candidate_id'],'enrolled_at':r['enrolled_at'],'known_at':CUTOFF,
                'features':compact_features(inputs,scenario),'code_only':outcome(r).model_dump(mode='json'),
                'ai_reviewed':{'state':'not_reviewed','reason':None,'net_pnl_eur':None,'observations_available':None,'simulated':True},
                'rejected_counterfactual_only':False}
            rows.append({'case_id':case_identity(c),**c})
    return rows,{'strategy_id':strategy,'day':day,'source_events':count,'accepted_events':accepted,
                'after_cutoff_excluded':excluded,'last_source_seq':after,'journal_sha256':h.hexdigest(),'cases':len(rows)}


def build(root, base, *, built_at=None):
    rows=imported_v1(base);manifests=[]
    for strategy in sorted(METHODS):
        for day in ('2026-11-12','2026-11-13'):
            found,m=replay(root/f'{strategy}-{day}.jsonl.gz',strategy=strategy,day=day)
            rows.extend(found);manifests.append(m)
    return seal(rows,base_library_id=base['library_id'],built_at=built_at or datetime.now(UTC),manifests=manifests)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--download',action='store_true')
    p.add_argument('--built-at');p.add_argument('--base',type=Path,default=Path('knowledge/library-20261113.json'))
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.download and args.built_at:raise ValueError('cannot_backdate_download')
    if args.download:
        client=EventClient(os.environ.get('REVIEW_INGEST_SECRET',''))
        for strategy in sorted(METHODS):
            for day in ('2026-11-12','2026-11-13'):
                download(client,args.output/f'{strategy}-{day}.jsonl.gz',strategy=strategy,day=day)
    library=build(args.output,json.loads(args.base.read_text()),built_at=args.built_at)
    (args.output/'library.json').write_text(canonical(library)+'\n')
    (args.output/'summary.json').write_text(canonical(summary(library))+'\n');print(canonical(summary(library)))


if __name__=='__main__':main()
