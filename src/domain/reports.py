"""Strict read-only XLSX extraction and idempotent, auditable shop report ingestion."""
import hashlib
import io
import json
import posixpath
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.db.models import Shop
from src.db.models_reports import ShopAdDay, SourceReport

ZERO = Decimal(0)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ADS_HEADERS = ["By Day", "Cost", "SKU orders (Current shop)",
               "Cost per order (Current shop)", "Gross revenue (Current shop)",
               "ROI (Current shop)", "Currency"]


def number(v):
    d = Decimal(str(v))
    if not d.is_finite() or abs(d) >= Decimal(100000000000000):
        raise ValueError("Non-finite or oversized financial value")
    return d


def read_xlsx(content: bytes) -> dict:
    if len(content) > 10_000_000:
        raise ValueError("Report too large")
    with ZipFile(io.BytesIO(content)) as z:
        if sum(x.file_size for x in z.infolist()) > 40_000_000:
            raise ValueError("Expanded report too large")
        def xml(path):
            data = z.read(path)
            if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                raise ValueError("XML entities are not allowed")
            return ET.fromstring(data)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.findall(".//m:t", NS))
                      for si in xml("xl/sharedStrings.xml").findall("m:si", NS)]
        rels = {r.attrib["Id"]: r.attrib["Target"]
                for r in xml("xl/_rels/workbook.xml.rels")}
        result = {}
        for s in xml("xl/workbook.xml").findall("m:sheets/m:sheet", NS):
            rid = s.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rels[rid]
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not target.startswith("xl/"):
                raise ValueError("Invalid sheet path")
            rows = defaultdict(dict)
            for c in xml(target).findall(".//m:sheetData/m:row/m:c", NS):
                if c.find("m:f", NS) is not None or c.attrib.get("t") == "e":
                    raise ValueError("Reports must contain exported values, not formulas/errors")
                col, row = re.fullmatch(r"([A-Z]+)(\d+)", c.attrib["r"]).groups()
                value = c.findtext("m:v", "", NS)
                if c.attrib.get("t") == "s":
                    value = shared[int(value)]
                elif c.attrib.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in c.findall(".//m:t", NS))
                if value != "":
                    rows[int(row)][col] = value
            result[s.attrib["name"]] = dict(sorted(rows.items()))
        return result


def parse_ads(sheets, currency):
    if len(sheets) != 1:
        raise ValueError("Expected one shop overview sheet")
    rows = next(iter(sheets.values()))
    if [rows.get(1, {}).get(c) for c in "ABCDEFG"] != ADS_HEADERS:
        raise ValueError("Expected daily Campaign overview export with Cost and Currency")
    days, totals = [], []
    for row, r in rows.items():
        if row == 1:
            continue
        if r.get("G") != currency:
            raise ValueError(f"Currency mismatch at row {row}")
        cost, orders, revenue = (number(r[c]) for c in ("B", "C", "E"))
        if min(cost, orders, revenue) < 0 or orders != orders.to_integral_value():
            raise ValueError(f"Invalid nonnegative metric at row {row}")
        if r["A"] == "-":
            totals.append((cost, orders, revenue))
            continue
        if not r["A"].endswith(" 00:00:00"):
            raise ValueError("Expected daily data at midnight")
        day = date.fromisoformat(r["A"][:10])
        days.append({"date": str(day), "cost": str(cost), "sku_orders": int(orders),
                     "gross_revenue": str(revenue), "row": row})
    if not days or len(totals) != 1:
        raise ValueError("Missing daily rows or unique total")
    days.sort(key=lambda x: x["date"])
    start, end = date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])
    if len({x["date"] for x in days}) != len(days) or len(days) != (end-start).days+1:
        raise ValueError("Duplicate dates or gaps in daily report")
    cost = sum((number(d["cost"]) for d in days), ZERO)
    orders = sum(d["sku_orders"] for d in days)
    revenue = sum((number(d["gross_revenue"]) for d in days), ZERO)
    if (cost, orders) != totals[0][:2]:
        raise ValueError("Daily Cost/orders do not match report total")
    delta = revenue - totals[0][2]
    if abs(delta) > 1:
        raise ValueError("Revenue total mismatch exceeds one currency unit")
    return start, end, {"days": days, "cost": str(cost), "sku_orders": orders,
                        "reported_gross_revenue": str(totals[0][2]),
                        "revenue_rounding_difference": str(delta),
                        "scope": "shop_overview", "metric": "Cost",
                        "taxes_and_credits": "not_reconciled"}


