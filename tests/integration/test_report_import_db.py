"""Report persistence and calendar reconciliation on the disposable test DB."""
# ruff: noqa: F811 -- pytest fixtures intentionally shadow imported fixture names
from datetime import UTC, date, datetime
from decimal import Decimal as D
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from sqlalchemy import func, select

from src.db.models import Shop
from src.db.models_profit import ShopDaily
from src.db.models_reports import ShopAdDay, SourceReport
from src.domain.dashboard.order_loaders import page
from src.domain.profit.aggregates import recompute_daily
from src.domain.reports import ad_days, import_report
from tests.integration.test_order_journal_db import db, engine  # noqa: F401
from tests.unit.test_source_reports import report


def xlsx(path, cost=100):
    sheets = report()
    for n in (2, 4):
        sheets['Sheet1'][n]['B'] = str(cost)
    main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{main}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        sheet = ET.Element('worksheet', xmlns=main)
        ET.SubElement(sheet, 'dimension', ref='A1:G2')  # stale dimension must not truncate data
        data = ET.SubElement(sheet, 'sheetData')
        for n, cells in sheets['Sheet1'].items():
            row = ET.SubElement(data, 'row', r=str(n))
            for col, value in cells.items():
                cell = ET.SubElement(row, 'c', r=f'{col}{n}', t='inlineStr')
                ET.SubElement(ET.SubElement(cell, 'is'), 't').text = value
        z.writestr('xl/worksheets/sheet1.xml', ET.tostring(sheet))
    return path


def put(db, path, day=3, shop=1):
    return import_report(db, shop, str(path), 'ads', 'Asia/Jakarta', datetime(2026, 8, day, tzinfo=UTC))


def test_idempotent_import_overlap_audit_and_shop_isolation(db, tmp_path):
    first = xlsx(tmp_path / 'first.xlsx')
    a = put(db, first)
    assert not a['unchanged'] and put(db, first)['unchanged']
    assert len(ad_days(db, 1)) == 2 and sum(r.cost for r in ad_days(db, 1)) == 100
    assert not ad_days(db, 2)
    newer = xlsx(tmp_path / 'new.xlsx', 200)
    b = put(db, newer, 4)
    assert b['report_id'] != a['report_id']
    assert sum(r.cost for r in ad_days(db, 1)) == 200
    assert db.scalar(select(func.count()).select_from(SourceReport).where(SourceReport.shop_id == 1)) == 2
    with pytest.raises(ValueError, match='not newer'), db.begin_nested():
        put(db, xlsx(tmp_path / 'old.xlsx', 50), 3)
    assert sum(r.cost for r in ad_days(db, 1)) == 200
    assert db.scalar(select(func.count()).select_from(SourceReport).where(SourceReport.shop_id == 1)) == 2
    put(db, first, shop=2)
    assert sum(r.cost for r in ad_days(db, 2)) == 100
    db.get(Shop, 1).currency = 'USD'
    db.flush()
    assert not ad_days(db, 1)


def test_calendar_cost_no_order_day_and_partial_rebuild_preserves_other_days(db, tmp_path):
    put(db, xlsx(tmp_path / 'first.xlsx'))
    day = db.scalar(select(ShopAdDay).where(ShopAdDay.shop_id == 1, ShopAdDay.metric_date == date(2026, 8, 2)))
    day.cost = D(700)  # no orders that day
    db.flush()
    recompute_daily(db, 1)
    before = db.scalar(select(ShopDaily).where(ShopDaily.shop_id == 1, ShopDaily.metric_date == date(2026, 8, 31)))
    saved = (before.orders, before.contribution, before.net_profit)
    recompute_daily(db, 1, [date(2026, 8, 1)])
    db.refresh(before)
    assert (before.orders, before.contribution, before.net_profit) == saved
    p = page(db, 1, date(2026, 8, 2), date(2026, 8, 2), 'Asia/Jakarta')
    assert p['total'] == 0 and p['summary']['ad_cost'] == 700
    assert p['summary']['net_profit'] == -700
    p = page(db, 1, date(2026, 8, 1), date(2026, 8, 3), 'Asia/Jakarta')
    assert p['advertising']['cost'] is None and p['summary']['net_profit'] is None
