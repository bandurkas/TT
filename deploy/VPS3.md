# VPS3 deploy notes

- Host 187.127.114.34, dir `/root/TT`, remote alias `github-tt` → deploy key `~/.ssh/tt_deploy_key` (read-only, repo TT).
- Ports: api 8400, dashboard 3400, caddy 80/443 (tt.lomiraproduct.com → auto TLS). Postgres/Redis internal to compose network only.
- OAuth callbacks: https://tt.lomiraproduct.com/oauth/tiktok-shop/callback, /oauth/tiktok-ads/callback
- Neighbours on the box: Jony (8200), BUBU (8300), opt-app (3000/8000). Never `docker compose down` in their dirs.
- `.env` lives only on VPS (`/root/TT/.env`); rsync/scp with `--exclude .env`.
- Deploy: `cd /root/TT && git pull && docker compose build api worker && docker compose run --rm api alembic upgrade head && docker compose up -d --force-recreate api worker`
- Check: `curl -s localhost:8400/health`; `docker compose logs -f --tail 100 api`
