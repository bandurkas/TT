// Error shapes the FastAPI backend returns, kept free of React so it can be unit-tested directly.
export class ApiError extends Error {
  status: number;
  /** The server refused a plausible-but-suspicious write that the operator may re-send with confirm. */
  confirmable: boolean;
  constructor(status: number, msg: string, confirmable = false) { super(msg); this.status = status; this.confirmable = confirmable; }
}

export interface ErrorDetail { message: string; confirmable: boolean }

/** FastAPI errors: {"detail": "text"}, {"detail": [{loc, msg, type}]}, or {"detail": {message, confirmable}}. */
export const readableError = async (r: Response): Promise<ErrorDetail> => {
  const plain = (message: string): ErrorDetail => ({ message, confirmable: false });
  const raw = await r.text().catch(() => "");
  try {
    const j = JSON.parse(raw) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === "string") return plain(d);
    if (Array.isArray(d) && d.length) { const f = d[0] as { msg?: string; loc?: unknown[] }; return plain(`${(f.loc ?? []).slice(-1).join("")}: ${f.msg ?? "invalid"}`); }
    if (d && typeof d === "object") {
      const o = d as { message?: string; confirmable?: boolean };
      if (o.message) return { message: o.message, confirmable: o.confirmable === true };
    }
  } catch { /* not JSON */ }
  return plain(raw || r.statusText || `HTTP ${r.status}`);
};

export const fail = async (r: Response): Promise<never> => {
  const { message, confirmable } = await readableError(r);
  throw new ApiError(r.status, message, confirmable);
};
