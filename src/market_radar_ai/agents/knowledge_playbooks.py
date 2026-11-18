"""Versioned explanations of existing stock rules, not new trading signals."""
from .candidate_packages import digest

VERSION = 'stock-playbooks-v1'
SOURCE_REVISION = '208f4bf5f9f1f403fb977075f0ea33912f4463b0'
COMMON = {
    'scope': 'Conditional intraday stock paper research; no orders or probability of profit.',
    'requirements': ['Current reference quote, FX, catalogue candidate and open market checks pass.',
        'Cost-inclusive planned loss <= EUR20 and net target reward >= twice that loss.',
        'No entry at or after 22:00 Europe/Dublin; exit before the saved same-day deadline.',
        'Trigger is not filled until a later eligible observed ask crosses it; current bid must exceed stop.'],
    'limitations': ['Rolling 20-bar VWAP is not full-session VWAP; opening mode uses its opening window.',
        'Recent-bar volume ratio is not time-of-day relative volume. IEX is a partial venue feed.',
        'Unknown quotes, costs or outcomes stay unknown. A successful script is not a profitable strategy.',
        'Historical examples cannot supply current news, quotes, broker permission or missing evidence.'],
    'failure_modes': ['Stale or wide quotes can prevent a trustworthy fill or exit.',
        'Costs, a trigger gap or nearby resistance can remove the required reward/risk.',
        'An unresolved exit is not a win, loss or zero-return trade.'],
}
RULES = {
    'trend_pullback_reclaim_v1': {
        'setup': 'Confirmed impulse, pullback and reclaim pattern from contiguous completed bars.',
        'requirements': ['Pattern state CONFIRMED; positive momentum; close above rolling VWAP.',
            'Last five-bar average volume / prior fifteen-bar average >= 1.',
            'Completed bounded symbol news risk check; a fresh positive catalyst is optional.'],
        'invalidation': 'Observed support/stop failure, invalidated pattern, stale evidence or expired plan.',
        'sources': ['market_data/pullback.py', 'agents/setup_checks.py', 'agents/chart_news.py', 'agents/paper_verdict.py'],
    },
    'trend_continuation_20bar_v1': {
        'setup': 'Chart-led continuation using twenty completed bars and the saved breakout trigger.',
        'requirements': ['Positive twenty-bar momentum; close above rolling VWAP.',
            'Last five-bar average volume / prior fifteen-bar average >= 1.',
            'Completed bounded symbol news risk check; a fresh positive catalyst is optional.'],
        'invalidation': 'Observed stop failure, loss of required current evidence, trigger gap or expiry.',
        'sources': ['agents/setup_checks.py', 'agents/chart_news.py', 'agents/paper_verdict.py'],
    },
    'opening_continuation_30m_v1': {
        'setup': 'Experimental opening continuation after at least six contiguous completed opening bars.',
        'requirements': ['Positive opening-window momentum; close above the opening-window VWAP.',
            'Last three-bar average volume / earlier opening-bar average >= 1.5.',
            'Current cited news evidence is required by this existing strategy.'],
        'invalidation': 'Observed stop failure, missing catalyst evidence, invalid session window or expiry.',
        'sources': ['market_data/strategy_window.py', 'agents/setup_checks.py', 'agents/paper_verdict.py'],
    },
}


def playbook(strategy):
    if strategy not in RULES:
        return None
    rules = RULES[strategy]
    body = {**COMMON, **rules, 'requirements': COMMON['requirements'] + rules['requirements'],
            'strategy_id': strategy, 'version': VERSION, 'source_revision': SOURCE_REVISION}
    return {'source_id': 'playbook:' + digest(body), **body}


CATALOGUE_ID = digest([playbook(s) for s in sorted(RULES)])
