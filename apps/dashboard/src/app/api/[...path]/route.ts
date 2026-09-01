// Dev-only mock of the FastAPI backend: `MOCK=1 npm run dev` serves apps/dashboard/fixtures/*.json.
// In production Caddy routes /api/* to api:8400, so this handler is never reached.
import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";
import { demoOrders, demoOrderPage } from "@/lib/order-mock";

export const dynamic = "force-dynamic";

const FIX = path.join(process.cwd(), "fixtures");
const FILES: Record<string, string> = {
  "dashboard/overview": "overview.json", "dashboard/trends": "trends.json", "dashboard/funnel": "funnel.json",
  "dashboard/insights": "insights.json", "analytics/products": "products.json", "analytics/videos": "videos.json",
  "analytics/campaigns": "campaigns.json", "analytics/video-products": "video-products.json", "advertising": "advertising.json", "costs": "costs.json", "analytics/creators": "creators.json",
};
const STATUSES = ["today", "in_progress", "review", "done"] as const;

type Task = Record<string, unknown> & { id: number; status: string };
type Lot = Record<string, unknown> & { id: number };
const g = globalThis as unknown as { __mockTasks?: Task[]; __mockAd?: Record<string, unknown>; __mockCosts?: Record<string, unknown> & { lots: Lot[] } };
const err = (status: number, detail: string) => NextResponse.json({ detail }, { status });
const confirmable = (message: string) => NextResponse.json({ detail: { message, confirmable: true } }, { status: 422 });
async function adv() { if (!g.__mockAd) g.__mockAd = await read("advertising.json"); return g.__mockAd!; }
async function costs() { if (!g.__mockCosts) g.__mockCosts = await read("costs.json"); return g.__mockCosts!; }
const recomputed = () => ({ versions: 6, skus_with_lots: 4, recomputed: { orders: 33, inserted: 33 } });

const off = () => NextResponse.json({ detail: "mock disabled" }, { status: 404 });
const read = async (f: string) => JSON.parse(await fs.readFile(path.join(FIX, f), "utf8"));

async function tasks(): Promise<Task[]> {
  if (!g.__mockTasks) g.__mockTasks = (await read("tasks.json")).tasks as Task[];
  return g.__mockTasks;
}
const listTasks = async () => {
  const all = await tasks();
  return { shop_id: 1, tasks: all, columns: Object.fromEntries(STATUSES.map((s) => [s, all.filter((t) => t.status === s)])) };
};

export async function GET(_req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  if (process.env.MOCK !== "1") return off();
  const key = (await ctx.params).path.join("/");
  if (key === "orders" || /^orders\/\d+$/.test(key)) {
    const params = new URL(_req.url).searchParams;
    if (params.has("shop_id") && params.get("shop_id") !== "1") return NextResponse.json({ detail: "shop not found" }, { status: 404 });
    const all = demoOrders(await read("orders.json"));
    if (key === "orders") return NextResponse.json(demoOrderPage(all, params));
    const detail = all.find(o => o.id === Number(key.split("/")[1]));
    return detail ? NextResponse.json(detail) : NextResponse.json({ detail: "order not found" }, { status: 404 });
  }
  if (key === "tasks") return NextResponse.json(await listTasks());
  if (key === "advertising") return NextResponse.json(await adv());
  if (key === "costs") return NextResponse.json(await costs());
  const f = FILES[key];
  if (!f) return NextResponse.json({ detail: "not found" }, { status: 404 });
  return NextResponse.json(await read(f));
}

