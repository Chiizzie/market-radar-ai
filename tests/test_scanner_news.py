from datetime import datetime, timezone
from market_radar_ai.evidence.scanner_feed import collect
from market_radar_ai.dashboard.evidence import export_evidence

NOW = datetime(2026, 11, 3, 20, tzinfo=timezone.utc)


def feed(name):
    return {'status': 'ok', 'scope': 'NEWS_LEADS', 'retrieved_at': NOW.isoformat(),
        'items': [{'kind': 'news', 'title': 'Publisher report', 'source': name,
                   'url': 'https://example.com/'+name, 'published_at': NOW.isoformat(),
                   'retrieved_at': NOW.isoformat(), 'symbols': []}]}


def test_bounded_collection_and_non_authorization():
    calls=[]
    def company(name): calls.append(name); return feed(name)
    def public(*, source): calls.append(source); return feed(source)
    result=collect(company_fetch=company, public_fetch=public, clock=lambda:NOW)
    assert len(calls)==6 and len(result['items'])==6
    assert result['trade_authorized'] is False and result['coverage_complete'] is False
    exported=export_evidence(result,now=NOW)
    assert 'NO_CRYPTO_COVERAGE' in exported['scope']
    assert all(not item['symbols'] for item in exported['items'])


def test_source_failure_is_partial_not_hidden_or_secret_bearing():
    def fail(*args, **kwargs): raise RuntimeError('SECRET_VALUE')
    result=collect(company_fetch=fail,public_fetch=lambda **kw:feed(kw['source']),clock=lambda:NOW)
    assert result['status']=='partial'
    assert sum(s['status']=='error' for s in result['sources'])==3
    assert 'SECRET_VALUE' not in str(result)


def test_total_failure_remains_unavailable():
    def fail(*args, **kwargs): raise ValueError()
    result=collect(company_fetch=fail,public_fetch=fail,clock=lambda:NOW)
    assert result['status']=='error' and result['items']==[]
    assert export_evidence(result,now=NOW)['status']=='error'


def test_duplicate_articles_do_not_become_independent_confirmation():
    result=collect(company_fetch=lambda _:feed('same'),public_fetch=lambda **_:feed('same'),clock=lambda:NOW)
    assert len(result['items'])==1 and result['status']=='partial'
