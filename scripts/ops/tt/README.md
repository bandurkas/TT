# Операционные скрипты (TikTok Shop / GMV Max), октябрь 2026

Запуск с Mac: `scp -q scripts/ops/tt/<x>.py vps3:/tmp/<x>.py && ssh vps3 "cd /root/TT && docker compose exec -T worker python -I - < /tmp/<x>.py" | grep -v 'retry in'`.
Перед сверкой обновить рекламу: `docker compose exec -T worker python -c "from apps.worker import main; main.run('ads_tiktok')"`.
Все скрипты читают ключи из `settings` внутри контейнера worker; секретов в файлах нет. Время печатается по Джакарте, `modify_time` кампаний — UTC.

| Файл | Что делает | Пишет? |
|---|---|---|
| affiliate_read.py | открытые/целевые сотрудничества, заявки на образцы, поиск креаторов, переписки (только чтение) | нет |
| verify.py | базы/остатки чёрных и набора, активные акции, купоны, затрагивающие чёрные | нет |
| stock2.py | остатки SKU чёрных | нет |
| camp_status.py | список GMV Max кампаний: status, modify_time | нет |
| creatives_today.py | расход по роликам Black one за даты из файла (OFF-list/keep) | нет |
| creatives.py | расход по роликам за период | нет |
| promo_read.py | все активные акции и купоны + базы трёх карточек | нет |
| new_objs.py, kill_smart.py, flash2.py, titles.py | разбор авто-акций TikTok («_smart», SmartAuto); kill_smart деактивирует BMSM | kill_smart — да |
| restore2.py | вернуть товары в наши скидки (20 %/17 % в файле — поправить) | да |
| three.py | шаблон: сменить % в наших скидках (26 % чёрные, 25 % набор) + проверка affiliate_PC | да |
| ten_reset.py, black_disc.py, black20.py, ten_now.py | история изменений скидок/базы набора и чёрных | да (устаревшие значения) |
| stock.py | выставить остаток 300 там, где 0 (inventory/update) | да |
| edit8.py, audit_wait.py, img_chk.py | partial_edit карточки 0025 на 8 пар и ожидание авто-проверки | edit8 — да |
| black10_backup_2026-10-28.json | копия карточки 0025 до правки (10 пар) | — |
| black5_daily.csv | дневные данные чёрных 14.09–25.10 для регрессии CPO/цена/расход | — |

Перед любым «пишущим» скриптом: прочитать текущее состояние, после — прочитать обратно. Правила и контекст — `HANDOFF_2026-10-28.md`.

## affiliate/ (30.10.2026, рассылка целевых приглашений)
`aff_read.py` — чтение: открытые/целевые сотрудничества, заявки на образцы, переписки (нет записи). `aff_enrich.py` — метрики продаж по шорт-листу (`/tmp/shortlist_ids.json`) + проверка пригодности. `rank_creators.py`, `build_batches.py` — отбор на Mac из скачанных пулов. `aff_create.py` — создание целевых приглашений по `/tmp/batches.json` (**пишет**; `dry_run` обязателен первым). Текст — `invite_text_v2.txt`. Итог и правила API — `docs/affiliate/outreach_2026-10-30.md`.
