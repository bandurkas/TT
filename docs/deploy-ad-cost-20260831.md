# Advertising accounting release — 2026-08-31

Core commit: `7421f49`. Migration: `d83f921a6b40`. API, worker and dashboard rebuilt and restarted together on VPS3. Original workbooks preserved; source hashes match before/after transfer. DB backup and previous images retained privately on VPS; other projects untouched.

Validation completed:

- 379 Python tests passed on Linux, including PostgreSQL import/overlap/rollback/currency/rebuild tests. Ruff clean.
- 10 frontend tests passed; TypeScript, ESLint and production build passed.
- Independent review: original P1/P2 findings fixed and confirmed closed.
- Production DB copied into an isolated test container; migration, both reports and two recalculations checked there before the live import. Second calculation: inserted=0, unchanged=81, mismatches=0.
- Live API, order ledger and waterfall totals agree. Health returns status=ok, db=ok; updated worker scheduler started; no startup errors in service logs.

| Period | Reported Cost, IDR | GMV Pay by statement date, IDR | Estimated calendar profit, IDR |
|---|---:|---:|---:|
| Aug 2–31 | 4,347,403 | 2,430,167 | -4,800 |
| Aug 1–30 | 4,273,414 | 2,495,139 | 94,123 |
| Aug 1–31 | 4,347,403 | 2,495,139 | 59,460 |

Aug 31 remains partial. September without a report returns unavailable Cost/profit, not zero. IDR 377,309 on Aug 7, 8, 12, 13 had no eligible same-day orders and remains in the calendar total. Three cancelled order details show source refund evidence with no invented profit.

Remaining evidence limits: 53 preliminary orders, configured/default internal costs, advertising credits/taxes not reconciled to billing. These are **not final net profit** figures. GMV Pay and Cost differ by definition and can have different date boundaries.
