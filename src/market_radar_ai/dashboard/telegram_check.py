"""One explicit manual Telegram connection test. Never sends trade calls."""
import os
import requests

TEXT = 'Market Radar AI — connection test. Research and paper trading only. This is NOT a trade call. Automatic notifications are not enabled.'


def execute(env, *, session=None):
    if (env.get('GITHUB_REPOSITORY')!='Chiizzie/market-radar-ai'
        or env.get('GITHUB_REF')!='refs/heads/phase-1/market-data-layer'
        or env.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
        or env.get('GITHUB_RUN_ATTEMPT')!='1'
        or env.get('SEND_TELEGRAM_TEST')!='true'):
        raise ValueError('manual_first_attempt_required')
    token=env.get('TELEGRAM_BOT_TOKEN','');chat=env.get('TELEGRAM_CHAT_ID','')
    if not token or not chat.lstrip('-').isdigit():
        raise ValueError('telegram_secrets_missing_or_invalid')
    try:
        response=(session or requests).post('https://api.telegram.org/bot'+token+'/sendMessage',
            json={'chat_id':chat,'text':TEXT,'protect_content':True},
            timeout=(10,20),allow_redirects=False)
        if response.status_code!=200:raise ValueError('telegram_error')
        body=response.json()
        if (body.get('ok') is not True or str(body['result']['chat']['id'])!=chat
                or type(body['result']['message_id']) is not int):
            raise ValueError('unconfirmed_destination')
    except Exception:
        raise RuntimeError('Telegram test unconfirmed; inspect destination before any new attempt. No automatic retry.') from None
    return {'state':'test_delivery_confirmed','automatic_notifications_enabled':False}


if __name__=='__main__':
    try:print(execute(os.environ))
    except Exception:raise SystemExit('Telegram test blocked or unconfirmed; no automatic retry.') from None