def parse_income(sheets, currency):
    rows, report = sheets["Order details"], sheets["Reports"]
    if report[4]["F"] != currency or report[3]["F"] != "UTC+7":
        raise ValueError("Unexpected income currency/timezone")
    start, end = (date.fromisoformat(v.replace("/", "-"))
                  for v in report[2]["F"].split("-"))
    data, ids = [], set()
    for i, r in rows.items():
        if i == 1:
            continue
        if r["A"] in ids or r["E"] != currency:
            raise ValueError("Duplicate income operation or currency mismatch")
        ids.add(r["A"])
        if number(r["F"]) != number(r["G"])+number(r["O"])+number(r["BK"]):
            raise ValueError(f"Income identity failed row {i}")
        data.append({"id": r["A"], "type": r["B"], "created": r["C"], "settled": r["D"],
                     "settlement": r["F"], "revenue": r["G"], "fees": r["O"],
                     "refund": r["L"], "dynamic_commission": r["AN"], "processing": r["AR"],
                     "tax": r["AZ"], "adjustment": r["BK"], "row": i})
    for key, i in (("settlement", 6), ("revenue", 7), ("fees", 15), ("adjustment", 62)):
        if sum((number(d[key]) for d in data), ZERO) != number(report[i]["F"]):
            raise ValueError(f"Income total mismatch: {key}")
    return start, end, {"operations": data}


def import_report(session, shop_id, path, kind, timezone, observed_at):
    if observed_at.tzinfo is None or observed_at > datetime.now(UTC) + timedelta(minutes=5):
        raise ValueError("Observed-at must be timezone-aware and not in the future")
    shop = session.get(Shop, shop_id)
    if not shop or timezone != shop.timezone:
        raise ValueError("Explicit report timezone must match the shop timezone")
    if kind not in ("ads", "income"):
        raise ValueError("Unknown report kind")
    content = Path(path).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    prior = session.scalar(select(SourceReport).where(SourceReport.shop_id == shop_id,
                           SourceReport.kind == kind, SourceReport.sha256 == digest))
    if prior:
        return {"report_id": prior.id, "unchanged": True}
    sheets = read_xlsx(content)
    start, end, data = (parse_ads if kind == "ads" else parse_income)(sheets, shop.currency)
    observed_day = observed_at.astimezone(ZoneInfo(timezone)).date()
    if end > observed_day:
        raise ValueError("Report contains future dates")
    report = SourceReport(shop_id=shop_id, kind=kind, sha256=digest,
        filename=Path(path).name, currency=shop.currency, timezone=timezone,
        period_start=start, period_end=end, observed_at=observed_at,
        imported_at=datetime.now(UTC), data=data)
    session.add(report)
    session.flush()
    if kind == "ads":
        old = {d.metric_date: (d, r) for d, r in session.execute(
            select(ShopAdDay, SourceReport).join(SourceReport, SourceReport.id == ShopAdDay.report_id)
            .where(ShopAdDay.shop_id == shop_id, ShopAdDay.metric_date >= start,
                   ShopAdDay.metric_date <= end))}
        for v in data["days"]:
            day = date.fromisoformat(v["date"])
            pair = old.get(day)
            if pair and pair[1].observed_at >= observed_at:
                raise ValueError("Overlapping report is not newer; existing values preserved")
            d = pair[0] if pair else ShopAdDay(shop_id=shop_id, metric_date=day)
            d.report_id, d.currency = report.id, shop.currency
            d.cost, d.sku_orders, d.gross_revenue = number(v["cost"]), v["sku_orders"], number(v["gross_revenue"])
            d.partial = day >= observed_day
            d.manual = False
            session.add(d)
    session.commit()
    return {"report_id": report.id, "unchanged": False, "sha256": digest,
            "period": [str(start), str(end)], "rows": len(data.get("days", data.get("operations", [])))}


MANUAL_SCOPE = "manual_entry"

