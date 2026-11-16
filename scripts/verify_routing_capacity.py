"""Verify the failed real input archive without market/model/order operations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from market_radar_ai.agents.strategy_routing_live import load_manifest, MANIFEST_MAX_BYTES
from market_radar_ai.agents.knowledge_shadow import bounded_json
from market_radar_ai.agents.candidate_packages import canonical
from market_radar_ai.market_data.limits import STOCK_RESEARCH_LIMIT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=args.input_dir
    path=root/'discovery-selection.json';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='87f0b0632191a4cebf9c3c43ea7db7f7d5a016a78ee086cb9374dca2b9de6926':
        raise ValueError('unexpected_incident_source')
    try:bounded_json(path,4_000_000)
    except ValueError as exc:
        if str(exc)!='knowledge_input_capacity':raise
    else:raise AssertionError('Original capacity failure did not reproduce')
    original=json.loads(raw);restored=load_manifest(path)
    assert restored==original
    capture=bounded_json(root/'enriched-capture.json',4_000_000)
    bounded_json(root/'news.json',2_000_000)
    discovery=bounded_json(root/'discovery.json',4_000_000)
    selected={r['requested_symbol'] for r in capture['captures'] if r['market']=='stocks'}
    linked={s for r in discovery.get('catalyst_links',{}).get('rows',[]) for s in (r['symbol'],r['source_symbol'])}
    assert len(selected)<=STOCK_RESEARCH_LIMIT and len(linked)<=3
    before={r['symbol']:r for r in original['symbols'] if r.get('snapshot_status')=='fresh'}
    after={r['symbol']:r for r in restored['symbols'] if r.get('snapshot_status')=='fresh'}
    assert before==after
    result={'state':'incident_input_roundtrip_verified','input_bytes':len(raw),
        'input_sha256':hashlib.sha256(raw).hexdigest(),'symbols':len(restored['symbols']),
        'selected_stocks':len(selected),'linked_stocks':len(linked),
        'fresh_prior_observations':len(after),'row_content_unchanged':True,
        'maximum_manifest_bytes':MANIFEST_MAX_BYTES,'original_failure_reproduced':True,
        'provider_calls':0,'model_calls':0,'trade_authorized':False,
        'scope':'Input handling only; no fresh collection or performance outcome inferred.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(canonical(result)+'\n');print(canonical(result))


if __name__=='__main__':main()
