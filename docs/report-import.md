# Advertising Cost and income report reconciliation

GMV Pay is a payment from shop funds, not campaign consumption. The dashboard now uses **daily Cost** from the supplied shop overview XLSX. Cost includes days without orders. Order/product attribution uses same-day net-revenue weights and remains BLENDED / LOW; unallocated spend remains in the shop total.

## Verified source snapshot, 2026-08-31

- Campaign overview, 2025-08-31 through 2026-08-31: 366 daily rows, total Cost **IDR 4,347,403**. The summary row is checked, never added again.
- Through August 30: **IDR 4,273,414**. August 31: **IDR 73,989**, partial day. The report was observed at 2026-08-30 21:39:39 UTC (file timestamp, not a platform-certified export time); report timezone explicitly confirmed as Asia/Jakarta.
- Income report: 41 operations = 30 orders + 11 GMV Pay payments, **IDR 2,495,139**. The two supplied copies have the same SHA-256 and are imported once. All XML rows are read despite the workbook's stale dimension attribute.
- Three cancelled orders have zero settlement and refund evidence in the export. Their source rows are shown without inventing COGS or a profit calculation.
- Previously displayed IDR 2,400,814 was allocated GMV Pay on the selected order cohort. It was not actual advertising Cost. Older handoff figures using that method are superseded.

## Safe import

Keep original XLSX files outside Git in the server's private `data/reports` directory. There is no public upload endpoint. Back up the DB before migrations/recalculation, then run the commands inside the updated worker image:

```sh
python -m apps.worker.report_cli ads '/app/data/reports/Campaign overview data 20250831 - 20260831.xlsx' --shop-id 1 --timezone Asia/Jakarta --observed-at 2026-08-30T21:39:39+00:00
python -m apps.worker.report_cli income '/app/data/reports/income_20260830221550(UTC+7).xlsx' --shop-id 1 --timezone Asia/Jakarta --observed-at 2026-08-30T21:27:45+00:00
python -m apps.worker.profit_cli compute
```

Migration: `d83f921a6b40`. Deploy API, worker and dashboard together: an old worker must not overwrite the corrected calculations. All order profits and daily aggregates are rebuilt, even when a caller supplies an incremental date. Re-running identical inputs leaves current profit versions unchanged.

Imports retain filenames, SHA-256, observed time, timezone, source rows and all report revisions. Same shop/kind/hash is idempotent. Overlapping dates are replaced only by a newer observed report; older conflicting imports fail atomically. The operator must confirm shop scope, timezone and actual observation time; the overview export has no account/campaign IDs.

## Interpretation and limitations

- Known zero requires an explicit daily source row. A missing day produces unavailable Cost and profit, not zero. Incomplete export days remain partial until replaced by a newer report.
- GMV Pay uses statement dates for reconciliation; these may differ from payment/export dates. It is never subtracted a second time.
- Calendar profit = order contribution in the selected period minus Cost on those dates. Filtered order views show only allocated cohort costs and say so. Shop Cost on days without eligible orders is visible in `unallocated_ad_cost`.
- Unknown COGS/fees/advertising suppress dependent profit, margin, chart totals and recommendations. A configured default COGS is an explicit estimate, not a verified invoice.
- Reported Cost is not fully reconciled cash cost. Ad credits, promotional offsets and billing taxes still require billing reconciliation. Final settlement does not establish final net profit. Do not increase advertising budgets based solely on this estimate.
- Income evidence is an audit reference, not a second source of deductions. Tax and component commissions already included in Total Fees are not subtracted again.

## Verification / rollback

Run the full Python suite on Linux and the PostgreSQL integration tests only against the explicitly named disposable `order_journal_test` DB. Check import idempotence, newer/older overlap, shop/currency isolation, zero and missing days, days without orders, and repeated full rebuilds. Then run frontend tests, typecheck, lint, build, independent review and live endpoint/UI checks.

Before release, retain the prior API/worker/dashboard images and a verified `pg_dump` backup outside the repository. Prefer rolling forward. A full rollback must restore a coordinated DB snapshot and all three previous images; merely restarting the old worker reintroduces the wrong expense source. Preserve new imports/backups before any rollback that would discard later work.