# Ads Manager reports the SELECTED DATE RANGE, so a range's totals are trivially entered as one day.
# Both checks below compare only against facts already in the database, and are overridable, never silent.
PERIOD_TOTAL_FACTOR = 2             # entered units / GMV above this multiple of the day's own actuals
COST_DROP_FACTOR = Decimal("0.5")   # a replacement cost below this share of the one it replaces
COST_SPIKE_FACTOR = Decimal(4)      # a cost above this multiple of the recent daily median
COST_SPIKE_WINDOW = 14              # days of spend history the median is taken over
COST_SPIKE_MIN_DAYS = 5             # below this much history the median means nothing


class NeedsConfirmation(ValueError):
    """A deterministic sanity check rejected the entry; the operator may override it with confirm=True."""


def _shop_daily(session, shop_id, day):
    from src.db.models_profit import ShopDaily
    return session.scalar(select(ShopDaily).where(ShopDaily.shop_id == shop_id,
                                                  ShopDaily.metric_date == day))


def _plain(v):
    """Money for an operator-facing message: 450000.000000 -> 450000."""
    return f"{v.normalize():f}"


def _range_hint(day):
    return (f"Ads Manager reports the selected date range; these look like period totals, not one day. "
            f"Re-select {day} alone, or confirm to save them as entered.")


def _recent_cost_median(session, shop_id, day):
    """Median over the last COST_SPIKE_WINDOW days *with spend* before `day` — zero-spend days are
    excluded in SQL, not after the limit, so a pause in advertising cannot empty the window and
    silently disarm the check on the day spend resumes. Deliberately reads only ShopAdDay: it is the
    one baseline available the moment a day opens, before any order has synced. Currency is matched
    to the shop's, on the same rule as ad_days(): never mix incompatible money."""
    rows = session.scalars(select(ShopAdDay.cost).join(Shop, Shop.id == ShopAdDay.shop_id)
                           .where(ShopAdDay.shop_id == shop_id, ShopAdDay.metric_date < day,
                                  ShopAdDay.cost > 0, ShopAdDay.currency == Shop.currency)
                           .order_by(ShopAdDay.metric_date.desc()).limit(COST_SPIKE_WINDOW)).all()
    costs = sorted(number(r) for r in rows)
    if len(costs) < COST_SPIKE_MIN_DAYS:
        return None
    mid = len(costs) // 2
    return costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2


def _check_manual_day(session, shop_id, day, cost, sku_orders, gross_revenue, prior_day):
    """The two ways manual entry has actually corrupted live data: a period's totals typed into a
    single day, and a fuller record replaced by a thinner one. Raises NeedsConfirmation."""
    # When the day has no synced orders yet (units = gmv = 0) these two checks stand down: Ads Manager
    # legitimately runs ahead of our hourly order sync, so comparing against zero would refuse every
    # early-morning entry. That gap is deliberate and bounded — sku_orders and gross_revenue are
    # reported figures that no profit line reads; Cost is the field that moves net profit, and it is
    # covered independently by the median check below, which needs no analytics at all.
    actual = _shop_daily(session, shop_id, day)
    if actual is not None:
        units = int(actual.units or 0)
        gmv = number(actual.gmv or 0)
        if units and sku_orders > PERIOD_TOTAL_FACTOR * units:
            raise NeedsConfirmation(f"SKU orders {sku_orders} is over {PERIOD_TOTAL_FACTOR}x the {units} "
                                    f"units the shop actually sold on {day}. " + _range_hint(day))
        if gmv > ZERO and gross_revenue > PERIOD_TOTAL_FACTOR * gmv:
            raise NeedsConfirmation(f"Gross revenue {_plain(gross_revenue)} is over {PERIOD_TOTAL_FACTOR}x the "
                                    f"{_plain(gmv)} GMV the shop actually made on {day}. " + _range_hint(day))
    median = _recent_cost_median(session, shop_id, day)
    if median is not None and cost > median * COST_SPIKE_FACTOR:
        raise NeedsConfirmation(f"Cost {_plain(cost)} is over {COST_SPIKE_FACTOR}x the {_plain(median)} "
                                f"median daily spend of the days before {day}. " + _range_hint(day))
    if prior_day is None:
        return
    prior_cost = number(prior_day.cost or 0)
    if prior_cost > ZERO and cost < prior_cost * COST_DROP_FACTOR:
        raise NeedsConfirmation(f"Cost {_plain(cost)} is far below the {_plain(prior_cost)} already "
                                f"recorded for {day}, and "
                                f"ad spend does not fall within a day. This would overwrite a fuller record; "
                                f"check the figure, or confirm to replace it.")
    emptied = [name for name, old, new in (("SKU orders", int(prior_day.sku_orders or 0), sku_orders),
                                           ("gross revenue", number(prior_day.gross_revenue or 0), gross_revenue))
               if old and not new]
    if emptied:
        raise NeedsConfirmation(f"This would blank {' and '.join(emptied)} already recorded for {day}. "
                                f"Enter the full figures, or confirm to replace the record as entered.")



