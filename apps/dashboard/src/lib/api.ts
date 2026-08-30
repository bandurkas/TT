"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { TaskIn, TaskPatch, Task } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) { super(msg); this.status = status; }
}

/** FastAPI errors: {"detail": "text"} or {"detail": [{loc, msg, type}]} -> readable message. */
export const readableError = async (r: Response): Promise<string> => {
  const raw = await r.text().catch(() => "");
  try {
    const j = JSON.parse(raw) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) { const f = d[0] as { msg?: string; loc?: unknown[] }; return `${(f.loc ?? []).slice(-1).join("")}: ${f.msg ?? "invalid"}`; }
  } catch { /* not JSON */ }
  return raw || r.statusText || `HTTP ${r.status}`;
};

export const qs = (p: Record<string, string | undefined>): string => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v) u.set(k, v);
  const s = u.toString();
  return s ? `?${s}` : "";
};

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { signal, headers: { accept: "application/json" }, cache: "no-store" });
  if (!r.ok) throw new ApiError(r.status, await readableError(r));
  return r.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method, headers: { "content-type": "application/json", accept: "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(r.status, await readableError(r));
  return r.json() as Promise<T>;
}

export const createTask = (body: TaskIn, shopId?: string) => send<Task>("POST", `/api/tasks${qs({ shop_id: shopId })}`, body);
export const patchTask = (id: number, body: TaskPatch) => send<Task>("PATCH", `/api/tasks/${id}`, body);

export interface Loaded<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** Minimal SWR-style fetch keyed by path; refetches when path or `tick` changes. */
export function useApi<T>(path: string | null, tick = 0): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [n, setN] = useState(0);
  const ctrl = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!path) return;
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setLoading(true);
    setError(null);
    apiGet<T>(path, c.signal)
      .then((d) => { if (!c.signal.aborted) { setData(d); setLoading(false); } })
      .catch((e: unknown) => {
        if (c.signal.aborted) return;
        setError(e instanceof ApiError ? `${e.status} ${e.message}`.slice(0, 200) : e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
    return () => c.abort();
  }, [path, tick, n]);
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { data, error, loading, reload };
}
