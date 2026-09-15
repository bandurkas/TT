import type { ProductRow } from "./types";

// Local, not lib/format's num(): that module has a runtime import chain the plain-Node test
// loader for this file (tests/productsSplit.test.mjs) can't resolve from a data: URI. Mirrors
// format.ts's num() exactly, including returning null (not 0) for an unmeasured value.
const num = (v: string | number | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};

export type ProductSortKey = "net_profit" | "gmv" | "net_margin" | "cvr" | "ctr" | "units";

export const PRODUCT_SORT_KEYS: { key: ProductSortKey; label: string }[] = [
  { key: "net_profit", label: "Net profit" },
  { key: "gmv", label: "GMV" },
  { key: "net_margin", label: "Margin" },
  { key: "cvr", label: "CVR" },
  { key: "ctr", label: "CTR" },
  { key: "units", label: "Units" },
];

/** Descending by key; unmeasured (null) rows sink to the bottom, not treated as worse-than-real. */
export function sortProducts(rows: ProductRow[], key: ProductSortKey): ProductRow[] {
  return [...rows].sort((a, b) => {
    const av = num(a[key]), bv = num(b[key]);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return bv - av;
  });
}

export function filterProducts(rows: ProductRow[], query: string): ProductRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => r.title.toLowerCase().includes(q));
}

/** null = not computed (no tone); ≥15% good, 0–15% warn, negative bad. */
export function marginTone(netMargin: number | null): "up" | "wn" | "dn" | "" {
  if (netMargin === null) return "";
  if (netMargin < 0) return "dn";
  if (netMargin < 0.15) return "wn";
  return "up";
}
