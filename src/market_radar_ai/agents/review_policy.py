"""Versioned team verdict rules shared by finalization and durable recording.

This only checks the team's verdicts. Identity, citations, timestamps, fresh
evidence and deterministic plan/risk checks remain mandatory at their callers.
"""

CONDITIONAL_CHIEF_POLICY = 'paper-specialists-v3-conditional-chief'


def team_approval_allowed(verdicts, *, policy_version):
    verdicts = tuple(verdicts)
    if (not verdicts or verdicts[-1] != 'APPROVE_PAPER'
            or any(v not in ('APPROVE_PAPER', 'MORE_EVIDENCE_REQUIRED') for v in verdicts)):
        return False
    # The explicit v3 policy allows the chief to resolve uncertainty, but never
    # an explicit rejection. Unversioned/other historical packets stay unanimous.
    return (policy_version == CONDITIONAL_CHIEF_POLICY
            or all(v == 'APPROVE_PAPER' for v in verdicts))
