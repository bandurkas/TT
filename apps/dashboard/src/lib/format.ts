import type { Dec } from "./types";
import type { Lang } from "./i18n";

const MINUS = "−";

export const num = (v: Dec | number | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};

const grp = (n: number, lang: Lang, frac = 0) =>
  n.toLocaleString(lang === "ru" ? "ru-RU" : "en-US", { minimumFractionDigits: frac, maximumFractionDigits: frac });

/** IDR like the mock: Rp 1.87m / Rp 254k / Rp 25,000. Sign uses a typographic minus. */
export const idr = (v: Dec | number | null | undefined, lang: Lang = "en", opts: { sign?: boolean } = {}): string => {
  const n = num(v);
  if (n === null) return "—";
  const a = Math.abs(n);
  let body: string;
  if (a >= 1_000_000) body = `Rp ${grp(a / 1_000_000, lang, 2)}m`;
  else if (a >= 100_000) body = `Rp ${grp(Math.round(a / 1000), lang)}k`;
  else body = `Rp ${grp(Math.round(a), lang)}`;
  if (n < 0) return MINUS + body;
  return opts.sign && n > 0 ? "+" + body : body;
};

export const pct = (v: Dec | number | null | undefined, lang: Lang = "en", opts: { sign?: boolean; frac?: number } = {}): string => {
  const n = num(v);
  if (n === null) return "—";
  const p = n * 100;
  const frac = opts.frac ?? (Math.abs(p) >= 10 ? 1 : 2);
  const s = grp(Math.abs(p), lang, frac) + "%";
  if (p < 0) return MINUS + s;
  return opts.sign && p > 0 ? "+" + s : s;
};

export const ratio = (v: Dec | number | null | undefined, lang: Lang = "en"): string => {
  const n = num(v);
  return n === null ? "—" : grp(n, lang, 2);
};

export const int = (v: Dec | number | null | undefined, lang: Lang = "en"): string => {
  const n = num(v);
  return n === null ? "—" : grp(Math.round(n), lang);
};

const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_RU = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
export const MONTHS_SHORT = { en: MONTHS_EN, ru: MONTHS_RU };
const MONTHS_EN_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MONTHS_RU_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
export const MONTHS_FULL = { en: MONTHS_EN_FULL, ru: MONTHS_RU_FULL };

export const parseDate = (s: string): Date => {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};

export const dayMon = (s: string | null | undefined, lang: Lang = "en"): string => {
  if (!s) return "—";
  const d = parseDate(s);
  return `${d.getUTCDate()} ${(lang === "ru" ? MONTHS_RU : MONTHS_EN)[d.getUTCMonth()]}`;
};

export const periodLabel = (start: string, end: string, lang: Lang = "en"): string => {
  const a = parseDate(start), b = parseDate(end);
  const sameMonth = a.getUTCFullYear() === b.getUTCFullYear() && a.getUTCMonth() === b.getUTCMonth();
  const last = new Date(Date.UTC(b.getUTCFullYear(), b.getUTCMonth() + 1, 0)).getUTCDate();
  if (sameMonth && a.getUTCDate() === 1 && b.getUTCDate() === last) {
    return `${(lang === "ru" ? MONTHS_RU_FULL : MONTHS_EN_FULL)[a.getUTCMonth()]} ${a.getUTCFullYear()}`;
  }
  return `${dayMon(start, lang)} – ${dayMon(end, lang)}`;
};

export const dateTime = (iso: string | null | undefined, lang: Lang = "en", tz?: string): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const f = new Intl.DateTimeFormat(lang === "ru" ? "ru-RU" : "en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz || "Asia/Jakarta",
  });
  return f.format(d);
};

export const shortId = (id: string | number | null | undefined): string => {
  if (id === null || id === undefined) return "—";
  const s = String(id);
  return s.length > 10 ? `${s.slice(0, 4)}…${s.slice(-4)}` : s;
};

export const toISODate = (d: Date): string => d.toISOString().slice(0, 10);
