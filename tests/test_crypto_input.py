from datetime import timedelta
import json
import pytest
from test_news_input import NOW
from market_radar_ai.market_data.models import Candle,ProviderResult
from market_radar_ai.market_data.capture import capture_markets
from market_radar_ai.agents.crypto_input import build_crypto_input,CryptoResearchInput,GAPS
from market_radar_ai.agents.live_research import preflight,run_research


def capture(pair='XBTEUR'):
    rows=[Candle(symbol=pair,interval='5m',timestamp=NOW-timedelta(minutes=n),
        open=100,high=102,low=99,close=101,volume=50,quote_currency='EUR',source='kraken') for n in (15,10,5)]
    return capture_markets([],[pair],stock_fetch=None,crypto_fetch=lambda _:ProviderResult(
        provider='kraken',retrieved_at=NOW,candles=rows),now=NOW)


@pytest.mark.parametrize('pair',['XBTEUR','ETHEUR','SOLEUR'])
def test_crypto_packet_preserves_missing_news_and_eligibility(pair):
    packet=build_crypto_input(capture(pair),symbol=pair,now=NOW)
    assert packet.news is None and packet.broker_eligibility=='UNKNOWN'
    assert packet.missing_data==GAPS and packet.market.quote_currency=='EUR'
    assert CryptoResearchInput.model_validate(packet.model_dump(mode='json')).digest()==packet.digest()
    assert preflight(packet,now=NOW).digest()==packet.digest()
    with pytest.raises(ValueError):preflight(packet,now=NOW+timedelta(hours=1))


@pytest.mark.parametrize('field,value',[('missing_data',[]),('broker_eligibility','VERIFIED'),('news',{}),('source_ids',['fake'])])
def test_crypto_gaps_cannot_be_erased(field,value):
    data=build_crypto_input(capture(),symbol='XBTEUR',now=NOW).model_dump(mode='json')
    data[field]=value
    with pytest.raises(ValueError):CryptoResearchInput.model_validate(data)


def test_crypto_dry_runner_never_fetches_equity_news(tmp_path,monkeypatch):
    from market_radar_ai.agents import github_live_research as runner
    from test_github_live_research import ENV,forbid_paid
    monkeypatch.setattr(runner,'capture_markets',lambda *a,**kw:capture())
    def forbidden(**kw):pytest.fail('Stock news cannot be used for crypto')
    monkeypatch.setattr(runner,'fetch_feed',forbidden);forbid_paid(monkeypatch)
    status=runner.execute(tmp_path,env={**ENV,'RESEARCH_TARGET':'XBTEUR'},clock=lambda:NOW)
    assert status['state']=='ready_dry_run' and status['model_calls']==0
    assert json.loads((tmp_path/'news.json').read_text())['status']=='not_connected'


def test_crypto_runs_all_eight_stubbed_research_stages(tmp_path,monkeypatch):
    import test_live_research as fixture
    packet=build_crypto_input(capture(),symbol='XBTEUR',now=NOW)
    monkeypatch.setattr(fixture,'build_combined_input',lambda *a,**kw:packet)
    _,client,store,requests=fixture.setup(monkeypatch)
    result=run_research(client,packet,path=tmp_path/'analysis.json',clock=lambda:NOW,enabled=True)
    assert len(requests)==8 and result['state']=='completed'
    assert result['mandatory_missing_data']==list(GAPS) and not result['trade_authorized']
    assert all(json.loads(r['input'])['snapshot']['news'] is None for r in requests)
    from market_radar_ai.agents.paper_team import ResearchInput
    with pytest.raises(ValueError):ResearchInput.model_validate(packet.model_dump(mode='json'))
