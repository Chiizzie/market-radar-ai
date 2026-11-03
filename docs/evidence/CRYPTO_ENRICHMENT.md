# Crypto evidence enrichment — 2026-11-03

Robinhood Europe remains the intended crypto broker. No broker account, order
permission or execution route was changed.

## Connected evidence

- The scanner fetches the official CoinDesk RSS feed with bounded time/size limits
  and at most one retry, only after a transport failure. Exact publisher categories
  map to COINDESK:BTC, COINDESK:ETH, COINDESK:SOL or COINDESK:XRP.
  Headline mentions, Ripple company references and Bitcoin Cash do not establish
  a link to those assets. Untagged articles remain unassociated.
- Two public Kraken GET requests fetch AssetPairs metadata and Ticker bid/ask for
  the captured EUR pairs (currently XBTEUR, ETHEUR, SOLEUR, XRPEUR). Pair identity,
  online status, positive decimal prices/sizes and uncrossed quotes are required.
- The enriched capture preserves the original candles and includes the raw
  reference response plus its SHA-256. Valid references enter the hashed market
  source in candidate evidence packages. Publisher-tagged news enters separately
  hashed news sources. All six generic roles receive these sources.
- Reference freshness expires 30 seconds after local receipt. Kraken's Ticker
  response does not supply an exchange observation timestamp. The package cannot
  outlive the quote. A review that finishes later remains stale research.
- The workflow retains both capture.json and enriched-capture.json. Reproduction
  of a package containing a reference quote requires enriched-capture.json.

These are public venue research references, **not Robinhood executable quotes**.
They do not establish account eligibility, personal fees, expected slippage or an
executable EUR trade plan. Those blockers remain. Single-publisher crypto news is
always partial and cannot clear independent catalyst confirmation. Older stories
remain context only. No inference that missing news means no relevant event.

## Verification

Live local checks retrieved EUR bid/ask for all four pairs. The CoinDesk final
check retrieved 25 articles, five carrying supported explicit tags; the first
transport attempt failed and the second succeeded. Tagged stories were older
than the intraday recency window. Provider coverage and availability can change.

Unit coverage includes malformed/crossed/nonfinite quotes, incorrect identities,
offline pairs, naive/future/stale timestamps, source checksum changes, foreign
publisher URLs, XML entities, ambiguous tags, retry limits, deterministic package
reproduction, and legacy records without enrichment.

tests/fixtures/candidate-review-enriched-v1.json is SYNTHETIC TEST DATA produced
with stub responses and fixed timestamps. Its PAID_AI wire field exercises the
existing archive contract; it does not document real spending or model calls.
Never ingest it into production or count it as a trade/review outcome.

## Broker/API considerations

Official documentation checked 2026-11-03:

- Robinhood's documented Crypto Trading API is for US customers. It cannot be
  assumed available to a Robinhood Europe account:
  https://docs.robinhood.com/crypto/trading/
- Bybit EU has API documentation, but its integration guide restricts the EU site
  API to the Connect to Third-Party Applications feature for API broker users.
  A custom personal integration must be verified before choosing it:
  https://bybit-exchange.github.io/docs/v5/guide
  https://www.bybit.eu/en-EU/help-center/article/How-to-retrieve-API-documentations?category=ae1012f19fad1c184e
- Binance's June 2026 notice says it withdrew its Greek MiCA application and
  pursued another member state. That notice is not proof of present account-
  specific Ireland permissions. Confirm current Irish availability, EUR products,
  API access and fees before any migration:
  https://www.binance.com/en/blog/regulation/4457979419755346760

No switch to Binance, Bybit or Kraken is needed to use the public evidence
collectors. No new secret is required for these collectors.

Provider references:
https://docs.kraken.com/api-reference/market-data/get-ticker-information
https://docs.kraken.com/api-reference/market-data/get-tradable-asset-pairs
https://www.coindesk.com/coindesk-news/2021/09/17/coindesk-rss

