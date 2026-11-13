"""Rotate existing settled records and verify every receipt; no model calls."""
from datetime import datetime, timezone
from hashlib import sha256
import time

from .budget_archive import encode
from .github_budget import GitHubBudgetStore
from ..dashboard.api_budget import summarize


def run(*, token, migrate=False, clock=lambda: datetime.now(timezone.utc),
        factory=GitHubBudgetStore, sleep=time.sleep):
    store = factory(token, archive_writes=True)
    before, version = store.load()
    before_storage = store.storage_summary()
    _, chunks, _ = store._archives.plan(before, enabled=True)
    now = clock()
    baseline = summarize(before, now=now)
    if migrate and chunks:
        store.save(before, version)
    # A new reader must recover the complete ledger, including immutable files.
    # The writer's in-memory acknowledgement cache is not migration evidence.
    for attempt in range(3):
        reader = factory(token, archive_writes=False)
        after, _ = reader.load()
        if after == before and (not migrate or not chunks or reader.storage_summary()['archive_files']):
            break
        if attempt < 2:
            sleep(attempt + 1)
    else:
        raise RuntimeError('Budget maintenance verification changed or stale; inspect before retry')
    if summarize(after, now=now) != baseline:
        raise RuntimeError('Budget maintenance accounting mismatch')
    return {'schema_version': 'budget-storage-maintenance-v1', 'as_of': now.isoformat(),
            'mode': 'migrate' if migrate else 'read_only',
            'state': 'verified', 'rotated': bool(migrate and chunks),
            'planned_archive_files': len(chunks), 'before': before_storage,
            'after': reader.storage_summary(),
            'logical_before_sha256': sha256(encode(before)).hexdigest(),
            'logical_after_sha256': sha256(encode(after)).hexdigest(),
            'accounting': baseline, 'model_calls': 0, 'trade_authorized': False,
            'note': 'All identities, limits, receipts and unresolved holds preserved. '
                    'One CAS manifest update changes storage only. No request or model call is repeated.'}


def main():
    import argparse
    import json
    import os
    from pathlib import Path
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--migrate', action='store_true')
    p.add_argument('--output', type=Path, default=Path('artifacts/budget-storage/maintenance.json'))
    a = p.parse_args()
    if any(os.environ.get(k) for k in ('OPENAI_API_KEY', 'OPEN_API_KEY', 'ALPACA_API_KEY',
                                      'TRADING212_API_KEY', 'TELEGRAM_BOT_TOKEN')):
        raise ValueError('unneeded_credentials_forbidden')
    result = run(token=os.environ.get('GH_BUDGET_TOKEN'), migrate=a.migrate)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
