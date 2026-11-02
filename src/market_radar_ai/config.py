from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    app_timezone: str = "Europe/Dublin"
    reporting_currency: str = "EUR"
    max_planned_risk_eur: float = 20.0
    paper_trading_only: bool = True

settings = Settings()

if not settings.paper_trading_only:
    raise RuntimeError("Live execution is deliberately unsupported in this project.")
if settings.max_planned_risk_eur <= 0:
    raise ValueError("MAX_PLANNED_RISK_EUR must be positive.")
