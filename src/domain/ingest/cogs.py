"""seed/cogs_seed.csv -> sku_cost_versions (upsert by sku + effective_from)."""
import csv
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Product, Sku, SkuCostVersion

log = logging.getLogger("tt.ingest.cogs")


@dataclass(frozen=True)
class CogsRow:
    product_id: str
    sku_id: str
    product_title: str
    cogs_per_unit: Decimal
    packaging_per_unit: Decimal
    inbound_logistics_per_unit: Decimal
    effective_from: date
    note: str
    pack_pairs: int | None
    status: str | None


def _dec(v: str | None) -> Decimal:
    return Decimal(v.strip()) if v and v.strip() else Decimal(0)


def parse_cogs_csv(path: str | Path) -> list[CogsRow]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r.get("sku_id"):
                continue
            out.append(CogsRow(
                product_id=r["product_id"].strip(), sku_id=r["sku_id"].strip(),
                product_title=(r.get("product_title") or "").strip(),
                cogs_per_unit=_dec(r.get("cogs_per_unit_idr")),
                packaging_per_unit=_dec(r.get("packaging_per_unit_idr")),
                inbound_logistics_per_unit=_dec(r.get("inbound_logistics_per_unit_idr")),
                effective_from=date.fromisoformat(r["effective_from"].strip()),
                note=(r.get("note") or "").strip(),
                pack_pairs=int(r["pack_pairs"]) if (r.get("pack_pairs") or "").strip() else None,
                status=(r.get("status") or "").strip() or None))
    dupes = {k for k in {(x.sku_id, x.effective_from) for x in out}
             if sum(1 for x in out if (x.sku_id, x.effective_from) == k) > 1}
    if dupes:
        raise ValueError(f"duplicate sku/effective_from rows: {sorted(dupes)}")
    return out


def load_cogs(session: Session, shop_id: int, rows: list[CogsRow], currency: str) -> dict[str, int]:
    n_ins = n_upd = n_placeholder = 0
    for r in rows:
        sku = session.scalar(select(Sku).join(Product).where(
            Product.shop_id == shop_id, Sku.external_sku_id == r.sku_id))
        if sku is None:
            log.warning("sku %s not in catalog; creating placeholder (run catalog sync first)",
                        r.sku_id)
            prod = session.scalar(select(Product).where(Product.shop_id == shop_id,
                                                        Product.external_product_id == r.product_id))
            if prod is None:
                prod = Product(shop_id=shop_id, external_product_id=r.product_id,
                               title=r.product_title, status=r.status)
                session.add(prod)
                session.flush()
            sku = Sku(product_id=prod.id, external_sku_id=r.sku_id, status=r.status)
            session.add(sku)
            session.flush()
            n_placeholder += 1
        existing = session.scalar(select(SkuCostVersion).where(
            SkuCostVersion.sku_id == sku.id, SkuCostVersion.effective_from == r.effective_from))
        notes = "; ".join(x for x in (r.note, f"pack_pairs={r.pack_pairs}" if r.pack_pairs else "")
                          if x) or None
        if existing is None:
            session.add(SkuCostVersion(
                sku_id=sku.id, effective_from=r.effective_from, cogs_per_unit=r.cogs_per_unit,
                packaging_per_unit=r.packaging_per_unit,
                inbound_logistics_per_unit=r.inbound_logistics_per_unit,
                other_variable_cost_per_unit=Decimal(0), currency=currency, notes=notes))
            n_ins += 1
        else:
            existing.cogs_per_unit = r.cogs_per_unit
            existing.packaging_per_unit = r.packaging_per_unit
            existing.inbound_logistics_per_unit = r.inbound_logistics_per_unit
            existing.currency, existing.notes = currency, notes
            n_upd += 1
    session.commit()
    return {"inserted": n_ins, "updated": n_upd, "placeholders": n_placeholder}
