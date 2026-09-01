"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { toISODate } from "./format";

export type Preset = "today" | "yesterday" | "7d" | "30d" | "month" | "prev_month" | "3m" | "custom";

export interface PeriodState {
  preset: Preset;
  from?: string;
  to?: string;
  shopId?: string;
  tab: string;
  query: string; // for API: ?from=&to=&shop_id=
}

// Shop-local "today" — the business day is the shop's, never the browser's. API defaults do the same server-side.
export const shopToday = (tz = "Asia/Jakarta"): Date => {
  const s = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};

const back = (d: Date, days: number) => { const x = new Date(d); x.setUTCDate(x.getUTCDate() - days); return x; };

export const presetRange = (p: Preset, tz?: string): { from?: string; to?: string } => {
  const today = shopToday(tz);
  const y = today.getUTCFullYear(), m = today.getUTCMonth();
  switch (p) {
    case "today": return { from: toISODate(today), to: toISODate(today) };
    case "yesterday": { const d = back(today, 1); return { from: toISODate(d), to: toISODate(d) }; }
    case "7d": return { from: toISODate(back(today, 6)), to: toISODate(today) };
    case "30d": return { from: toISODate(back(today, 29)), to: toISODate(today) };
    case "prev_month": return { from: toISODate(new Date(Date.UTC(y, m - 1, 1))), to: toISODate(new Date(Date.UTC(y, m, 0))) };
    case "3m": return { from: toISODate(new Date(Date.UTC(y, m - 2, 1))), to: toISODate(today) };
    default: return {};   // "month" keeps the server default (current month to date)
  }
};

export function usePeriod() {
  const sp = useSearchParams();
  const router = useRouter();
  const state = useMemo<PeriodState>(() => {
    const preset = (sp.get("preset") as Preset | null) ?? "month";
    let from = sp.get("from") ?? undefined, to = sp.get("to") ?? undefined;
    if (preset !== "custom") ({ from, to } = presetRange(preset));
    const shopId = sp.get("shop_id") ?? undefined;
    const u = new URLSearchParams();
    if (from) u.set("from", from);
    if (to) u.set("to", to);
    if (shopId) u.set("shop_id", shopId);
    const q = u.toString();
    return { preset, from, to, shopId, tab: sp.get("tab") ?? "products", query: q ? `?${q}` : "" };
  }, [sp]);

  const update = useCallback((patch: Partial<Record<"preset" | "from" | "to" | "tab" | "shop_id", string | undefined>>) => {
    const u = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) { if (v) u.set(k, v); else u.delete(k); }
    if (u.get("preset") !== "custom") { u.delete("from"); u.delete("to"); }
    const s = u.toString();
    router.replace(s ? `?${s}` : "/", { scroll: false });
  }, [sp, router]);

  return { state, update };
}
