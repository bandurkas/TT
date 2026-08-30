# TT — TikTok Shop Profit Control AI

Спека: `docs/SPEC.md` (v1.0, 2026-08-30) — источник истины по продукту. Текущее состояние: `HANDOFF_*.md` (самый свежий по дате; на 31.08 — HANDOFF_2026-08-31.md).

## Жёсткие правила (из SPEC §38)
- Не выдумывать TikTok API endpoints — сверяться с актуальной официальной документацией перед каждым адаптером; недоступное поле = фича `NOT AVAILABLE`, не костыль.
- Все финансовые расчёты детерминированные, `Decimal`/целые minor units, никогда float. LLM не источник чисел.
- Сырые ответы API сохраняем (`raw_*` → `normalized_*` → `analytics_*`). Ingestion идемпотентный.
- Provisional settlement ≠ final. Оценочная атрибуция рекламы ≠ точная. Reported ROAS ≠ adjusted/blended — всегда подписывать.
- MVP read-only: никаких изменений рекламы через API. Любая будущая write-операция = policy engine + approval + audit log.
- Каждая рекомендация: evidence + confidence; неполные данные понижают confidence.
- Финансовая корректность важнее UI.

## Порядок работ (SPEC §37/§39)
Phase 0 → 6 deliverables (capability matrix, data-model, profit-calculation, attribution-model, connectivity test, reconciliation test) → только потом полный MVP. К автоматическим рекомендациям не переходить, пока финансовый движок не сверен с Seller Center вручную.

## Флоу разработки
план → код (минимальный дифф) → тесты (весь набор) → независимое код-ревью → правки → подтверждающее ревью → деплой → live-check по логам. Комментарии в коде минимальные.

## Инфра
- Локально: `~/Desktop/TT`, репо `git@github.com:bandurkas/TT.git`, ветка `main`.
- VPS3 (187.127.114.34): `/root/TT`, remote `github-tt` (deploy key `~/.ssh/tt_deploy_key`). Порты: API **8400**, dashboard **3400**; postgres/redis без host-портов. На VPS3 живут Jony (8200) и BUBU (8300) — не трогать.
- Деплой: `git pull && docker compose build <svc> && docker compose up -d --force-recreate <svc>`. Файлы на VPS руками не править. `.env` только на VPS, в репо не попадает.
- Время: бизнес-день = таймзона магазина (Asia/Jakarta), хранение в UTC.
