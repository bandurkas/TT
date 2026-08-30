"""Shop-scoped, paginated queries. No buyer PII is returned by the order ledger."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from src.db.models import Order, OrderItem, OrderProfit, Product, Sku
from src.db.models_finance import OrderStatementRecord
from src.domain.dashboard import orders as O


def _final():
    return and_(OrderProfit.profit_status.in_(O.FINAL_STATUSES),
                OrderProfit.inputs_snapshot["source"].astext == "settled")


def _base(shop_id, start, end, tz, search, state, loss_only):
    z = ZoneInfo(tz)
    conditions = [Order.shop_id == shop_id,
                  Order.order_created_at >= datetime.combine(start, datetime.min.time(), tzinfo=z),
                  Order.order_created_at < datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=z)]
    if search:
        product_match = (select(OrderItem.id).join(Product, Product.id == OrderItem.product_id)
                         .where(OrderItem.order_id == Order.id, Product.shop_id == shop_id,
                                Product.title.icontains(search, autoescape=True)).exists())
        conditions.append(or_(Order.external_order_id.icontains(search, autoescape=True), product_match))
    if state == "not_calculated":
        conditions.append(OrderProfit.id.is_(None))
    elif state == "preliminary":
        conditions.extend([OrderProfit.id.is_not(None), ~func.coalesce(_final(), False)])
    elif state == "final":
        conditions.append(_final())
    if loss_only:
        conditions.append(OrderProfit.estimated_net_profit < 0)
    return (select(Order, OrderProfit).outerjoin(OrderProfit, and_(OrderProfit.order_id == Order.id,
                                                                 OrderProfit.is_current.is_(True)))
            .where(*conditions))


def items_for(session, shop_id, order_ids):
    if not order_ids:
        return {}
    q = (select(OrderItem, Product.title, Sku.external_sku_id, Sku.title)
         .join(Order, Order.id == OrderItem.order_id)
         .outerjoin(Product, and_(Product.id == OrderItem.product_id, Product.shop_id == shop_id))
         .outerjoin(Sku, and_(Sku.id == OrderItem.sku_id, Sku.product_id == Product.id))
         .where(Order.shop_id == shop_id, Order.id.in_(order_ids)).order_by(OrderItem.id))
    result = {}
    for item, title, sku, sku_title in session.execute(q):
        result.setdefault(item.order_id, []).append({"title": title, "sku_id": sku,
                                                     "sku_title": sku_title, "quantity": item.quantity})
    return result


def page(session, shop_id, start, end, tz, search="", state="all", loss_only=False, offset=0, limit=25):
    base = _base(shop_id, start, end, tz, search, state, loss_only)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    sums = base.with_only_columns(*[func.coalesce(func.sum(getattr(OrderProfit, k)), 0).label(k) for k in O.FIELDS],
                                  func.count(OrderProfit.id).label("calculated_orders"),
                                  func.count(func.distinct(OrderProfit.currency)).label("currency_count"),
                                  func.min(OrderProfit.currency).label("currency"),
                                  func.count(OrderProfit.id).filter(or_(
                                      ~func.coalesce(_final(), False),
                                      OrderProfit.inputs_snapshot["cogs_missing"].as_boolean().is_(True)
                                  )).label("uncertain_orders"),
                                  maintain_column_froms=True)
    aggregate = session.execute(sums).mappings().one()
    summary = O.compact({k: O.dec(aggregate[k]) for k in O.FIELDS})
    summary.update(calculated_orders=aggregate["calculated_orders"],
                   missing_orders=total - aggregate["calculated_orders"], currency=aggregate["currency"],
                   uncertain_orders=aggregate["uncertain_orders"])
    if aggregate["currency_count"] > 1:
        summary = None
    records = list(session.execute(base.order_by(Order.order_created_at.desc(), Order.id.desc())
                                   .offset(offset).limit(limit)))
    items = items_for(session, shop_id, [o.id for o, _ in records])
    return {"total": total, "offset": offset, "limit": limit, "summary": summary,
            "mixed_currencies": aggregate["currency_count"] > 1,
            "rows": [O.order_row(o, p, items.get(o.id, [])) for o, p in records]}


def detail(session, shop_id, order_id):
    pair = session.execute(select(Order, OrderProfit)
                           .outerjoin(OrderProfit, and_(OrderProfit.order_id == Order.id, OrderProfit.is_current.is_(True)))
                           .where(Order.shop_id == shop_id, Order.id == order_id)).first()
    if pair is None:
        raise LookupError("order not found")
    order, profit = pair
    ids = O.statement_ids(profit) if profit else []
    records = list(session.scalars(select(OrderStatementRecord)
                                  .where(OrderStatementRecord.shop_id == shop_id,
                                         OrderStatementRecord.external_order_id == order.external_order_id,
                                         OrderStatementRecord.statement_id.in_(ids))
                                  .order_by(OrderStatementRecord.statement_time, OrderStatementRecord.id))) if ids else []
    return O.breakdown(order, profit, items_for(session, shop_id, [order_id]).get(order_id, []), records)
