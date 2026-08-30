"""python -m apps.worker.profit_cli compute [--since YYYY-MM-DD] | report --month YYYY-MM [--json]
| config [--default-cogs N]"""
import argparse
import json
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from src.config.settings import settings
from src.db.models import Shop, ShopConfig
from src.db.models_profit import ShopDaily
from src.db.session import SessionLocal
from src.domain.profit import aggregates, jobs

log = logging.getLogger("tt.profit_cli")
COLS = ("net_seller_revenue", "fees", "cogs", "ad_cost", "net_profit")


def pick_shop(session, shop_id: int | None):
    if shop_id is not None:
        s = session.get(Shop, shop_id)
    else:
        s = session.scalars(select(Shop).order_by(Shop.id)).first()
    if s is None:
        raise SystemExit("no shop found; run apps.worker.cli catalog first")
    return s


def cmd_compute(session, shop_id: int | None, since: date | None) -> dict:
    shop = pick_shop(session, shop_id)
    res = jobs.compute_order_profits(session, shop.id, since)
    agg = aggregates.recompute_daily(session, shop.id, res["dates"] or None, shop.timezone)
    return {"shop_id": shop.id, **{k: v for k, v in res.items() if k != "dates"},
            "dates": [str(d) for d in res["dates"]], **agg}


def cmd_config(session, shop_id: int | None, default_cogs: Decimal | None) -> dict:
    shop = pick_shop(session, shop_id)
    cfg = session.scalar(select(ShopConfig).where(ShopConfig.shop_id == shop.id))
    if cfg is None:
        cfg = ShopConfig(shop_id=shop.id)
        session.add(cfg)
    if default_cogs is not None:
        if default_cogs < 0:
            raise SystemExit("default cogs must be >= 0")
        cfg.default_cogs_per_unit = default_cogs
    session.commit()
    return {"shop_id": shop.id, "default_cogs_per_unit": cfg.default_cogs_per_unit,
            "currency": shop.currency}


def month_range(month: str) -> tuple[date, date]:
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    end = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
    return start, end


def report_rows(session, shop_id: int, month: str) -> list[dict]:
    start, end = month_range(month)
    q = (select(ShopDaily).where(ShopDaily.shop_id == shop_id, ShopDaily.metric_date >= start,
                                 ShopDaily.metric_date <= end).order_by(ShopDaily.metric_date))
    return [{"date": str(r.metric_date), "orders": r.orders, "settled": r.settled_orders,
             "provisional": r.provisional_orders, **{c: Decimal(getattr(r, c)) for c in COLS},
             "net_margin": r.net_margin} for r in session.scalars(q)]


def totals(rows: list[dict]) -> dict:
    t = {"date": "TOTAL", "orders": sum(r["orders"] for r in rows),
         "settled": sum(r["settled"] for r in rows),
         "provisional": sum(r["provisional"] for r in rows),
         **{c: sum((r[c] for r in rows), Decimal(0)) for c in COLS}}
    t["net_margin"] = (t["net_profit"] / t["net_seller_revenue"]).quantize(Decimal("0.000001")) \
        if t["net_seller_revenue"] > 0 else None
    return t


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, Decimal):
        return f"{v:,.0f}"
    return str(v)


def render_table(rows: list[dict]) -> str:
    hdr = ("date", "orders", "net revenue", "fees", "cogs", "ads (BLENDED/LOW)", "net profit", "margin")
    keys = ("date", "orders", "net_seller_revenue", "fees", "cogs", "ad_cost", "net_profit", "net_margin")
    body = [[_fmt(r[k]) if k != "net_margin" else (f"{r[k]:.1%}" if r[k] is not None else "-")
             for k in keys] for r in rows + [totals(rows)]]
    widths = [max(len(h), *(len(b[i]) for b in body)) for i, h in enumerate(hdr)]
    line = lambda cells: "  ".join(c.rjust(w) if i else c.ljust(w)
                                   for i, (c, w) in enumerate(zip(cells, widths, strict=True)))
    out = [line(hdr), line(["-" * w for w in widths])] + [line(b) for b in body[:-1]]
    out += [line(["-" * w for w in widths]), line(body[-1])]
    out.append("ad cost = GMV Max payout deductions, BLENDED over trailing 7 days, confidence LOW "
               "(estimate). Provisional orders: fees estimated, not settled.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="apps.worker.profit_cli")
    p.add_argument("--shop-id", type=int, default=None)
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("compute")
    sp.add_argument("--since", type=date.fromisoformat, default=None)
    sp = sub.add_parser("report")
    sp.add_argument("--month", required=True, help="YYYY-MM")
    sp = sub.add_parser("config")
    sp.add_argument("--default-cogs", type=Decimal, default=None, help="fallback COGS per unit")
    a = p.parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(message)s")
    with SessionLocal() as session:
        if a.cmd == "compute":
            print(json.dumps(cmd_compute(session, a.shop_id, a.since), default=str))
            return 0
        if a.cmd == "config":
            print(json.dumps(cmd_config(session, a.shop_id, a.default_cogs), default=str))
            return 0
        shop = pick_shop(session, a.shop_id)
        rows = report_rows(session, shop.id, a.month)
        if a.json:
            print(json.dumps({"shop_id": shop.id, "month": a.month, "rows": rows,
                              "totals": totals(rows)}, default=str))
        else:
            print(render_table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
