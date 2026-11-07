# Market, sector and same-time volume research

This independent research worker records observations without adding anything to current qualification rules, AI prompts or the comparison/AVWAP protocols. It does not rank discovery, authorize trades, send Telegram alerts, call models or use brokerage order endpoints.

## Measurements

- SPY is the large-cap market proxy; XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLK and XLU provide eleven sector comparisons. These are reference benchmarks, not trade candidates. Individual company-sector membership is not inferred. The dashboard lets a viewer select a benchmark explicitly.
- Each of up to 40 captured stocks gets a row, including missing-data rows. Capture identity is stored as a SHA256. The worker requests fresh benchmark/stock bars separately and reports its own time of availability; context must not be backdated into an earlier decision.
- Return is the percentage change from the first regular-session five-minute bar's open to the selected completed bar's close. The stock-minus-benchmark difference is in percentage points over exactly the same window. Overnight returns and dividend total returns are excluded.
- Cumulative IEX volume from the session open to that cutoff is divided by mean cumulative volume over the identical elapsed window on ten prior full sessions, with at least five complete samples required. Sample dates, volumes, observed bucket counts and source hashes are retained. A missing bar is unknown, never zero; incomplete windows are excluded. A zero baseline cannot yield a ratio.
- All bars use the same IEX feed and split adjustment. Alpaca documents that split adjustment applies to both price and volume. IEX is partial exchange coverage: these values are not consolidated US volume and venue participation may vary over time.
- Alpaca's US market calendar supplies session dates and early closes. New York local session clocks handle DST. Prior shortened sessions are excluded; a current shortened session uses its actual close and equivalent elapsed windows from full prior sessions. The most recent bar must have completed at least 30 seconds before the cutoff calculation.

## Reliability and scope

The worker is a separate job following collection, concurrent with the review path. It cannot delay approval by being part of the review's dependencies. It has its own concurrency group and eight-minute timeout. Historical compact series are cached for the current New York date and protocol, bounded to 400 symbols/6 MB, validated by hashes and shape, and refreshed on a new date. A normal warm run makes one current bar batch plus the calendar request. A cold run requests ten historical session batches and one current batch, with bounded pagination and response sizes.

Failures and missing samples remain explicit. Historical API revisions, feed entitlement and real symbol coverage must be assessed from natural runs. The dashboard flags an old measurement window as historical, even if it was fetched recently. Its last twelve context reports are selectable; the append-only database retains earlier reports.

`context_report` uses its own signed event partition and viewer-only RLS. The endpoint validates time, symbol/benchmark identity, completeness, arithmetic and no-trading/no-model flags. The original comparison, method and raw-event access policies are preserved. Normalized historical volume cache and report artifacts are retained for 30 days; primary source hashes identify the bar response.

The verification workflow publishes only the actual current session status. A separate provider rehearsal evaluates the last completed real session on ASH, AAPL, MSFT and the benchmarks, labels it `historical_rehearsal`, stores it as an artifact, and cannot publish it as prospective evidence. It is a provider/measurement check, not a strategy backtest or profitability test.

## Primary references checked 7 November 2026

- [Alpaca historical bars: feed, split-adjusted price/volume, symbol identity and pagination](https://docs.alpaca.markets/us/reference/stockbars)
- [Alpaca US calendar: trading dates and early closes](https://docs.alpaca.markets/us/reference/legacycalendar)
- [State Street sector ETF benchmark identities](https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs)

Next research steps: verify company-sector classifications, evaluate these observations prospectively against outcomes, then preregister a separate strategy version if evidence warrants using them in decisions. No improvement in performance is assumed from adding context.
