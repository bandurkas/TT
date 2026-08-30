// Deterministic, explicitly labelled demo only. All money sums use integer micro-units.
import type { OrderDetail, OrderPage } from "./orders";

const SCALE = 1_000_000n;
const units = (s: string) => {
  const [whole, fraction = ""] = s.replace(/^-/, "").split(".");
  return (BigInt(whole) * SCALE + BigInt(fraction.padEnd(6, "0"))) * (s.startsWith("-") ? -1n : 1n);
};
const decimal = (n: bigint) => `${n < 0 ? "-" : ""}${(n < 0 ? -n : n) / SCALE}.${((n < 0 ? -n : n) % SCALE).toString().padStart(6, "0")}`;
const share = (n: bigint, base: bigint): string | null => {
  if (base <= 0n) return null;
  const abs = (n < 0n ? -n : n) * SCALE, q = abs / base, r = abs % base;
  const rounded = q + (r * 2n > base || (r * 2n === base && q % 2n !== 0n) ? 1n : 0n);
  return decimal(n < 0n ? -rounded : rounded);
};

export function demoOrders(templates: OrderDetail[]): OrderDetail[] {
  return Array.from({ length: 34 }, (_, n) => ({
    ...structuredClone(templates[n % templates.length]), id: n + 1,
    external_order_id: `DEMO-${String(n + 1).padStart(6, "0")}`,
    created_at: `2026-08-${String(n % 30 + 1).padStart(2, "0")}T10:00:00+07:00`,
    demo: true, timezone: "Asia/Jakarta",
  }));
}

export function demoOrderPage(all: OrderDetail[], params: URLSearchParams): OrderPage {
  const start = params.get("from") ?? "2026-08-01", end = params.get("to") ?? "2026-08-31";
  const search = (params.get("search") ?? "").toLocaleLowerCase(), state = params.get("state") ?? "all";
  const filtered = all.filter(o => {
    const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta" }).format(new Date(o.created_at!));
    return day >= start && day <= end && (state === "all" || o.state === state) &&
      (params.get("loss_only") !== "true" || !!o.amounts?.net_profit?.startsWith("-")) &&
      (!search || o.external_order_id.toLocaleLowerCase().includes(search) || o.items.some(i => i.title?.toLocaleLowerCase().includes(search)));
  }).sort((a, b) => b.created_at!.localeCompare(a.created_at!) || b.id - a.id);
  const offset = Math.max(0, Number(params.get("offset")) || 0), limit = Math.min(100, Math.max(1, Number(params.get("limit")) || 25));
  const fields = ["revenue_base", "fees", "costs", "refunds", "other_effect", "ad_cost", "net_profit"] as const;
  const sums = Object.fromEntries(fields.map(k => [k, filtered.reduce((n, o) => n + units(o.amounts?.[k] ?? "0"), 0n)])) as Record<typeof fields[number], bigint>;
  const amounts = Object.fromEntries(fields.map(k => [k, decimal(sums[k])])) as Record<typeof fields[number], string>;
  const calculated = filtered.filter(o => o.amounts).length;
  return { demo: true, shop: { id: 1, name: "Demo", currency: "IDR", timezone: "Asia/Jakarta" },
    period: { start, end }, compare: { start, end }, generated_at: "2026-08-30T12:00:00Z",
    total: filtered.length, offset, limit, mixed_currencies: false,
    summary: { ...amounts, shares: Object.fromEntries(fields.map(k => [k, share(sums[k], sums.revenue_base)])),
      profit_share: share(sums.net_profit, sums.revenue_base), currency: "IDR", calculated_orders: calculated, missing_orders: filtered.length - calculated,
      uncertain_orders: filtered.filter(o => o.amounts && (o.state !== "final" || o.warnings.includes("cogs_missing"))).length },
    rows: filtered.slice(offset, offset + limit),
  };
}
