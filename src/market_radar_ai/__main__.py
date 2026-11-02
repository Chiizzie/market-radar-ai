from market_radar_ai.config import settings

def main() -> None:
    print("Market Radar AI foundation is ready.")
    print(f"Environment: {settings.app_env}")
    print(f"Timezone: {settings.app_timezone}")
    print(f"Reporting currency: {settings.reporting_currency}")
    print("Execution mode: PAPER ONLY")

if __name__ == "__main__":
    main()
