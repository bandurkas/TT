"use client";
import { useEffect, useRef, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { dayMon, idr, int, num, pct, ratio, shortId } from "@/lib/format";
import type { VPHistory, VPHistProduct, VPHistVideo, LiftVerdict, VideoPhase } from "@/lib/types";
import { Pill } from "./ui";

const fmtAxis = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)}k` : String(v));

function useWidth<T extends HTMLElement>(init = 900) {
  const ref = useRef<T>(null);
  const [W, setW] = useState(init);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver((e) => setW(Math.max(280, Math.floor(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, W };
}

function ProductTimeline({ p }: { p: VPHistProduct }) {
  const lang = useLang(), t = useT();
  const { ref, W } = useWidth<HTMLDivElement>();
  const H = 200, P = { l: 46, r: 36, t: 16, b: 24 };
  const n = p.days.length;
  const vg = p.days.map((d) => num(d.video_gmv) ?? 0), ng = p.days.map((d) => num(d.non_video_gmv) ?? 0), ord = p.days.map((d) => d.orders);
  const maxG = Math.max(1, ...vg.map((v, i) => v + ng[i])), maxO = Math.max(1, ...ord);
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const X = (i: number) => P.l + (n > 1 ? (iw * i) / (n - 1) : iw / 2);
  const Y = (v: number) => P.t + ih * (1 - v / maxG), YO = (v: number) => P.t + ih * (1 - v / maxO);
  const bw = Math.max(2, Math.min(12, (iw / Math.max(n, 1)) * 0.6));
  const labelEvery = Math.max(1, Math.ceil(n / 6));
  const idx = new Map(p.days.map((d, i) => [d.date, i]));
  return (
    <div ref={ref}>
      <div className="legend"><span><i style={{ background: "var(--accent)" }} />{t("Video GMV")}</span><span><i style={{ background: "var(--gray-soft)", border: "1px solid var(--line)" }} />{t("non-video GMV")}</span><span><i style={{ background: "var(--ink)" }} />{t("Orders")}</span><span style={{ marginLeft: "auto" }}>◆ {t("video publish")}</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${p.title}: video vs non-video GMV by day`}>
        {[0, 0.5, 1].map((f) => <g key={f}><line x1={P.l} x2={W - P.r} y1={Y(maxG * f)} y2={Y(maxG * f)} stroke="var(--line)" /><text x={4} y={Y(maxG * f) + 4} fontSize="11" fill="var(--muted)">{fmtAxis(maxG * f)}</text><text x={W - P.r + 4} y={YO(maxO * f) + 4} fontSize="11" fill="var(--ink2)">{Math.round(maxO * f)}</text></g>)}
        {p.days.map((d, i) => (i % labelEvery === 0 || i === n - 1) && <text key={d.date} x={X(i)} y={H - 6} fontSize="11" fill="var(--muted)" textAnchor="middle">{dayMon(d.date, lang)}</text>)}
        {p.days.map((d, i) => <g key={d.date}>
          {ng[i] > 0 && <rect x={X(i) - bw / 2} y={Y(ng[i])} width={bw} height={Y(0) - Y(ng[i])} fill="var(--gray-soft)" stroke="var(--line)"><title>{`${dayMon(d.date, lang)} ${t("non-video GMV")} ${idr(ng[i], lang)}`}</title></rect>}
          {vg[i] > 0 && <rect x={X(i) - bw / 2} y={Y(ng[i] + vg[i])} width={bw} height={Y(0) - Y(vg[i])} fill="var(--accent)" opacity="0.8"><title>{`${dayMon(d.date, lang)} ${t("Video GMV")} ${idr(vg[i], lang)}`}</title></rect>}
        </g>)}
        {n > 0 && <path d={ord.map((v, i) => `${i ? "L" : "M"}${X(i)} ${YO(v)}`).join(" ")} fill="none" stroke="var(--ink)" strokeWidth="1.5" opacity="0.8" />}
        {p.events.map((e, k) => { const i = idx.get(e.date); if (i === undefined) return null; return <text key={k} x={X(i)} y={P.t + 2 + (k % 2) * 12} fontSize="12" textAnchor="middle" fill="var(--warn)"><title>{`${dayMon(e.date, lang)} ${t("published")}: ${e.external_video_id ?? e.video_id}`}</title>◆</text>; })}
      </svg>
    </div>
  );
}

const VERDICT: Record<LiftVerdict, "good" | "bad" | "gray"> = { positive: "good", negative: "bad", neutral: "gray", insufficient: "gray", pending: "gray" };
const PHASE: Record<VideoPhase, "good" | "info" | "warn" | "gray"> = { rising: "good", steady: "info", fading: "warn", insufficient: "gray" };

