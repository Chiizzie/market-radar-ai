"""A chart thesis may lack a catalyst; an unperformed/failed news check cannot pass."""
from datetime import datetime
from ..dashboard.evidence import export_evidence

SCOPE = 'PUBLISHER_TAGGED_STOCK_NEWS_PARTIAL'


def checked_source(feed, *, symbol, now):
    try:
        evidence = export_evidence(feed, now=now)
        if evidence['status'] not in ('ok', 'partial'):
            return None
        sources = [s for s in feed.get('sources', [])
                   if s.get('query_symbol') == symbol and s.get('scope') == SCOPE]
        if len(sources) != 1:
            return None
        source = sources[0]
        at = datetime.fromisoformat(source['retrieved_at'])
        ids = source['validated_evidence_ids']
        if (source['status'] not in ('ok', 'partial') or at.tzinfo is None
                or not 0 <= (now-at).total_seconds() <= 900
                or type(source['rejected_item_count']) is not int or source['rejected_item_count'] != 0
                or type(source['response_item_count']) is not int
                or not 0 <= source['response_item_count'] <= 10
                or type(source['validated_item_count']) is not int
                or not isinstance(ids, list) or len(ids) != source['validated_item_count']
                or len(set(ids)) != len(ids) or len(ids) != source['response_item_count']):
            return None
        retained = {i['evidence_id'] for i in evidence['items']
                    if i['kind'] == 'news' and symbol in i['symbols']}
        if not set(ids) <= retained:
            return None  # Global feed limits must not erase adverse-source evidence.
        return {'schema_version': 'chart-news-check-v1', 'query_symbol': symbol,
                'status': 'checked_bounded_source', 'scope': SCOPE,
                'checked_at': at.isoformat(), 'validated_item_count': len(ids),
                'coverage_complete': False, 'fresh_catalyst_required': False,
                'limitation': 'One publisher, at most ten articles over seven days. Absence of a fresh catalyst is not absence of news risk; reviewers must inspect retained headlines.'}
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def valid_check(value, *, symbol, now):
    try:
        at = datetime.fromisoformat(value['checked_at'])
        return (value['schema_version'] == 'chart-news-check-v1'
                and value['query_symbol'] == symbol and value['status'] == 'checked_bounded_source'
                and value['scope'] == SCOPE and at.tzinfo is not None
                and 0 <= (now-at).total_seconds() <= 900
                and type(value['validated_item_count']) is int and 0 <= value['validated_item_count'] <= 10
                and value['coverage_complete'] is False and value['fresh_catalyst_required'] is False)
    except (ValueError, TypeError, KeyError):
        return False
