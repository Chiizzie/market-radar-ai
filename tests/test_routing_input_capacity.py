"""Catalogue-scale input regressions, with no provider/model/broker calls."""
import json
from types import SimpleNamespace

import pytest

from market_radar_ai.agents import strategy_routing_live as live
from market_radar_ai.agents.candidate_packages import canonical
from market_radar_ai.agents.knowledge_shadow import bounded_json
from test_strategy_routing import knowledge, pullback_input


def manifest(rows):
    return {'schema_version':'stock-selection-trace-v1', 'trade_authorized':False,
            'symbols':rows}


def test_catalogue_larger_than_capture_limit_preserves_all_rows_through_real_cli(tmp_path, monkeypatch):
    source, now = pullback_input()
    rows = [{'symbol':f'S{i:05}', 'snapshot_status':'fresh',
             'observed_at':now.isoformat(), 'price':str(i+1),
             'chart_diagnostics':{'detail':'x'*700}} for i in range(6000)]
    rows[-1].update(symbol='NVDA', prior_observation={'price':'100','observed_at':now.isoformat()})
    original=manifest(rows)
    paths={}
    for name, payload in [('manifest',original),('capture',{'captures':[]}),
                          ('news',{}),('discovery',{}),('library',knowledge())]:
        paths[name]=tmp_path/(name+'.json');paths[name].write_text(canonical(payload))
    assert paths['manifest'].stat().st_size>4_000_000
    with pytest.raises(ValueError,match='knowledge_input_capacity'):
        bounded_json(paths['manifest'],4_000_000)
    assert live.load_manifest(paths['manifest'])==original
    reached=[]
    def collect(capture, feed, discovery, selected, **kwargs):
        assert selected==original and selected['symbols'][-1]['symbol']=='NVDA'
        reached.append(True)
        return [source],now,{'selected_symbols':['TEST'],'source_missing_symbols':[]}
    monkeypatch.setattr(live,'collect_inputs',collect)
    monkeypatch.setattr(live,'datetime',SimpleNamespace(now=lambda *a:now))
    output=tmp_path/'output'
    argv=['routing','--output',str(output)]
    for name,path in paths.items():argv.extend(['--'+name,str(path)])
    monkeypatch.setattr('sys.argv',argv)
    live.main()
    report=json.loads((output/'report.json').read_text())
    assert reached==[True] and report['state']=='research_prepared'
    assert report['symbols_evaluated']==1 and report['research_pairs']>=2
    assert report['model_calls']==0 and report['trade_authorized'] is False
    assert json.loads((output/'health.json').read_text())['state']=='completed'


@pytest.mark.parametrize('fault,code',[
    ('root','shape'),('schema','shape'),('authorization','shape'),('rows','shape'),
    ('duplicate','symbol_identity'),('invalid_symbol','symbol_identity'),('non_object','symbol_identity'),
    ('too_many','symbol_capacity')])
def test_manifest_rejects_invalid_identity_and_row_capacity(tmp_path,monkeypatch,fault,code):
    doc=manifest([{'symbol':'A'},{'symbol':'B'}])
    if fault=='root':doc=[]
    if fault=='schema':doc['schema_version']='unknown'
    if fault=='authorization':doc['trade_authorized']=True
    if fault=='rows':doc['symbols']={}
    if fault=='duplicate':doc['symbols'][1]['symbol']='A'
    if fault=='invalid_symbol':doc['symbols'][0]['symbol']='../../x'
    if fault=='non_object':doc['symbols'][0]=None
    if fault=='too_many':monkeypatch.setattr(live,'MAX_SYMBOLS',1)
    path=tmp_path/'manifest.json';path.write_text(canonical(doc))
    with pytest.raises(ValueError,match='routing_manifest_'+code):live.load_manifest(path)


def test_manifest_reads_at_most_the_byte_bound_plus_one(tmp_path,monkeypatch):
    path=tmp_path/'manifest.json';raw=canonical(manifest([{'symbol':'A'}])).encode()
    path.write_bytes(raw);monkeypatch.setattr(live,'MANIFEST_MAX_BYTES',len(raw))
    assert live.load_manifest(path)['symbols']==[{'symbol':'A'}]
    path.write_bytes(raw+b' ')
    with pytest.raises(ValueError,match='routing_manifest_capacity'):live.load_manifest(path)
    assert live.load_manifest(None)=={} and live.load_manifest(tmp_path/'missing')=={}


def test_failure_retains_diagnostic_artifact_without_publishing_success(tmp_path,monkeypatch):
    source,now=pullback_input();output=tmp_path/'output'
    monkeypatch.setattr(live,'datetime',SimpleNamespace(now=lambda *a:now))
    monkeypatch.setattr('sys.argv',['routing','--capture','missing','--news','missing',
        '--library','missing','--output',str(output)])
    with pytest.raises(FileNotFoundError):live.main()
    health=json.loads((output/'health.json').read_text())
    assert health['state']=='failed' and health['error_type']=='FileNotFoundError'
    assert health['model_calls']==0 and not health['trade_authorized']
    assert not (output/'report.json').exists()
