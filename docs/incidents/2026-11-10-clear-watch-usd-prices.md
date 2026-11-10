# Clear breakout watches and USD stock prices

Watch alerts previously put an EUR entry price before the conditional-breakout
instruction. A watch could be mistaken for an instruction to enter immediately.

The alert now leads with WAIT FOR BREAKOUT, identifies the reference-ask trigger,
shows the original expiry in Europe/Dublin, and says to skip if no eligible
trigger occurs. It distinguishes the watch from a recorded simulated entry and
from manual broker purchases. Expired/rejected decisions still show no entry.

Stock plan prices, assumed costs and fictional allocation are displayed in USD
using the original plan's EUR-per-USD conversion. Native EUR plans stay EUR.
Lifecycle messages can show clearly labelled approximate USD equivalents using
that plan FX, alongside the original EUR observation; observation-time FX can
differ and is not reconstructed. Historical records are not rewritten.

The dashboard defaults stock candles to native USD and converts EUR paper-plan
overlays into the same units. An explicit chart EUR toggle converts both candles
and overlays together. The plan panel makes the waiting/expired state explicit.

No strategy, spread, entry-gap, expiry, paper-fill, risk, budget or live-order
rules changed. Risk and performance accounting remain EUR; the €20 limit stays.

Validation: 69 focused backend tests and 45 dashboard tests passed, including
exact trigger display, native-EUR preservation, no archive mutation, expiry,
notification delivery, watcher lifecycle and matching chart/overlay currency.
Dashboard production build and scoped lint checks passed. No paid AI replay or
Telegram test message was sent.
