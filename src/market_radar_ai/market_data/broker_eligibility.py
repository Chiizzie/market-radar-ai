"""Separate catalogue identity evidence from account-specific permission."""
from datetime import datetime


def assess_nvda(catalogue, *, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    identity = False
    reason = 'catalogue_unavailable_invalid_or_stale'
    try:
        observed = datetime.fromisoformat(catalogue['observed_at'])
        if (observed.tzinfo is None or catalogue['state'] != 'catalogue_received'
                or not 0 <= (now-observed).total_seconds() <= 600):
            raise ValueError('stale')
        matches = [r for r in catalogue['candidates'] if r['ticker'] == 'NVDA_US_EQ']
        identity = (len(matches) == 1 and matches[0]['isin'] == 'US67066G1040'
            and matches[0]['type'] == 'STOCK' and matches[0]['currencyCode'] == 'USD'
            and any(e['name'] == 'NASDAQ' for e in matches[0]['exchanges']))
        reason = 'exact_catalogue_identity_matched' if identity else 'catalogue_identity_mismatch_or_ambiguous'
    except (KeyError, TypeError, ValueError):
        pass
    return dict(version='broker-eligibility-v1', broker='trading212_invest', symbol='NVDA',
        instrument_id='NVDA_US_EQ', evaluated_at=now.isoformat(),
        catalogue_identity_verified=identity, catalogue_reason=reason,
        account_type_status='unknown', account_permission_status='unknown',
        trade_authorized=False, eligibility_verified=False,
        missing_evidence=['invest_account_confirmation','current_instrument_buy_permission'],
        next_check='Confirm the API key belongs to Invest and NVDA is currently buy-enabled in that account. Do not submit an order to test this.',
        evidence_note='Catalogue access supports identity only; it is not account-specific permission. No balance, account identifier or positions are needed.')
