"""Read-only authenticated catalogue smoke check; never authorizes a trade."""
from datetime import datetime, timezone
import json
from pathlib import Path
from .providers.catalogues import Trading212Catalogue


def check(catalogue=None):
    result = {'version': 'trading212-catalogue-check-v1',
              'observed_at': datetime.now(timezone.utc).isoformat(),
              'state': 'blocked', 'trade_authorized': False, 'model_calls': 0,
              'account_type_verified': False, 'candidates': []}
    try:
        catalogue = catalogue or Trading212Catalogue()
        rows = catalogue.fetch()
        candidates = [r for r in rows if 'nvidia' in r.name.casefold() or r.ticker.startswith('NVDA_')]
        exchanges = catalogue.client.get_json('https://live.trading212.com/api/v0/equity/metadata/exchanges')
        if not isinstance(exchanges, list):
            raise ValueError('invalid_exchanges')
        for row in candidates:
            matching = [e for e in exchanges if any(s.get('id') == row.workingScheduleId
                        for s in e.get('workingSchedules', []))]
            result['candidates'].append({**row.model_dump(), 'exchanges': [
                {'id':e['id'], 'name':e['name']} for e in matching]})
        result.update(state='catalogue_received', instrument_count=len(rows),
                      reason='Catalogue availability is not account-specific order permission; confirm exact identity and account type.')
    except Exception:
        # Never persist provider response bodies, auth headers, or exception strings.
        result.update(state='blocked', candidates=[], reason='Catalogue check failed; check credentials, metadata permissions and provider availability.')
    return result


def main():
    result = check()
    path = Path('artifacts/broker-check/result.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'state':result['state'], 'candidates':len(result['candidates']), 'trade_authorized':False}))
    return int(result['state'] != 'catalogue_received')


if __name__ == '__main__':
    raise SystemExit(main())
