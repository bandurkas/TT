import type { Card } from "./types";

// Presentation only: amounts and deltas are supplied by the deterministic API.
export function kpiChange(c: Pick<Card, "key" | "kind" | "value" | "prev" | "change_abs" | "change_pct">) {
  const raw = c.kind === "pct" ? c.change_abs : c.change_pct;
  if (c.value === null || c.prev === null || raw === null || raw === "" || !Number.isFinite(Number(raw))) return null;
  const direction = Number(c.change_abs ?? raw);
  const neutral = c.key === "ad_spend" || !Number.isFinite(direction) || direction === 0;
  const improved = c.key === "refund_rate" ? direction < 0 : direction > 0;
  return { raw, points: c.kind === "pct", direction, tone: neutral ? "muted" : improved ? "up" : "dn" };
}
