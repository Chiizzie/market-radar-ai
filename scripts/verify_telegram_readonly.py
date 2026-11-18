"""Check current bot/chat access without sending or reading messages."""
import json
import os
from pathlib import Path
import time

import requests
from market_radar_ai.dashboard.paper_final_delivery import response_details, transport_reason


def probe(env, session=requests):
    token, chat = env.get('TELEGRAM_BOT_TOKEN', ''), env.get('TELEGRAM_CHAT_ID', '')
    report = {'schema_version': 'telegram-readonly-check-v1', 'model_calls': 0,
              'notifications_sent': 0, 'trade_authorized': False, 'checks': []}
    if not token or not chat.lstrip('-').isdigit():
        report['checks'].append({'method': 'configuration', 'state': 'credentials_missing'})
        return report
    for method in ('getMe', 'getChat'):
        start = time.monotonic()
        row = {'method': method}
        try:
            reply = session.get('https://api.telegram.org/bot'+token+'/'+method,
                params={'chat_id': chat} if method == 'getChat' else {},
                timeout=(10, 20), allow_redirects=False)
        except Exception as exc:
            row['state'] = transport_reason(exc)
        else:
            try: value = reply.json()
            except Exception: value = None
            row.update(response_details(reply, value))
            result = value.get('result') if isinstance(value, dict) else None
            valid = (reply.status_code == 200 and isinstance(value, dict)
                     and value.get('ok') is True and isinstance(result, dict))
            if valid:
                valid = result.get('is_bot') is True if method == 'getMe' else str(result.get('id')) == chat
            row['state'] = 'confirmed' if valid else 'not_confirmed'
        row['elapsed_seconds'] = round(time.monotonic()-start, 3)
        report['checks'].append(row)
    return report


if __name__ == '__main__':
    report = probe(os.environ)
    path = Path('artifacts/telegram-readonly.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    raise SystemExit(0 if all(x['state']=='confirmed' for x in report['checks']) else 1)
