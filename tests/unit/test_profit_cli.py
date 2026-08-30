from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from apps.worker import profit_cli


def test_render_table_has_settled_provisional_columns():
    rows = [{"date": "2026-08-18", "orders": 3, "settled": 1, "provisional": 2,
             "net_seller_revenue": D(300000), "fees": D(30000), "cogs": D(75000), "ad_cost": D(50000),
             "net_profit": D(145000), "net_margin": D("0.483333")}]
    out = profit_cli.render_table(rows)
    head = out.splitlines()[0]
    assert "settled" in head and "prov" in head
    assert "TOTAL" in out and "48.3%" in out


def test_cmd_config_creates_row_and_sets_default_cogs():
    session = MagicMock()
    shop = NS(id=1, currency="IDR", timezone="Asia/Jakarta")
    session.get.return_value = shop
    session.scalar.return_value = None
    out = profit_cli.cmd_config(session, 1, D(25000))
    added = session.add.call_args.args[0]
    assert added.shop_id == 1 and added.default_cogs_per_unit == D(25000)
    assert out == {"shop_id": 1, "default_cogs_per_unit": D(25000), "currency": "IDR"}
    session.commit.assert_called_once()
