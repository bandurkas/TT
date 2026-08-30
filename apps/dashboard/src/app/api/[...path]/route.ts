// Dev-only mock of the FastAPI backend: `MOCK=1 npm run dev` serves apps/dashboard/fixtures/*.json.
// In production Caddy routes /api/* to api:8400, so this handler is never reached.
import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

const FIX = path.join(process.cwd(), "fixtures");
const FILES: Record<string, string> = {
  "dashboard/overview": "overview.json", "dashboard/trends": "trends.json", "dashboard/funnel": "funnel.json",
  "dashboard/insights": "insights.json", "analytics/products": "products.json", "analytics/videos": "videos.json",
  "analytics/campaigns": "campaigns.json", "analytics/creators": "creators.json",
};
const STATUSES = ["today", "in_progress", "review", "done"] as const;

type Task = Record<string, unknown> & { id: number; status: string };
const g = globalThis as unknown as { __mockTasks?: Task[] };

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
  if (key === "tasks") return NextResponse.json(await listTasks());
  const f = FILES[key];
  if (!f) return NextResponse.json({ detail: "not found" }, { status: 404 });
  return NextResponse.json(await read(f));
}

export async function POST(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  if (process.env.MOCK !== "1") return off();
  if ((await ctx.params).path.join("/") !== "tasks") return NextResponse.json({ detail: "not found" }, { status: 404 });
  const body = await req.json();
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
