# Onboarding: подключение lomira.product (2026-08-30)

Что нужно получить до Phase 0 connectivity test. Все ключи → локально `.env` (в .gitignore), затем на VPS3 `/root/TT/.env`.

## A. TikTok Shop API (Partner Center, регион ID/SEA)
1. https://partner.tiktokshop.com/account/sign-up — регистрация как APP developer.
2. App & Service → Create App → **Custom App**, name `TT Profit Control`, redirect `https://localhost/callback` (код копируем из URL вручную; заменить на HTTPS-домен, когда появится).
3. Manage API — включить: Shop Authorized Info, Product, Order, Fulfillment, **Finance**, **Data Insights/Analytics**, **Affiliate Seller**, Return & Refund, Promotion. Недоступные → `NOT AVAILABLE` в capability matrix.
4. Со страницы app: App Key, App Secret, Service ID → `TIKTOK_SHOP_APP_KEY/SECRET`.
5. Authorization link → логин в Seller Center lomira.product → redirect с `code=` → обмен на access (7д) + refresh (30д) через `auth.tiktok-shops.com/api/v2/token/get`; затем `shop_cipher` через authorization shops endpoint. Код короткоживущий.

## B. TikTok Ads (Marketing API v1.3)
1. https://business-api.tiktok.com/portal → Become a Developer.
2. My Apps → Create App: redirect `https://localhost/callback`; scopes **read-only**: Ad Account Mgmt (read), Ads Mgmt (read), Reporting, Creative Mgmt (read). Никаких write-скоупов (SPEC §2.4).
3. App review (1–3+ раб. дня). Sandbox не используем.
4. App ID, Secret → `TIKTOK_ADS_APP_ID/SECRET`.
5. Advertiser authorization URL → выбрать кабинет lomira → redirect с `auth_code=` → `POST /open_api/v1.3/oauth2/access_token/` → долгоживущий token + advertiser_id.
6. Проверить наличие GMV Max в Reporting для этого кабинета.

## C. Telegram
@BotFather → /newbot → token; группа для отчётов + бот в ней; chat_id через getUpdates.

## D. COGS по SKU
`seller_sku | name | cogs/unit IDR | packaging/unit | inbound logistics/unit | effective_from`.

## Открытые вопросы
- Домен/HTTPS для VPS3 (callback + dashboard)?
- Доступен ли Finance scope для ID-магазина без доп. одобрения?
- Отдаёт ли Ads Reporting GMV Max?
