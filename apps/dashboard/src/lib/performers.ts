import type { ProductRow, VideoCard } from "./types";

// Local, not lib/format's num(): that module has a runtime import chain the plain-Node test
// loader for this file (tests/performers.test.mjs) can't resolve from a data: URI. Mirrors
// format.ts's num() exactly, including returning null (not 0) for an unmeasured value.
const num = (v: string | number | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};

// "Best/worst" reuses the status/classification the backend already computed
// (product_rows()/video_cards()) — no new scoring logic, just a presentation cut of it.
const BEST_PRODUCT_STATUSES = new Set(["SCALE", "HEALTHY"]);
const WORST_PRODUCT_STATUSES = new Set(["REDUCE", "INVESTIGATE"]);
const BEST_VIDEO_CLASSES = new Set(["WINNER", "PROMISING"]);
// LOW_ATTENTION/NEUTRAL/WATCH/INSUFFICIENT_DATA are not "worst" — they're unproven or
// inconclusive, not a measured loss, so they're excluded rather than lumped in here.
const WORST_VIDEO_CLASSES = new Set(["LOSER", "FATIGUING", "TRAFFIC_NO_SALES"]);

// SCALE/HEALTHY require profit_known (product_status() returns INVESTIGATE first otherwise),
// so net_profit is never null here in practice — ?? 0 is just a type-safe fallback.
export function bestProducts(rows: ProductRow[], n = 5): ProductRow[] {
  return rows.filter((r) => BEST_PRODUCT_STATUSES.has(r.status))
    .sort((a, b) => (num(b.net_profit) ?? 0) - (num(a.net_profit) ?? 0)).slice(0, n);
}

// Unlike Best, Worst legitimately includes INVESTIGATE rows whose profit is unmeasured
// (product_status(): "profit inputs missing or preliminary") — net_profit is null there, not a
// known 0. Treating that as a known break-even would misrank it against a real REDUCE loss, so
// unmeasured rows sort first: unverified is itself the reason they need attention.
export function worstProducts(rows: ProductRow[], n = 5): ProductRow[] {
  return rows.filter((r) => WORST_PRODUCT_STATUSES.has(r.status))
    .sort((a, b) => {
      const an = num(a.net_profit), bn = num(b.net_profit);
      if (an === null || bn === null) return (an === null ? -1 : 0) + (bn === null ? 1 : 0);
      return an - bn;
    }).slice(0, n);
}

// video_cards() already returns cards sorted best-to-worst by classification then -gmv
// (compute.py): WINNER before PROMISING, so filtering + taking the front is already "best
// first" — no re-sorting needed here.
export function bestVideos(cards: VideoCard[], n = 5): VideoCard[] {
  return cards.filter((c) => BEST_VIDEO_CLASSES.has(c.classification)).slice(0, n);
}

// Same source order, but ascending severity (TRAFFIC_NO_SALES, then FATIGUING, then LOSER) —
// the front of the filtered list is the *mildest* of the worst, not the worst. Take the tail
// and reverse it so the most severe (LOSER) leads, instead of silently dropping it past `n`.
export function worstVideos(cards: VideoCard[], n = 5): VideoCard[] {
  return cards.filter((c) => WORST_VIDEO_CLASSES.has(c.classification)).slice(-n).reverse();
}
