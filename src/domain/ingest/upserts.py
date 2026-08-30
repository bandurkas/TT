"""Idempotent INSERT ... ON CONFLICT DO UPDATE helpers (Postgres)."""
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.orm import Session

from src.db.models import Order, Product, Shop, Sku, Video


def build_upsert(model: type, rows: Sequence[dict], conflict_cols: Sequence[str],
                 exclude_update: Iterable[str] = ()) -> Insert | None:
    rows = dedupe_rows([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
                       conflict_cols)
    if not rows:
        return None
    stmt = insert(model).values(rows)
    skip = set(conflict_cols) | set(exclude_update) | {"id", "created_at"}
    cols = [c for c in rows[0] if c not in skip]
    if not cols:
        return stmt.on_conflict_do_nothing(index_elements=list(conflict_cols))
    return stmt.on_conflict_do_update(index_elements=list(conflict_cols),
                                      set_={c: getattr(stmt.excluded, c) for c in cols})


def dedupe_rows(rows: Sequence[dict], conflict_cols: Sequence[str]) -> list[dict]:
    """One row per conflict key, last wins (PG rejects a second hit on the same key in one INSERT)."""
    by_key: dict[tuple, dict] = {}
    for r in rows:
        by_key[tuple(r.get(c) for c in conflict_cols)] = r
    return list(by_key.values())


def upsert(session: Session, model: type, rows: Sequence[dict], conflict_cols: Sequence[str],
           exclude_update: Iterable[str] = (), returning: str | None = None) -> list[Any]:
    """Returns list of `returning` column values (rows order not guaranteed) or []."""
    stmt = build_upsert(model, rows, conflict_cols, exclude_update)
    if stmt is None:
        return []
    if returning:
        stmt = stmt.returning(getattr(model, returning))
        return list(session.execute(stmt).scalars())
    session.execute(stmt)
    return []


def upsert_map(session: Session, model: type, rows: Sequence[dict], conflict_cols: Sequence[str],
               key: str, exclude_update: Iterable[str] = ()) -> dict[str, int]:
    """Upsert and return {external key -> id}."""
    stmt = build_upsert(model, rows, conflict_cols, exclude_update)
    if stmt is None:
        return {}
    stmt = stmt.returning(getattr(model, key), model.id)
    return {str(k): i for k, i in session.execute(stmt)}


# --- lookups -----------------------------------------------------------------------
def shop_id_by_external(session: Session, external_shop_id: str) -> int | None:
    return session.scalar(select(Shop.id).where(Shop.platform == "tiktok_shop",
                                                Shop.external_shop_id == external_shop_id))


def product_ids(session: Session, shop_id: int) -> dict[str, int]:
    return dict(session.execute(select(Product.external_product_id, Product.id)
                                .where(Product.shop_id == shop_id)).all())


def sku_ids(session: Session, shop_id: int) -> dict[str, tuple[int, int]]:
    """external_sku_id -> (sku.id, product.id)."""
    q = (select(Sku.external_sku_id, Sku.id, Sku.product_id).join(Product)
         .where(Product.shop_id == shop_id))
    return {e: (s, p) for e, s, p in session.execute(q)}


def order_ids(session: Session, shop_id: int, external_ids: Sequence[str]) -> dict[str, int]:
    if not external_ids:
        return {}
    q = select(Order.external_order_id, Order.id).where(Order.shop_id == shop_id,
                                                        Order.external_order_id.in_(external_ids))
    return dict(session.execute(q).all())


def video_ids(session: Session, shop_id: int) -> dict[str, int]:
    return dict(session.execute(select(Video.external_video_id, Video.id)
                                .where(Video.shop_id == shop_id)).all())
