# Market-context deployment mismatch — 10 November 2026

At 14:35 and 14:40 Europe/Dublin, scheduled runs 42835575407 and 42836435191 failed only in the independent market-context job. Collection, review, paper watcher, shadow research and account sync succeeded. The 14:40 collector screened 1,200 stock histories and delivered 79 current stock captures; review completed with no qualified candidate and zero model calls.

The context job was still pinned to 28b7c2b, whose collector rejected more than 40 symbols (`ValueError: invalid_batch_symbols`). The broader collector was pinned to 4b4fc934, allowing 80. This was a deployment integration regression from the capacity expansion, not a failure of the new conditional review policy. Market-context evidence is research-only and is not an input to trade admission.

The fix aligns the context job with the current runtime and fixes a second adapter limit: 80 stocks plus 12 benchmarks can now pass through the real historical-bars adapter. The response bound uses the actual requested symbol count times 78 five-minute bars. Malformed identities, excess symbols, excess bars and incomplete pagination still fail closed.

The dashboard and database accept up to 256,000 bytes for a validated context report only; other research events retain the 180,000-byte limit. Full-width reports could otherwise exceed the old cap. No historical rows, trading rules, budgets or live-order permissions are changed.

Validation: 18 focused backend tests passed, including full-width cold/warm caches through the real adapter with a mocked network boundary; 34 dashboard tests passed, including signed 80-stock report ingestion, oversized-context refusal and preservation of other event limits. Dashboard production build checked before publication. New workflow pin and live run must be checked after deployment.
