"""Historical market input with synthetic model replies: never a live AI test."""
from datetime import timedelta
from pathlib import Path
import json
import pytest

from market_radar_ai.agents.crypto_input import CryptoResearchInput
from market_radar_ai.agents.live_research import run_research
from test_live_research import setup


def recorded_packet():
    fixture=json.loads((Path(__file__).parent/'fixtures/live_crypto_trial.json').read_text())
    return CryptoResearchInput.model_validate(fixture['input'])


@pytest.mark.parametrize('bad_stage', [None, *range(8)])
def test_historical_crypto_full_protocol(tmp_path,monkeypatch,bad_stage):
    packet=recorded_packet()
    seen=[]
    def reply(data,payload):
        stage=len(seen)
        seen.append(payload)
        metrics=payload['computed_metrics']
        data['source_ids']=[packet.market.source_id()]
        data['metric_claims']=[dict(metric='window_high',value='68961.8',
            quote_currency='EUR',source_id=packet.market.source_id())]
        if stage==bad_stage:
            data['metric_claims'][0]['value']='68914.9'
        if 'rationale' in data:
            data['verdict']='INSUFFICIENT_EVIDENCE'
            data['rationale']='News and broker eligibility remain unverified. No trade is authorized.'
        assert metrics['values']['window_high']=='68961.8'
        assert payload['snapshot']['news'] is None
    _,client,store,requests=setup(monkeypatch,mutate=reply,packet_override=packet)
    path=tmp_path/'replay.json'
    # Historical clock is used only inside this test. Production freshness
    # validation is unchanged; this old capture is not current evidence.
    if bad_stage is None:
        result=run_research(client,packet,path=path,clock=lambda:packet.assembled_at,enabled=True)
        assert result['state']=='completed' and len(requests)==8
        assert result['conclusion']['verdict']=='INSUFFICIENT_EVIDENCE'
        assert len(result['assessments'])==6 and len(result['unresolved_concerns'])==6
        assert result['analysis_quality']=='requires_human_review'
    else:
        with pytest.raises(RuntimeError):
            run_research(client,packet,path=path,clock=lambda:packet.assembled_at,enabled=True)
        result=json.loads(path.read_text())
        assert result['state']=='blocked_or_failed'
        assert result['calls'][-1]['state']=='rejected'
        assert len(requests)==bad_stage+1
        assert result['conclusion'] is None
    assert result['mandatory_missing_data']==list(packet.missing_data)
    assert result['trade_authorized'] is False
    assert all(entry['actual'] is not None for entry in store.state['entries'].values())
    assert all('assessments' not in p for p in seen[:6])
    if len(seen)>6:
        assert len(seen[6]['assessments'])==6
        assert seen[6]['mandatory_missing_data']==list(packet.missing_data)


def test_historical_capture_cannot_be_reused_as_current(tmp_path,monkeypatch):
    packet=recorded_packet()
    _,client,store,requests=setup(monkeypatch,packet_override=packet)
    with pytest.raises(RuntimeError):
        run_research(client,packet,path=tmp_path/'stale.json',
            clock=lambda:packet.assembled_at+timedelta(days=1),enabled=True)
    assert not requests and not store.state['entries']