function Lifts({ p }: { p: VPHistProduct }) {
  const lang = useLang(), t = useT();
  if (!p.lifts.length) return <div className="tiny">{t("No history for this period.")}</div>;
  return (
    <div className="list" style={{ padding: 0 }}>
      {p.lifts.map((l) => {
        const tone = VERDICT[l.verdict];
        const lift = num(l.lift_pct);
        return (
          <div className="item" key={l.video_id} style={{ gridTemplateColumns: "auto 1fr auto" }}>
            <Pill tone={tone}>{t(l.verdict)}</Pill>
            <div>
              <div className={`t ${tone === "good" ? "up" : tone === "bad" ? "dn" : ""}`}>Video {shortId(l.external_video_id ?? l.video_id)} · {t("published")} {dayMon(l.published, lang)}: {t("orders/day")} {ratio(l.before.orders_per_day, lang)} → {ratio(l.after.orders_per_day, lang)}{lift !== null && `, ${pct(lift, lang, { sign: true, frac: 0 })}`}</div>
              <div className="s">{t("before")} {int(l.before.orders, lang)} {t("orders")} / {idr(l.before.gmv, lang)} · {t("after")} {int(l.after.orders, lang)} {t("orders")} / {idr(l.after.gmv, lang)} ({t("Video GMV")} {idr(l.after.video_gmv, lang)}) · {l.note}</div>
            </div>
            <span />
          </div>
        );
      })}
    </div>
  );
}

function VideoSpark({ v }: { v: VPHistVideo }) {
  const lang = useLang(), t = useT();
  const vals = v.days.map((d) => d.views);
  const max = Math.max(1, ...vals);
  const pts = vals.map((y, i) => `${(i / Math.max(1, vals.length - 1)) * 100} ${28 - (y / max) * 26}`);
  const peakI = v.days.findIndex((d) => d.date === v.peak_day);
  const clicks = v.days.reduce((a, d) => a + d.clicks, 0), orders = v.days.reduce((a, d) => a + d.orders, 0);
  return (
    <div className="card" style={{ padding: "10px 12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span><b>Video {shortId(v.external_video_id ?? v.video_id)}</b> <span className="tiny">{v.caption ?? ""} · {t("published")} {dayMon(v.published_at, lang)}</span></span>
        <Pill tone={PHASE[v.phase]}>{t(v.phase)}</Pill>
      </div>
      <svg viewBox="0 0 100 30" preserveAspectRatio="none" style={{ width: "100%", height: 40, marginTop: 6 }} aria-hidden="true">
        <path d={`M${pts.join(" L")}`} fill="none" stroke="var(--warn)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {peakI >= 0 && <circle cx={(peakI / Math.max(1, vals.length - 1)) * 100} cy={28 - (vals[peakI] / max) * 26} r="2" fill="var(--ink)" />}
      </svg>
      <div className="small" style={{ color: "var(--ink2)" }}>{t("peak")} <b>{int(v.peak_views, lang)}</b> · {dayMon(v.peak_day, lang)} · {t("recent vs peak")} <b>{pct(v.recent_vs_peak, lang, { frac: 0 })}</b> · {t("Clicks")} {int(clicks, lang)} · {t("Orders")} {int(orders, lang)}</div>
    </div>
  );
}

export default function History({ hist }: { hist: VPHistory }) {
  const t = useT();
  const [pid, setPid] = useState<number | null>(hist.products[0]?.product_id ?? null);
  const p = hist.products.find((x) => x.product_id === pid) ?? hist.products[0];
  if (!p) return <div className="note">{t("No history for this period.")}</div>;
  return (
    <>
      <div className="trend">
        <div className="card chart">
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
            <span className="k lbl">{t("History · videos → product over time")}</span>
            <select aria-label={t("Select product")} value={p.product_id} onChange={(e) => setPid(Number(e.target.value))} style={{ padding: "3px 8px", fontSize: 12 }}>
              {hist.products.map((x) => <option key={x.product_id} value={x.product_id}>{x.title}</option>)}
            </select>
          </div>
          <ProductTimeline p={p} />
          <div className="k lbl" style={{ margin: "12px 0 4px" }}>{t("What worked / what needs improvement")} <span className="tiny" style={{ textTransform: "none", letterSpacing: 0 }}>· {t("Association on all traffic, not attribution")}</span></div>
          <Lifts p={p} />
        </div>
        <div className="card pace">
          <div className="k lbl">{t("Video lifecycle")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8, maxHeight: 520, overflow: "auto" }}>
            {hist.videos.map((v) => <VideoSpark key={v.video_id} v={v} />)}
          </div>
        </div>
      </div>
      <div className="tiny">{hist.notes.join(" · ")}</div>
    </>
  );
}
