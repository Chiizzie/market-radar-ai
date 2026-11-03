"""Clock and execution scope for the capture-only scheduled collector."""
from datetime import datetime
from zoneinfo import ZoneInfo

REPOSITORY = 'Chiizzie/market-radar-ai'
WORKFLOW_REF = REPOSITORY + '/.github/workflows/scheduled-scanner.yml@refs/heads/main'


def collection_window(now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    local = now.astimezone(ZoneInfo('Europe/Dublin'))
    return 8 <= local.hour < 23


def scheduled_scope(env, now):
    """Manual out-of-hours verification is explicit; cron never bypasses the clock."""
    valid = (env.get('GITHUB_REPOSITORY') == REPOSITORY
             and env.get('GITHUB_REF') == 'refs/heads/main'
             and env.get('GITHUB_WORKFLOW_REF') == WORKFLOW_REF
             and env.get('GITHUB_EVENT_NAME') in ('schedule', 'workflow_dispatch')
             and env.get('GITHUB_RUN_ATTEMPT') == '1'
             and env.get('SCANNER_COLLECTION_MODE') == 'scheduled')
    if not valid:
        return False
    verification = (env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
                    and env.get('SCANNER_VERIFY_OUTSIDE_WINDOW') == 'true')
    return collection_window(now) or verification
