from unittest.mock import MagicMock, patch

import pytest

from apps.worker import cli

C = "apps.worker.cli"


def parse(argv):
    with patch(f"{C}.run_command") as rc:
        rc.return_value = {}
        assert cli.main(argv) == 0
        return rc.call_args.args[0]


def test_days_default_none_for_orders_and_statements():
    assert parse(["orders"]).days is None
    assert parse(["statements"]).days is None
    assert parse(["orders", "--days", "7"]).days == 7
    assert parse(["metrics"]).days == 60
    assert parse(["backfill"]).days == 60
    assert parse(["order-statements"]).days == 90


def test_order_ids_and_status_parse():
    a = parse(["order-statements", "--order-ids", "a,b,,c"])
    assert [x for x in a.order_ids.split(",") if x] == ["a", "b", "c"]
    assert parse(["status"]).cmd == "status"
    with pytest.raises(SystemExit):
        parse(["nope"])


def _ctx():
    ctx = MagicMock()
    ctx.now = cli.datetime(2026, 8, 30, tzinfo=cli.UTC)
    ctx.shop.external_shop_id = "s1"
    ctx.sink.count = 3
    return ctx


@patch(f"{C}.jobs.sync_orders", return_value={"orders": 1})
@patch(f"{C}.build_context")
@patch(f"{C}.SessionLocal")
def test_orders_routes_since(sl, bc, so):
    bc.return_value = _ctx()
    assert cli.main(["orders"]) == 0
    assert so.call_args.kwargs["since"] is None
    cli.main(["orders", "--days", "3"])
    assert so.call_args.kwargs["since"] == cli.datetime(2026, 8, 27, tzinfo=cli.UTC)


@patch(f"{C}.jobs.sync_order_statements", return_value={})
@patch(f"{C}.build_context")
@patch(f"{C}.SessionLocal")
def test_order_statements_routes_ids(sl, bc, sos):
    bc.return_value = _ctx()
    cli.main(["order-statements", "--order-ids", "a,b"])
    assert sos.call_args.args[1] == ["a", "b"] and sos.call_args.kwargs["unsettled_days"] == 90
    cli.main(["order-statements"])
    assert sos.call_args.args[1] is None


@patch(f"{C}.cmd_status", return_value={"counts": {}})
@patch(f"{C}.SessionLocal")
def test_status_is_db_only(sl, st, capsys):
    with patch(f"{C}.build_context") as bc:
        assert cli.main(["status"]) == 0
        bc.assert_not_called()
    assert '"counts"' in capsys.readouterr().out


@patch(f"{C}.load_cogs", return_value={"inserted": 1})
@patch(f"{C}.parse_cogs_csv", return_value=[])
@patch(f"{C}.shop_from_db")
@patch(f"{C}.SessionLocal")
def test_cogs_uses_db_shop_no_api(sl, sfd, pc, lc):
    sfd.return_value = MagicMock(id=9, external_shop_id="s1")
    with patch(f"{C}.build_context") as bc:
        assert cli.main(["cogs", "--file", "f.csv"]) == 0
        bc.assert_not_called()
    assert lc.call_args.args[1] == 9


@patch(f"{C}.build_context", side_effect=RuntimeError("no token"))
@patch(f"{C}.SessionLocal")
def test_exception_prints_error_json(sl, bc, capsys):
    assert cli.main(["catalog"]) == 1
    assert '"error": "RuntimeError: no token"' in capsys.readouterr().out
