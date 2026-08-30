"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { toISODate } from "./format";

export type Preset = "month" | "30d" | "custom";

export interface PeriodState {
  preset: Preset;
  from?: string;
  to?: string;
  shopId?: string;
  tab: string;
  query: string; // for API: ?from=&to=&shop_id=
}

// Shop-local "today" (Asia/Jakarta) computed client-side only for presets; API defaults do the same server-side.
const jakartaToday = (): Date => {
  const s = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};

export const presetRange = (p: Preset): { from?: string; to?: string } => {
  const today = jakartaToday();
  if (p === "30d") {
    const from = new Date(today);
    from.setUTCDate(from.getUTCDate() - 29);
    return { from: toISODate(from), to: toISODate(today) };
  }
  return {};
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
