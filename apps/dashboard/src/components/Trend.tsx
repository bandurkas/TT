"use client";
import { useEffect, useRef, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { dayMon, idr, int, num, pct, periodLabel, shortId } from "@/lib/format";
import type { Overview, Trends } from "@/lib/types";
import { ErrorNote, Skeleton, ZoneHeader } from "./ui";

const fmtAxis = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)}k` : String(v));

function niceStep(range: number) {
  const raw = range / 4;
  const p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const m = raw / p;
  return (m >= 5 ? 5 : m >= 2 ? 2 : 1) * p;
}

export function TrendChart({ tr }: { tr: Trends }) {
  const lang = useLang();
  const ref = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(900);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver((e) => setW(Math.max(320, Math.floor(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = 240, P = { l: 46, r: 12, t: 12, b: 24 };
  const s = tr.series;
  const n = s.length;
  const gmv = s.map((d) => num(d.gmv) ?? 0), ads = s.map((d) => num(d.ad_cost) ?? 0), cum = s.map((d) => num(d.cum_net_profit) ?? 0);
  const maxY = Math.max(1, ...gmv, ...cum), minY = Math.min(0, ...ads.map((a) => -a), ...cum);
  const step = niceStep(maxY - minY);
  const top = Math.ceil(maxY / step) * step, bot = Math.floor(minY / step) * step;
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const X = (i: number) => P.l + (n > 1 ? (iw * i) / (n - 1) : iw / 2);
  const Y = (v: number) => P.t + ih * (1 - (v - bot) / (top - bot || 1));
  const bw = Math.max(2, Math.min(10, (iw / Math.max(n, 1)) * 0.6));
  const ticks: number[] = [];
  for (let v = bot; v <= top + 1e-9; v += step) ticks.push(v);
  const labelEvery = Math.max(1, Math.ceil(n / 6));
  const evIdx = new Map<number, string[]>();
  tr.events.forEach((e) => { const i = s.findIndex((d) => d.date === e.date); if (i >= 0) evIdx.set(i, [...(evIdx.get(i) ?? []), e.type]); });
  return (
    <div ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label="GMV, ad deductions and cumulative net profit by day">
        {ticks.map((v) => <g key={v}><line x1={P.l} x2={W - P.r} y1={Y(v)} y2={Y(v)} stroke="var(--line)" /><text x={4} y={Y(v) + 4} fontSize="11" fill="var(--muted)">{fmtAxis(v)}</text></g>)}
        {s.map((d, i) => (i % labelEvery === 0 || i === n - 1) && <text key={d.date} x={X(i)} y={H - 6} fontSize="11" fill="var(--muted)" textAnchor="middle">{dayMon(d.date, lang)}</text>)}
        {gmv.map((v, i) => v > 0 && <rect key={`g${i}`} x={X(i) - bw / 2} y={Y(v)} width={bw} height={Y(0) - Y(v)} fill="var(--accent)" opacity="0.6"><title>{`${dayMon(s[i].date, lang)} GMV ${idr(v, lang)}`}</title></rect>)}
        {ads.map((v, i) => v > 0 && <rect key={`a${i}`} x={X(i) - bw / 2} y={Y(0)} width={bw} height={Y(-v) - Y(0)} fill="var(--bad)"><title>{`${dayMon(s[i].date, lang)} ad ${idr(-v, lang)}`}</title></rect>)}
        <line x1={P.l} x2={W - P.r} y1={Y(0)} y2={Y(0)} stroke="var(--muted)" strokeWidth="1" />
        {n > 0 && <path d={cum.map((v, i) => `${i ? "L" : "M"}${X(i)} ${Y(v)}`).join(" ")} fill="none" stroke="var(--ink)" strokeWidth="2" />}
        {n > 0 && <circle cx={X(n - 1)} cy={Y(cum[n - 1])} r="3.5" fill="var(--ink)" />}
        {[...evIdx.entries()].map(([i, types]) => <text key={`e${i}`} x={X(i)} y={Y(-ads[i]) + 14} fontSize="12" textAnchor="middle" fill={types.includes("ad_deduction") ? "var(--bad)" : "var(--accent)"}>◆</text>)}
      </svg>
    </div>
  );
}

export default function Trend({ tr, ov, loading, error, reload }: { tr: Trends | null; ov: Overview | null; loading: boolean; error: string | null; reload: () => void }) {
  const lang = useLang(), t = useT();
  // No client-side re-summing: totals come from overview.totals (server Decimal sums); only the last cum_net_profit is read off the series.
  const tot = ov?.totals ?? null;
  const last = tr?.series.length ? tr.series[tr.series.length - 1] : null;
  const src = tr?.gmv_sources.length ? tr.gmv_sources[tr.gmv_sources.length - 1] : null;
  const evLabel = (e: Trends["events"][number]) => e.type === "ad_deduction" ? `${t("GMV Max deduction")} ${idr(e.amount, lang)}` : e.type === "video_posted" ? `${t("new video posted")} (${shortId(e.external_video_id ?? e.video_id ?? e.label)})` : e.label;
  return (
    <section className="zone">
      <ZoneHeader id="z3" eyebrow={t("3 · Sales & profit trend")} title={tr ? `${periodLabel(tr.period.start, tr.period.end, lang)}, ${t("daily")}` : t("daily")} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !tr ? <Skeleton h={260} /> : tr && (
        <div className="trend">
          <div className="card chart">
            <div className="legend">
              <span><i style={{ background: "var(--accent)" }} />{t("GMV")}</span>
              <span><i style={{ background: "var(--bad)" }} />{t("Ad deduction")} <span className="tiny">({t("estimate")})</span></span>
              <span><i style={{ background: "var(--ink)" }} />{t("Cumulative net profit")}</span>
              <span style={{ marginLeft: "auto" }}>{t("◆ event annotation")}</span>
            </div>
            <TrendChart tr={tr} />
          </div>
          <div className="card pace">
            <div className="k lbl">{t("Period totals")} <span style={{ textTransform: "none", letterSpacing: 0 }}>· {t("Source · overview totals (API)")}</span></div>
            <div className="big">{tot ? int(tot.orders, lang) : "—"} {t("orders")}</div>
            <div style={{ color: "var(--ink2)" }}>{tot ? int(tot.settled_orders, lang) : "—"} {t("settled")} · {tot ? int(tot.provisional_orders, lang) : "—"} {t("provisional")} <span className="tiny">({t("provisional ≠ settled")})</span></div>
            <div className="small" style={{ marginTop: 6 }}>{t("GMV")} <b>{idr(tot?.gmv, lang)}</b> · {t("Ad deduction")} <b className="dn">{tot ? idr(-(num(tot.ad_cost) ?? 0), lang) : "—"}</b> · {t("Net profit")} <b className={(num(tot?.net_profit) ?? 0) < 0 ? "dn" : "up"}>{idr(tot?.net_profit, lang)}</b></div>
            {last && <div className="tiny">{t("Cumulative net profit")} · {t("last day of series")} {dayMon(last.date, lang)}: {idr(last.cum_net_profit, lang)}</div>}
            {src && (
              <div className="small" style={{ marginTop: 6 }}><span className="k lbl">{t("GMV by source")} · {dayMon(src.date, lang)}</span><br />
                {t("video")} {idr(src.gmv_video, lang)} · {t("product card")} {idr(src.gmv_product_card, lang)} · {t("live")} {idr(src.gmv_live, lang)} · GMV Max {pct(src.gmv_max_pct, lang)}
              </div>
            )}
            <div className="k lbl" style={{ marginTop: 14 }}>{t("Events")}</div>
            <div style={{ fontSize: 12, color: "var(--ink2)", display: "flex", flexDirection: "column", gap: 4, marginTop: 6, maxHeight: 140, overflow: "auto" }}>
              {tr.events.length === 0 && <span className="muted">{t("No events in this period.")}</span>}
              {tr.events.map((e, i) => <span key={i}>◆ {dayMon(e.date, lang)} — {evLabel(e)}</span>)}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
