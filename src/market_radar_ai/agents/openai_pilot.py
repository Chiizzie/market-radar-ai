"""Opt-in, text-only pilot client; deliberately separate from the offline team.

Prices checked against the official model page on 2026-11-02. Costs exclude tax.
Never use an ephemeral ledger for repeated paid runs.
"""
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import json
import requests
import sqlite3
from jsonschema import Draft202012Validator

MODEL = 'gpt-5.4-mini-2026-03-17'
ENDPOINT = 'https://api.openai.com/v1/responses'
INPUT_USD_PER_MILLION = Decimal('0.75')
CACHED_USD_PER_MILLION = Decimal('0.075')
OUTPUT_USD_PER_MILLION = Decimal('4.50')


def strict_schema(schema):
    result = deepcopy(schema)
    def visit(node):
        if isinstance(node, dict):
            node.pop('default', None)
            if node.get('type') == 'object':
                node['additionalProperties'] = False
                node['required'] = list(node.get('properties', {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(result)
    return result


def usage_cost(usage):
    """All output tokens, including reasoning, are charged once."""
    incoming, outgoing = usage['input_tokens'], usage['output_tokens']
    cached = usage.get('input_tokens_details', {}).get('cached_tokens', 0)
    if any(type(n) is not int or n < 0 for n in (incoming, outgoing, cached)) or cached > incoming:
        raise ValueError('Invalid token usage')
    return ((incoming-cached)*INPUT_USD_PER_MILLION + cached*CACHED_USD_PER_MILLION
            + outgoing*OUTPUT_USD_PER_MILLION) / Decimal(1_000_000)


@dataclass(frozen=True)
class PilotReply:
    data: dict
    response_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    estimated_cost_microeur: int
    eur_per_usd: Decimal


class OpenAIPilot:
    def __init__(self, *, api_key, ledger, eur_per_usd, enabled=False):
        if enabled is not True:
            raise ValueError('Paid pilot is disabled')
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('OPENAI_API_KEY is missing')
        rate = Decimal(str(eur_per_usd))
        if not rate.is_finite() or rate <= 0:
            raise ValueError('Explicit positive EUR per USD rate required')
        if ledger.monthly_limit is None or ledger.lifetime_limit is None:
            raise ValueError('Monthly and lifetime pilot limits are required')
        self._key, self.ledger, self.rate = api_key, ledger, rate

    def _eur(self, usd):
        return int((usd*self.rate*1_000_000).to_integral_value(rounding=ROUND_CEILING))

    def call(self, *, prompt, schema, request_id, now, max_output_tokens=512):
        if not isinstance(prompt, str) or not 0 < len(prompt.encode('utf-8')) <= 16000:
            raise ValueError('Pilot prompt must be 1 to 16000 UTF-8 bytes')
        if type(max_output_tokens) is not int or not 16 <= max_output_tokens <= 2048:
            raise ValueError('Pilot output cap must be 16 to 2048 tokens')
        validated_schema = strict_schema(schema)
        Draft202012Validator.check_schema(validated_schema)
        payload = dict(model=MODEL, input=prompt, store=False, service_tier='default',
            max_output_tokens=max_output_tokens, reasoning={'effort':'none'},
            text={'format':{'type':'json_schema', 'name':'pilot_result',
                           'strict':True, 'schema':validated_schema}})
        if len(json.dumps(payload).encode('utf-8')) > 64000:
            raise ValueError('Pilot request too large')
        # Reserve the full context window at uncached price, plus output cap.
        # This deliberately avoids claiming a byte-count token estimate is exact.
        bound = (400000*INPUT_USD_PER_MILLION + max_output_tokens*OUTPUT_USD_PER_MILLION)/1_000_000
        self.ledger.reserve(request_id, self._eur(bound), now)
        try:
            response = requests.post(ENDPOINT, json=payload,
                headers={'Authorization':'Bearer '+self._key}, timeout=(10, 45),
                allow_redirects=False)
            if response.status_code != 200:
                raise RuntimeError('provider_error')
            body = response.json()
        except Exception:
            # Never expose provider bodies, request headers, or exception strings.
            raise RuntimeError('OpenAI request failed; reservation retained; do not retry automatically') from None
        try:
            usd = usage_cost(body['usage'])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise RuntimeError('Unknown usage; reservation retained') from None
        estimated = self._eur(usd)
        with sqlite3.connect(self.ledger.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS openai_usage (request_id TEXT PRIMARY KEY, response_id TEXT, model TEXT, usage_json TEXT, cost_usd TEXT, eur_per_usd TEXT, estimated_microeur INTEGER)')
            db.execute('INSERT INTO openai_usage VALUES (?,?,?,?,?,?,?)',
                (request_id, body.get('id'), body.get('model'), json.dumps(body['usage']),
                 str(usd), str(self.rate), estimated))
        self.ledger.settle(request_id, estimated)
        if body.get('status') != 'completed' or body.get('model') != MODEL:
            raise RuntimeError('Incomplete or unexpected model response; usage settled')
        texts = [part['text'] for item in body.get('output', []) if item.get('type') == 'message'
                 for part in item.get('content', []) if part.get('type') == 'output_text']
        if len(texts) != 1 or len(texts[0]) > 100000:
            raise ValueError('Missing, refused, or oversized structured response')
        data = json.loads(texts[0])
        if not isinstance(data, dict):
            raise ValueError('Expected an object response')
        Draft202012Validator(validated_schema).validate(data)
        return PilotReply(data, body['id'], body['usage']['input_tokens'],
            body['usage']['output_tokens'], usd, estimated, self.rate)
