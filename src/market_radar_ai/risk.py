from dataclasses import dataclass
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
    if not paper_only:
        failures.append("paper_trading_only must be true")
    if planned_loss_eur < 0 or planned_loss_eur > 20:
        failures.append("planned loss exceeds EUR 20 ceiling or is invalid")
    if not data_quality_passed:
        failures.append("data quality gate failed")
    if intraday and now.astimezone(DUBLIN).hour >= 22:
        failures.append("intraday entry/holding cutoff reached")
    return RiskCheck(not failures, tuple(failures))
