"""Preserve paid responses before accounting; recover costs without model calls."""
import json
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
from pathlib import Path

from .github_budget import Usage
from .openai_pilot import MODEL, usage_cost


def save_receipt(directory, *, request_id, now, actual_microeur, usage, response):
    root=Path(directory); root.mkdir(parents=True,exist_ok=True)
    payload={'schema_version':'paid-response-receipt-v1','request_id':request_id,
             'request_at':now.isoformat(),'actual_microeur':actual_microeur,
             'usage':Usage.model_validate(usage).model_dump(), 'response':response}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    if len(raw)>2_000_000:raise ValueError('paid_receipt_capacity')
    path=root/(sha256(request_id.encode()).hexdigest()+'.json')
    # One request identity, one immutable response. It is an artifact, not a new
    # review, and must never be promoted to an approval after the deadline.
    with path.open('xb') as f:f.write(raw)
    path.chmod(0o600)


def reconcile_receipts(directory, ledger):
    result={'schema_version':'settlement-recovery-v1','model_calls':0,
            'trade_authorized':False,'reconciled':0,'unresolved':0}
    for path in sorted(Path(directory).glob('*.json')):
        try:
            if path.stat().st_size>2_000_000:raise ValueError('receipt_capacity')
            r=json.loads(path.read_text());u=Usage.model_validate(r['usage']).model_dump()
            response=r['response'];cost=usage_cost(response['usage']);rate=Decimal(u['eur_per_usd'])
            expected=int((cost*rate*1_000_000).to_integral_value(rounding=ROUND_CEILING))
            if (r['schema_version']!='paid-response-receipt-v1' or response['model']!=MODEL
                    or u['model']!=MODEL or u['response_id']!=response['id']
                    or not rate.is_finite() or rate<=0 or Decimal(u['cost_usd'])!=cost
                    or type(r['actual_microeur']) is not int or r['actual_microeur']!=expected
                    or u['input_tokens']!=response['usage']['input_tokens']
                    or u['output_tokens']!=response['usage']['output_tokens']
                    or u['cached_input_tokens']!=response['usage'].get('input_tokens_details',{}).get('cached_tokens',0)
                    or path.stem!=sha256(r['request_id'].encode()).hexdigest()):
                raise ValueError('receipt_identity_or_cost')
            ledger.settle(r['request_id'],expected,usage=u)
            result['reconciled']+=1
        except (RuntimeError, ValueError, KeyError, TypeError, OSError, ArithmeticError):
            result['unresolved']+=1
    return result
