from dataclasses import dataclass
from math import isfinite
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

DUBLIN = ZoneInfo("Europe/Dublin")

@dataclass(frozen=True)
class RiskCheck:
    passed: bool
    failures: tuple[str, ...]

def mandatory_risk_check(planned_loss_eur: float, paper_only: bool,
                          data_quality_passed: bool,
                          intraday: bool, now: datetime) -> RiskCheck:
    failures = []
    if paper_only is not True:
        failures.append("paper_trading_only must be true")
    if (type(planned_loss_eur) not in (int, float, Decimal)
            or not isfinite(planned_loss_eur) or not 0 <= planned_loss_eur <= 20):
        failures.append("planned loss exceeds EUR 20 ceiling or is invalid")
    if data_quality_passed is not True:
        failures.append("data quality gate failed")
    if intraday is not True:
        failures.append("intraday trades only")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        failures.append("now must be timezone-aware")
    elif now.astimezone(DUBLIN).hour >= 22:
        failures.append("intraday entry/holding cutoff reached")
    return RiskCheck(not failures, tuple(failures))
