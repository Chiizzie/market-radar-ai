from datetime import datetime, timezone
from market_radar_ai.market_data.capture import capture_crypto_bounded
from market_radar_ai.market_data.models import ProviderResult


def test_provider_outage_stops_request_fanout_and_preserves_missing_identities():
    calls=[]
    pairs=[f'PAIR{i}' for i in range(30)]
    def fetch(pair):
        calls.append(pair)
        return ProviderResult(provider='kraken',retrieved_at=datetime.now(timezone.utc),status='error')
    rows=capture_crypto_bounded(pairs,fetch=fetch)
    assert len(calls)==2 and list(rows)==pairs
    assert all(r.status=='error' and not r.candles for r in rows.values())
    assert all(rows[p].issues[0].code=='provider_circuit_open' for p in pairs[2:])


def test_single_bad_pair_does_not_stop_healthy_provider():
    calls=[]
    def fetch(pair):
        calls.append(pair)
        return ProviderResult(provider='kraken',retrieved_at=datetime.now(timezone.utc),
                              status='error' if pair=='BAD' else 'ok')
    rows=capture_crypto_bounded(['BAD','OK','NEXT'],fetch=fetch)
    assert len(calls)==3 and rows['NEXT'].status=='ok'
