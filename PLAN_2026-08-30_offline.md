# План работ без доступа к API (пока Partner registration review)

Принцип: всё, что не требует живых токенов, делаем сейчас на фикстурах; адаптеры — по документированным контрактам, каждая непроверенная деталь помечается `UNVERIFIED` и попадает в capability matrix.

## Этап A — Data foundation (SPEC §5, §21, §22, §26, §27)
- SQLAlchemy 2.0 модели всех сущностей §5 + `raw_api_responses`, `integration_sync_state`, `audit_log`, `shop_config` (§28).
- Деньги: `Numeric(20,6)` + `currency`; в Python только `Decimal`. Время: UTC `timestamptz`; `metric_date` в таймзоне магазина.
- Alembic: initial migration. `docs/data-model.md` (Deliverable 2).

## Этап B — Finance engine (SPEC §6, §7, §20, §34) — чистые функции, без ORM/LLM
- `analytics/profitability.py`: net seller revenue → contribution → net profit; статусы PROVISIONAL/SETTLED/PAID/REFUNDED/ADJUSTED; versioned COGS lookup; multi-SKU order split.
- `analytics/attribution.py`: PLATFORM_REPORTED / DIRECT_CREATIVE / PROPORTIONAL / BLENDED + confidence.
- Transaction type mapping: native → normalized, UNKNOWN сохраняется.
- Тесты — весь список §34, фикстура из спеки (23,500) точным Decimal.
- `docs/profit-calculation.md` (Deliverable 3), `docs/attribution-model.md` (Deliverable 4).

## Этап C — Analytics engine (SPEC §8, §9, §14, §18, §19)
- `baselines.py` (24h/3d/7d/14d/30d/same-weekday), `creative_scoring.py` (WINNER/PROMISING/TRAFFIC_NO_SALES/LOW_ATTENTION/LOSER/FATIGUING, относительные пороги + min sample), `anomaly_detection.py`, `data_quality.py`, `reconciliation.py` (MATCHED/PARTIAL/MISMATCH/PENDING), `alerts/` (severity, dedupe, cooldown).
- Все на dataclass-входах, тесты на фикстурах.

## Этап D — Integrations (SPEC §3, §4, §25, §26)
- `tiktok_shop/client.py`: подпись запросов (HMAC-SHA256, документированный алгоритм — UNVERIFIED до первого живого вызова), auto-refresh, пагинация, backoff, raw-сохранение. Методы по §25 как заглушки с path/version из документации (помечены UNVERIFIED).
- `tiktok_ads/client.py`: то же для Business API v1.3 (Access-Token header, report endpoint).
- `telegram/client.py`: sendMessage + форматтер daily report (§15).
- `docs/tiktok-api-capability-matrix.md`: заполнить endpoints/scopes из документации, статус UNKNOWN → «documented, unverified».

## Этап E — Ревью
Независимое код-ревью (субагент) → правки → подтверждающее ревью. Только потом деплой на VPS3.

## Не делаем сейчас
LLM-агенты (§11–12), дашборд (§41–56), Celery-джобы — ждут реальных данных и подтверждённых полей API.

## После получения токенов
Deliverable 5 connectivity test → фикстуры из реальных ответов → правка моделей/адаптеров → Deliverable 6 reconciliation.