def record_manual_ad_day(session, shop_id, day, cost, sku_orders, gross_revenue, observed_at, timezone,
                         final=False, note="", entered_by="dashboard", confirm=False):
    """Operator-entered daily Cost (from the Ads Manager / GMV Max overview screen) until the Ads API
    is approved. Same audit trail as XLSX imports: a SourceReport (kind=ads, scope manual_entry) with a
    content hash, and a ShopAdDay row that only a NEWER observation may replace. `final=False` keeps the
    day flagged partial (figures still moving); `final=True` marks the day complete.

    `sku_orders` / `gross_revenue` of None mean "leave whatever the day already has": the operator
    updates Cost several times a day and must not blank the other figures by omitting them. Blanking
    stays possible, but only by entering 0 explicitly."""
    if observed_at.tzinfo is None or observed_at > datetime.now(UTC) + timedelta(minutes=5):
        raise ValueError("Observed-at must be timezone-aware and not in the future")
    shop = session.get(Shop, shop_id)
    if not shop or timezone != shop.timezone:
        raise ValueError("Explicit report timezone must match the shop timezone")
    observed_day = observed_at.astimezone(ZoneInfo(timezone)).date()
    if day > observed_day:
        raise ValueError("Report contains future dates")
    if final and day >= observed_day:
        raise ValueError("A day can only be marked final after it has ended in the shop timezone")
    pair = session.execute(select(ShopAdDay, SourceReport)
                           .join(SourceReport, SourceReport.id == ShopAdDay.report_id)
                           .where(ShopAdDay.shop_id == shop_id, ShopAdDay.metric_date == day)).first()
    prior_day = pair[0] if pair else None
    carried = []
    if sku_orders is None:
        if prior_day is not None:
            carried.append("sku_orders")
        sku_orders = int(prior_day.sku_orders or 0) if prior_day is not None else 0
    if gross_revenue is None:
        if prior_day is not None:
            carried.append("gross_revenue")
        gross_revenue = number(prior_day.gross_revenue or 0) if prior_day is not None else ZERO
    cost, gross_revenue = number(cost), number(gross_revenue)
    sku_orders = int(sku_orders)
    if min(cost, gross_revenue) < 0 or sku_orders < 0:
        raise ValueError("Cost, SKU orders and gross revenue must be non-negative")
    payload = {"days": [{"date": str(day), "cost": str(cost), "sku_orders": sku_orders,
                         "gross_revenue": str(gross_revenue), "row": 1}],
               "cost": str(cost), "sku_orders": sku_orders, "reported_gross_revenue": str(gross_revenue),
               "revenue_rounding_difference": "0", "scope": MANUAL_SCOPE, "metric": "Cost",
               "taxes_and_credits": "not_reconciled", "final": bool(final), "note": (note or "")[:500],
               "entered_by": entered_by, "observed_at": observed_at.isoformat(timespec="seconds"),
               **({"confirmed_override": True} if confirm else {}),
               # Not freshly observed: inherited from the day's previous entry because the operator
               # left the field empty. Matters most under final=True, where these become the day's
               # closing figures without having been read off the screen again.
               **({"carried_over": carried} if carried else {})}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    prior = session.scalar(select(SourceReport).where(SourceReport.shop_id == shop_id,
                           SourceReport.kind == "ads", SourceReport.sha256 == digest))
    if prior:
        return {"report_id": prior.id, "unchanged": True}
    if pair and pair[1].observed_at >= observed_at:
        raise ValueError("A newer or equal observation for this day already exists; enter a later one")
    if not confirm:
        _check_manual_day(session, shop_id, day, cost, sku_orders, gross_revenue, prior_day)
    report = SourceReport(shop_id=shop_id, kind="ads", sha256=digest,
                          filename=f"manual-entry {day} @ {observed_at.astimezone(ZoneInfo(timezone)):%H:%M} {timezone}",
                          currency=shop.currency, timezone=timezone, period_start=day, period_end=day,
                          observed_at=observed_at, imported_at=datetime.now(UTC), data=payload)
    session.add(report)
    session.flush()
    d = prior_day if prior_day is not None else ShopAdDay(shop_id=shop_id, metric_date=day)
    d.report_id, d.currency = report.id, shop.currency
    d.cost, d.sku_orders, d.gross_revenue = cost, sku_orders, gross_revenue
    d.partial = (day >= observed_day) or not final
    d.manual = True
    session.add(d)
    session.commit()
    return {"report_id": report.id, "unchanged": False, "sha256": digest, "period": [str(day), str(day)],
            "rows": 1, "partial": d.partial}