export async function POST(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  if (process.env.MOCK !== "1") return off();
  const key = (await ctx.params).path.join("/");
  const body = await req.json();
  if (key === "advertising/manual") {
    const a = await adv();
    const days = a.days as Record<string, unknown>[];
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta" }).format(new Date());
    if (body.date > today) return err(422, "Report contains future dates");
    if (body.final && body.date >= today) return err(422, "A day can only be marked final after it has ended in the shop timezone");
    const prior = days.find((d) => d.date === body.date);
    if (prior && prior.source === "manual_entry" && String(prior.observed_at) > new Date().toISOString()) return err(422, "A newer or equal observation for this day already exists; enter a later one");
    // Sanity guard, mirroring src/domain/reports._check_manual_day. Only the "thinner record" half can
    // be reproduced here: the period-totals half compares against analytics_shop_daily, which the
    // fixtures have no per-day equivalent of, so that check is backend-only.
    if (prior && !body.confirm) {
      const orders = Number(body.sku_orders ?? 0), gross = Number(body.gross_revenue ?? 0);
      const wasCost = Number(prior.cost), wasOrders = Number(prior.sku_orders), wasGross = Number(prior.gross_revenue);
      if (wasCost > 0 && Number(body.cost) < wasCost * 0.5)
        return confirmable(`Cost ${body.cost} is far below the ${wasCost} already recorded for ${body.date}, and ad spend does not fall within a day. This would overwrite a fuller record; check the figure, or confirm to replace it.`);
      const emptied = [wasOrders && !orders ? "SKU orders" : "", wasGross && !gross ? "gross revenue" : ""].filter(Boolean);
      if (emptied.length)
        return confirmable(`This would blank ${emptied.join(" and ")} already recorded for ${body.date}. Enter the full figures, or confirm to replace the record as entered.`);
    }
    const day = { date: body.date, cost: String(body.cost), partial: !body.final, sku_orders: body.sku_orders ?? 0, gross_revenue: String(body.gross_revenue ?? 0), source: "manual_entry", observed_at: new Date().toISOString(), note: body.note || null };
    if (prior) Object.assign(prior, day); else { days.push(day); days.sort((x, y) => String(x.date).localeCompare(String(y.date))); }
    a.manual_days = days.filter((d) => d.source === "manual_entry").length;
    return NextResponse.json({ report_id: 900 + days.length, partial: day.partial, recomputed: { orders: 33, inserted: 33 }, day }, { status: 201 });
  }
  if (key === "costs/default") {
    const c = await costs();
    c.default_cogs_per_unit = body.default_cogs_per_unit === null || body.default_cogs_per_unit === undefined ? null : String(body.default_cogs_per_unit);
    return NextResponse.json({ default_cogs_per_unit: c.default_cogs_per_unit, ...recomputed() });
  }
  if (key === "costs/lots") {
    const c = await costs();
    if ((body.scope === "product" && !body.product_id) || (body.scope === "sku" && !body.sku_id)) return err(422, "product_id / sku_id required for that scope");
    const lot: Lot = { id: Math.max(0, ...c.lots.map((l) => l.id)) + 1, scope: body.scope ?? "all", product_id: body.scope === "product" ? body.product_id : null, sku_id: body.scope === "sku" ? body.sku_id : null, received_on: body.received_on, unit_cost: String(body.unit_cost), quantity: body.quantity ?? null, currency: "IDR", note: body.note ?? null, active: true };
    c.lots.push(lot);
    return NextResponse.json({ lot_id: lot.id, ...recomputed() }, { status: 201 });
  }
  if (key !== "tasks") return NextResponse.json({ detail: "not found" }, { status: 404 });
  const all = await tasks();
  const now = new Date().toISOString();
  const { source, ...evidence } = (body.evidence ?? {}) as Record<string, unknown>;
  void source;
  const t: Task = {
    id: Math.max(0, ...all.map((x) => x.id)) + 1, shop_id: 1, title: body.title, detail: body.detail ?? null,
    team: body.team, priority: body.priority ?? "P2", status: body.status ?? "today", owner: body.owner ?? null,
    deadline: body.deadline ?? null, impact_note: body.impact_note ?? null, source: body.source ?? "manual",
    evidence, result_note: null, done_at: null, created_at: now, updated_at: now,
  };
  all.unshift(t);
  return NextResponse.json(t, { status: 201 });
}

export async function PATCH(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  if (process.env.MOCK !== "1") return off();
  const p = (await ctx.params).path;
  if (p[0] === "costs" && p[1] === "lots" && p.length === 3) {
    const c = await costs();
    const lot = c.lots.find((l) => l.id === Number(p[2]));
    if (!lot) return err(404, "lot not found");
    const b = await req.json();
    if ("quantity" in b) lot.quantity = b.quantity || null;
    for (const k of ["received_on", "unit_cost", "note", "active"]) if (k in b) lot[k] = k === "unit_cost" ? String(b[k]) : b[k];
    return NextResponse.json({ lot_id: lot.id, ...recomputed() });
  }
  if (p[0] !== "tasks" || p.length !== 2) return NextResponse.json({ detail: "not found" }, { status: 404 });
  const all = await tasks();
  const t = all.find((x) => x.id === Number(p[1]));
  if (!t) return NextResponse.json({ detail: "task not found" }, { status: 404 });
  const body = await req.json();
  Object.assign(t, body, { updated_at: new Date().toISOString() });
  if (body.status === "done" && !t.done_at) t.done_at = new Date().toISOString();
  else if (body.status && body.status !== "done") t.done_at = null;
  return NextResponse.json(t);
}
