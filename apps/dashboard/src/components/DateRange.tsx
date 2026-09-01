"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { MONTHS_FULL, MONTHS_SHORT, parseDate, toISODate } from "@/lib/format";
import { shopToday, type Preset } from "@/lib/period";

const DOW_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DOW_RU = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const PRESETS: { key: Preset; label: [string, string] }[] = [
  { key: "today", label: ["Сегодня", "Today"] },
  { key: "yesterday", label: ["Вчера", "Yesterday"] },
  { key: "7d", label: ["Последние 7 дней", "Last 7 days"] },
  { key: "30d", label: ["Последние 30 дней", "Last 30 days"] },
  { key: "month", label: ["Этот месяц", "This month"] },
  { key: "prev_month", label: ["Прошлый месяц", "Last month"] },
  { key: "3m", label: ["Последние 3 месяца", "Last 3 months"] },
];

const addMonths = (d: Date, n: number) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1));
const startOfMonth = (d: Date) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));

/** 6×7 grid for one month, padded with the neighbouring months' days. */
function grid(month: Date, weekStartsMonday: boolean): Date[] {
  const first = startOfMonth(month);
  const shift = weekStartsMonday ? (first.getUTCDay() + 6) % 7 : first.getUTCDay();
  const start = new Date(first);
  start.setUTCDate(start.getUTCDate() - shift);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i);
    return d;
  });
}

interface Props {
  preset: Preset;
  from?: string;              // effective range, as the API resolved it
  to?: string;
  timezone?: string;
  onPick: (p: { preset: Preset; from?: string; to?: string }) => void;
}

export default function DateRange({ preset, from, to, timezone, onPick }: Props) {
  const lang = useLang(), t = useT();
  const ru = lang === "ru";
  const today = useMemo(() => shopToday(timezone), [timezone]);
  const [open, setOpen] = useState(false);
  // open so the range's end month sits on the RIGHT: a range inside the current month would
  // otherwise show the current month plus a fully-disabled future one, with nothing to click.
  const initialAnchor = useCallback(() => {
    const end = startOfMonth(to ? parseDate(to) : today);
    const start = from ? startOfMonth(parseDate(from)) : end;
    return start.getTime() === end.getTime() ? addMonths(end, -1) : start;
  }, [from, to, today]);
  const [anchor, setAnchor] = useState<Date>(initialAnchor);
  const [pending, setPending] = useState<string | null>(null);   // first click of a range
  const [hover, setHover] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setAnchor(initialAnchor());
    setPending(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDown); };
  }, [open, initialAnchor]);

  const iso = { today: toISODate(today), from, to };
  const label = from && to
    ? `${fmt(from, lang)} – ${fmt(to, lang)}`
    : t("This month");

  const pickDay = (day: string) => {
    if (!pending) { setPending(day); setHover(null); return; }
    const [a, b] = pending <= day ? [pending, day] : [day, pending];
    onPick({ preset: "custom", from: a, to: b });
    setPending(null);
    setOpen(false);
  };

  // the range being previewed: committed, or the one the cursor is drawing
  const range = pending
    ? (hover && hover < pending ? [hover, pending] : [pending, hover ?? pending])
    : [iso.from ?? "", iso.to ?? ""];

  const months = [anchor, addMonths(anchor, 1)];
  const canForward = toISODate(addMonths(anchor, 1)) < toISODate(startOfMonth(today));

  return (
    <div className="dr" ref={box}>
      <button className="dr-trigger" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="lab">{t("Period")}</span><b>{label}</b>
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">
          <rect x="2" y="3" width="12" height="11" rx="2" /><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" />
        </svg>
      </button>
      {open && (
        <div className="dr-pop" role="dialog" aria-label={t("Period")}>
          <div className="dr-presets">
            {PRESETS.map((p) => (
              <button key={p.key} className={preset === p.key ? "on" : ""}
                onClick={() => { onPick({ preset: p.key, from: undefined, to: undefined }); setOpen(false); }}>
                {p.label[ru ? 0 : 1]}
              </button>
            ))}
          </div>
          <div className="dr-cal">
            <div className="dr-nav">
              <button aria-label={t("Previous year")} onClick={() => setAnchor(addMonths(anchor, -12))}>«</button>
              <button aria-label={t("Previous month")} onClick={() => setAnchor(addMonths(anchor, -1))}>‹</button>
              {months.map((m, i) => (
                <span key={i} className="dr-mon">{MONTHS_FULL[ru ? "ru" : "en"][m.getUTCMonth()]} {m.getUTCFullYear()}</span>
              ))}
              <button aria-label={t("Next month")} disabled={!canForward} onClick={() => setAnchor(addMonths(anchor, 1))}>›</button>
              <button aria-label={t("Next year")} disabled={!canForward} onClick={() => setAnchor(addMonths(anchor, 12))}>»</button>
            </div>
            <div className="dr-months">
              {months.map((m, mi) => (
                <table className="dr-grid" key={mi}>
                  <thead><tr>{(ru ? [...DOW_RU.slice(1), DOW_RU[0]] : DOW_EN).map((d) => <th key={d} scope="col">{d}</th>)}</tr></thead>
                  <tbody>
                    {Array.from({ length: 6 }, (_, w) => (
                      <tr key={w}>
                        {grid(m, ru).slice(w * 7, w * 7 + 7).map((d) => {
                          const s = toISODate(d);
                          const outside = d.getUTCMonth() !== m.getUTCMonth();
                          const future = s > iso.today;
                          const inRange = !!range[0] && !!range[1] && s >= range[0] && s <= range[1];
                          const edge = s === range[0] || s === range[1];
                          const cls = [outside ? "out" : "", future ? "off" : "", inRange ? "in" : "", edge ? "edge" : "", s === iso.today ? "now" : ""].filter(Boolean).join(" ");
                          return (
                            <td key={s} className={cls}>
                              <button disabled={future || outside} aria-label={s} aria-current={s === iso.today ? "date" : undefined}
                                onMouseEnter={() => pending && setHover(s)} onClick={() => pickDay(s)}>
                                {d.getUTCDate()}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ))}
            </div>
            <div className="dr-foot">
              <span className="tiny">{tzLabel(timezone)}</span>
              <span className="sp" />
              <span className="tiny">{pending ? `${t("Start")}: ${fmt(pending, lang)} · ${t("pick the end date")}` : from && to ? `${fmt(from, lang)} – ${fmt(to, lang)}` : ""}</span>
              {pending && <button className="btn xs" onClick={() => setPending(null)}>{t("Cancel")}</button>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const fmt = (s: string, lang: "ru" | "en") => {
  const d = parseDate(s);
  return `${d.getUTCDate()} ${MONTHS_SHORT[lang][d.getUTCMonth()]} ${d.getUTCFullYear()}`;
};

/** "(UTC+07:00) Asia/Jakarta" — the business day is the shop's, never the browser's. */
function tzLabel(tz?: string): string {
  if (!tz) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "longOffset" }).formatToParts(new Date());
    const off = parts.find((p) => p.type === "timeZoneName")?.value ?? "";
    return `(${off.replace(/^GMT/, "UTC") || "UTC+00:00"}) ${tz}`;
  } catch { return tz; }
}