def ad_days(session, shop_id):
    # Fail closed for historical currency changes; never mix incompatible money.
    return list(session.scalars(select(ShopAdDay).join(Shop, Shop.id == ShopAdDay.shop_id)
                                .where(ShopAdDay.shop_id == shop_id, ShopAdDay.currency == Shop.currency)))


def coverage(rows, start, end):
    selected = {r.metric_date: r for r in rows if start <= r.metric_date <= end}
    expected = (end-start).days+1
    missing = [str(start+timedelta(days=i)) for i in range(expected)
               if start+timedelta(days=i) not in selected]
    known_cost = sum((r.cost for r in selected.values()), ZERO)
    return {"cost": known_cost if not missing else None, "known_cost": known_cost,
            "covered_days": len(selected), "expected_days": expected,
            "missing_days": missing, "partial_days": [str(d) for d, r in selected.items() if r.partial],
            "status": "missing" if missing else "partial" if any(r.partial for r in selected.values()) else "reported",
            "source": "Campaign overview · Cost", "taxes_and_credits": "not_reconciled"}


def advertising_summary(session, shop_id, start, end, timezone):
    from src.domain.dashboard.loaders import ad_deductions
    days = ad_days(session, shop_id)
    result = coverage(days, start, end)
    payments = ad_deductions(session, shop_id, start, end, timezone)
    result["gmv_pay"] = sum((r["amount"] for r in payments), ZERO)
    result["payment_basis"] = "statement_date; not campaign Cost"
    ids = {r.report_id for r in days if start <= r.metric_date <= end}
    reports = {r.id: r for r in session.scalars(select(SourceReport).where(SourceReport.id.in_(ids)))} if ids else {}
    result["reports"] = [{"filename": r.filename, "sha256": r.sha256,
                           "observed_at": r.observed_at, "timezone": r.timezone,
                           "timezone_basis": "operator_confirmed",
                           "scope": (r.data or {}).get("scope", "shop_overview"),
                           "period_start": r.period_start, "period_end": r.period_end} for r in reports.values()]
    result["days"] = [{"date": r.metric_date, "cost": r.cost, "partial": r.partial,
                        "sku_orders": r.sku_orders, "gross_revenue": r.gross_revenue,
                        "source": (reports.get(r.report_id).data or {}).get("scope", "shop_overview")
                        if r.report_id in reports else "shop_overview",
                        "observed_at": reports[r.report_id].observed_at if r.report_id in reports else None,
                        "note": ((reports.get(r.report_id).data or {}).get("note") or None)
                        if r.report_id in reports else None}
                       for r in sorted(days, key=lambda r: r.metric_date) if start <= r.metric_date <= end]
    manual = sum(1 for d in result["days"] if d["source"] == MANUAL_SCOPE)
    result["manual_days"] = manual
    result["source"] = ("Campaign overview · Cost" if not manual else
                        "Manual entry from Ads Manager · Cost (until Ads API)" if manual == len(result["days"])
                        else "Campaign overview + manual entry · Cost")
    return result


def income_evidence(session, shop_id):
    report = session.scalar(select(SourceReport).where(SourceReport.shop_id == shop_id,
                            SourceReport.kind == "income").order_by(SourceReport.observed_at.desc()).limit(1))
    return {r["id"]: {**r, "filename": report.filename, "sha256": report.sha256}
            for r in report.data["operations"] if r["type"] == "Order"} if report else {}
