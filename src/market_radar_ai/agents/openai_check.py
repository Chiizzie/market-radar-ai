"""Explicit one-call connectivity check using a persistent local budget database."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import json
import os
from pathlib import Path
from .openai_pilot import OpenAIPilot
from .spending import SpendingLedger


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-paid', action='store_true')
    parser.add_argument('--eur-per-usd', required=True)
    parser.add_argument('--budget-db', required=True)
    args=parser.parse_args()
    if not args.enable_paid:
        parser.error('Paid calls are disabled; explicit --enable-paid is required')
    path=Path(args.budget_db).expanduser().resolve()
    ledger=SpendingLedger(path, 500000, monthly_limit_microeur=10000000,
                         lifetime_limit_microeur=500000)
    key=os.environ.get('OPENAI_API_KEY') or getpass('OpenAI API key (hidden): ')
    pilot=OpenAIPilot(api_key=key, ledger=ledger, eur_per_usd=args.eur_per_usd, enabled=True)
    try:
        reply=pilot.call(prompt='Connectivity test only. Return {"ok":true}.',
            schema={'type':'object','properties':{'ok':{'type':'boolean','const':True}}},
            request_id='connectivity-v1', now=datetime.now(timezone.utc), max_output_tokens=64)
        print(json.dumps({'status':'connected','response_id':reply.response_id,
            'cost_usd':str(reply.cost_usd), 'estimated_cost_microeur':reply.estimated_cost_microeur,
            'eur_per_usd':str(reply.eur_per_usd)}))
    except Exception:
        raise SystemExit('Check failed; inspect the budget ledger before any retry. No automatic retry was made.') from None


if __name__ == '__main__':
    main()
