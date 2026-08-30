# Order journal — 2026-08-31

The dashboard's **Order journal / Журнал заказов** reads the current version of each order's
profit calculation. It does not recalculate profits, change TikTok data, or run ingestion.

## API

- `GET /api/orders?shop_id=1&from=2026-08-01&to=2026-08-31&search=&state=all&loss_only=false&offset=0&limit=25`
- `GET /api/orders/{internal_order_id}?shop_id=1`

Dates are inclusive business dates in the shop timezone. Results sort by order creation time
descending, then internal ID descending. Search is a literal, case-insensitive substring in the
external order ID or product title. States: `all`, `final`, `preliminary`, `not_calculated`.
The maximum page size is 100. Summary totals cover all filtered rows, not only the page.
Orders without a profit row are included in the journal and counted separately, with null amounts.
Different currencies are never combined in a monetary summary. Detail queries are also shop-scoped.
Response fields are explicitly whitelisted: no buyer information or raw API payloads.

## Money and percentages

All API money is Decimal, serialized as exponent-free strings. The frontend displays the complete
stored decimal string without `k/m` abbreviations or floating-point money conversion.

The percentage denominator is **sale proceeds minus seller discounts**, before refunds and fees.
If that denominator is zero or negative, percentages are unavailable. These percentages describe
the order's revenue composition; they are not the contractual TikTok fee rates, which may use
different bases. Refunds, subsidies and signed adjustments remain separate in the detail.

The detailed waterfall is:

1. Sale minus seller discount = percentage base.
2. Minus refunds, platform fees, affiliate commission, seller-funded logistics and taxes;
   plus subsidies and signed adjustments = net seller revenue.
3. Minus purchase costs, packaging, inbound logistics and other entered variable costs = contribution.
4. Minus allocated advertising = estimated net profit.

Expanding a line shows the source transactions already included in that line. Do not deduct these
again. `fee_residual` is a combined dynamic commission / order-processing amount; the system does
not invent a separate split. Unrecognized transactions retain their original signed amount and
appear in a warning block without being added again to expenses.

## Evidence and reconciliation

“TikTok: final” requires a `settled` source snapshot and a recognized final profit status.
Preliminary records and fee-ratio estimates remain preliminary, including fully refunded orders
without a final source. Missing fee ratios and missing SKU costs are not presented as confirmed zero.
The UI shows the zero assumed by the existing engine explicitly. Shop-default costs are estimates.
Cost-version dates and the calculation version/timestamp are visible.

Advertising is allocated shop-wide by the existing BLENDED model (LOW confidence, trailing seven
days). Final TikTok data therefore does not make order profit exact. Unentered business costs are
not included; this is not comprehensive accounting profit.

Arithmetic checks validate the three identities above with exact Decimal equality. The separate
TikTok check compares net seller revenue with the sum of final statement records whose IDs occur
in the calculation snapshot. Missing records, currencies or final statuses prevent a match claim.
Newer/unrelated statement IDs are excluded. Matching totals do not verify each component or a bank
payout. Historical component-mismatch warnings remain visible even if the totals match.

## Unit economics correction

The previous per-unit table used Shop Analytics GMV for revenue and order-profit rows for the other
lines. These sources can disagree. Revenue now uses net seller revenue plus the same order fees;
it is explicitly labelled after refunds and adjustments, before fees. This changes the displayed
revenue basis, not the stored profit. Per-unit rounding is shown at each subtotal only when the
unrounded identities match; source mismatches produce a warning instead.

## Verification

- Pure tests: money signs, common percentage base, nonpositive revenue, missing data, final-source
  requirements, multiple statements, mismatches, unknown transactions and field whitelisting.
- Disposable PostgreSQL tests: date boundaries, current-version selection, shop isolation, search
  escaping, filters, totals versus pagination, mixed currency and HTTP validation.
- Frontend tests: exact decimal formatting, translations and deterministic demo filter behavior.
- Browser checks: desktop and 390 px phone widths, expandable fees, filters, modal open/close.

Acceptance run: 365 Python tests passed, including five PostgreSQL integration tests; Ruff clean.
Ten frontend tests, TypeScript, ESLint and the production build passed. Independent review found
one issue (hidden unrecognized operations); it was corrected and the confirming review was clean.
Read-only verification against the August production data found 86 orders: 80 calculated and six
without calculations. All 80 arithmetic checks matched, all 27 final statement totals matched,
53 orders remained preliminary, and the summed profit matched the existing dashboard. One order
uses default SKU costs. These counts describe the verification snapshot, not a permanent guarantee.

Run PostgreSQL tests only with `ORDER_LEDGER_TEST_DATABASE_URL` pointing to a disposable database
named `order_journal_test`. They create schema there and roll back their test data. Never use production.
Demo fixture endpoints exist only when `MOCK=1`; they visibly label every demo result.

## Existing deployment risk

The application currently has no authentication. Shop scoping is not authorization. Before sharing
the dashboard with others, protect both the dashboard and all API entry points; protecting only
Caddy leaves direct published service ports as a bypass. This feature does not change access policy.
