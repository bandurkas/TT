"use client";
import { useEffect, useRef, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { dayMon, idr, int, num, pct, shortId } from "@/lib/format";
import type { VideoProducts as VP } from "@/lib/types";
import { ErrorNote, Pill, Skeleton, ZoneHeader } from "./ui";
import { ProductPill, VideoPill } from "./Explorer";
import History from "./History";

const fmtAxis = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)}k` : String(v));

function SplitChart({ days }: { days: VP["shop_split"]["days"] }) {
  const lang = useLang(), t = useT();
  const ref = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(900);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver((e) => setW(Math.max(320, Math.floor(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = 220, P = { l: 46, r: 46, t: 12, b: 24 };
  const n = days.length;
  const vid = days.map((d) => num(d.gmv_video) ?? 0), card = days.map((d) => num(d.gmv_product_card) ?? 0), views = days.map((d) => d.video_views);
  const maxG = Math.max(1, ...vid.map((v, i) => v + card[i])), maxV = Math.max(1, ...views);
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const X = (i: number) => P.l + (n > 1 ? (iw * i) / (n - 1) : iw / 2);
  const Y = (v: number) => P.t + ih * (1 - v / maxG), YV = (v: number) => P.t + ih * (1 - v / maxV);
  const bw = Math.max(2, Math.min(12, (iw / Math.max(n, 1)) * 0.6));
  const labelEvery = Math.max(1, Math.ceil(n / 6));
  return (
    <div ref={ref}>
      <div className="legend"><span><i style={{ background: "var(--accent)" }} />{t("Video GMV")}</span><span><i style={{ background: "var(--gray-soft)", border: "1px solid var(--line)" }} />{t("Product card GMV")}</span><span><i style={{ background: "var(--warn)" }} />{t("Video views")}</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label="GMV video vs product card, video views">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => <g key={f}><line x1={P.l} x2={W - P.r} y1={Y(maxG * f)} y2={Y(maxG * f)} stroke="var(--line)" /><text x={4} y={Y(maxG * f) + 4} fontSize="11" fill="var(--muted)">{fmtAxis(maxG * f)}</text><text x={W - P.r + 4} y={YV(maxV * f) + 4} fontSize="11" fill="var(--warn)">{fmtAxis(maxV * f)}</text></g>)}
        {days.map((d, i) => (i % labelEvery === 0 || i === n - 1) && <text key={d.date} x={X(i)} y={H - 6} fontSize="11" fill="var(--muted)" textAnchor="middle">{dayMon(d.date, lang)}</text>)}
        {days.map((d, i) => <g key={d.date}>
          <rect x={X(i) - bw / 2} y={Y(card[i])} width={bw} height={Y(0) - Y(card[i])} fill="var(--gray-soft)" stroke="var(--line)"><title>{`${dayMon(d.date, lang)} ${t("product card")} ${idr(card[i], lang)}`}</title></rect>
          <rect x={X(i) - bw / 2} y={Y(card[i] + vid[i])} width={bw} height={Y(0) - Y(vid[i])} fill="var(--accent)" opacity="0.75"><title>{`${dayMon(d.date, lang)} ${t("video")} ${idr(vid[i], lang)}`}</title></rect>
        </g>)}
        {n > 0 && <path d={views.map((v, i) => `${i ? "L" : "M"}${X(i)} ${YV(v)}`).join(" ")} fill="none" stroke="var(--warn)" strokeWidth="2" />}
      </svg>
    </div>
  );
}

const strength = (r: number | null) => (r === null ? "n/a" : Math.abs(r) >= 0.5 ? "strong" : Math.abs(r) >= 0.3 ? "moderate" : "weak");
const lagLabel = (l: number) => (l === 0 ? "same day" : l === 1 ? "+1 day" : "+2 days");

export default function VideoProducts({ vp, loading, error, reload }: { vp: VP | null; loading: boolean; error: string | null; reload: () => void }) {
  const lang = useLang(), t = useT();
  const [openP, setOpenP] = useState<Set<number>>(new Set());
  const toggle = (id: number) => setOpenP((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const sp = vp?.shop_split;
  return (
    <section className="zone">
      <ZoneHeader id="z4b" eyebrow={t("4b · Videos → Product cards")} title={t("Which video drives which listing")} hint={t("measured by TikTok video analytics")} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !vp ? <Skeleton h={260} /> : vp && sp && (
        <>
          <div className="trend">
            <div className="card chart">
              <div className="k lbl" style={{ marginBottom: 6 }}>{t("GMV: video vs product card")} · {t("video")} <b>{idr(sp.gmv_video, lang)}</b> · {t("product card")} <b>{idr(sp.gmv_product_card, lang)}</b>{(num(sp.gmv_live) ?? 0) > 0 && <> · {t("live")} <b>{idr(sp.gmv_live, lang)}</b></>} · {t("video share of GMV")} <b>{pct(sp.video_share, lang)}</b></div>
              {sp.days.length ? <SplitChart days={sp.days} /> : <div className="muted small">—</div>}
            </div>
            <div className="card pace">
              <div className="k lbl">{t("Dependency: views → product-card sales")}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {vp.dependency.lags.map((l) => {
                  const r = num(l.correlation);
                  const s = strength(r);
                  const best = vp.dependency.best_lag === l.lag_days && r !== null;
                  return (
                    <div key={l.lag_days} className="card" style={{ padding: "8px 10px", borderColor: best ? "var(--accent)" : undefined }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                        <span className="small"><b>{t("Video views")}</b> → {t("Product card GMV")} {t(lagLabel(l.lag_days))}</span>
                        <Pill tone={s === "strong" ? "good" : s === "moderate" ? "info" : "gray"}>{t(s)}</Pill>
                      </div>
                      <div className="mono small" style={{ marginTop: 2 }}>r = {r === null ? "—" : r.toFixed(2)} · n = {l.n} {t("days")}{best && <span className="up"> · {t("best lag")}</span>}</div>
                    </div>
                  );
                })}
              </div>
              <div className="tiny" style={{ marginTop: 10 }}>{vp.dependency.note}</div>
            </div>
          </div>
          <div className="two">
            <div className="card">
              <div className="k lbl" style={{ padding: "12px 12px 0" }}>{t("Products ← videos feeding them")}</div>
              <div className="scroll"><table className="tbl">
                <thead><tr><th></th><th>{t("Product")}</th><th className="r">{t("GMV")}</th><th className="r">{t("Video GMV")}</th><th className="r">{t("Video GMV share")}</th><th className="r">{t("Video units")}</th><th>{t("Status")}</th></tr></thead>
                <tbody>
                  {vp.products.length === 0 && <tr><td colSpan={7} className="empty">{t("No products in this period.")}</td></tr>}
                  {vp.products.map((p) => {
                    const open = openP.has(p.product_id);
                    return [
                      <tr key={p.product_id} style={{ cursor: p.videos.length ? "pointer" : "default" }} onClick={() => p.videos.length && toggle(p.product_id)}>
                        <td className="muted">{p.videos.length ? (open ? "▾" : "▸") : ""}</td>
                        <td style={{ whiteSpace: "normal", minWidth: 180 }}>{p.title}<br /><span className="tiny">{p.videos.length ? `${p.videos.length} ${t("Videos").toLowerCase()} · ${int(p.video_impressions, lang)} ${t("Impressions").toLowerCase()} · ${int(p.video_clicks, lang)} ${t("Clicks").toLowerCase()}` : t("no video traffic measured")}</span></td>
                        <td className="r">{idr(p.gmv, lang)}</td>
                        <td className="r">{idr(p.video_gmv, lang)}</td>
                        <td className="r">{pct(p.video_share, lang)}</td>
                        <td className="r">{int(p.video_units, lang)}</td>
                        <td><ProductPill s={p.status} /></td>
                      </tr>,
                      open && p.videos.map((v) => (
                        <tr key={`${p.product_id}-${v.video_id}`} style={{ background: "var(--surface2)" }}>
                          <td></td>
                          <td style={{ whiteSpace: "normal" }}><span className="muted">↳</span> Video {shortId(v.external_video_id ?? v.video_id)}<br /><span className="tiny">{v.caption ?? ""} · {int(v.impressions, lang)} {t("Impressions").toLowerCase()} · {int(v.clicks, lang)} {t("Clicks").toLowerCase()} · CTR {pct(v.ctr, lang)} · {int(v.customers, lang)} {t("customers")}</span></td>
                          <td className="r muted">—</td>
                          <td className="r">{idr(v.gmv, lang)}</td>
                          <td className="r">{pct(num(p.gmv) ? (num(v.gmv) ?? 0) / (num(p.gmv) ?? 1) : null, lang)}</td>
                          <td className="r">{int(v.units_sold, lang)}</td>
                          <td></td>
                        </tr>
                      )),
                    ];
                  })}
                </tbody>
              </table></div>
            </div>
            <div className="card">
              <div className="k lbl" style={{ padding: "12px 12px 0" }}>{t("Videos → products they sell")}</div>
              <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
                {vp.videos.length === 0 && <div className="muted small">{t("No videos with metrics in this period.")}</div>}
                {vp.videos.map((v) => (
                  <div className="card" key={v.video_id} style={{ padding: "10px 12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <span><b>Video {shortId(v.external_video_id ?? v.video_id)}</b> <span className="tiny">{v.caption ?? ""}</span></span>
                      <span className="small">{int(v.views, lang)} {t("Views count").toLowerCase()} <VideoPill c={v.classification} /></span>
                    </div>
                    <div className="scroll" style={{ marginTop: 6 }}><table className="tbl">
                      <thead><tr><th>{t("Product")}</th><th className="r">{t("Impressions")}</th><th className="r">{t("Clicks")}</th><th className="r">CTR</th><th className="r">{t("Units")}</th><th className="r">{t("GMV")}</th></tr></thead>
                      <tbody>{v.products.map((p) => <tr key={p.product_id}><td style={{ whiteSpace: "normal" }}>{p.title}</td><td className="r">{int(p.impressions, lang)}</td><td className="r">{int(p.clicks, lang)}</td><td className="r">{pct(p.ctr, lang)}</td><td className="r">{int(p.units_sold, lang)}</td><td className="r">{idr(p.gmv, lang)}</td></tr>)}</tbody>
                    </table></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          {vp.history && <History hist={vp.history} />}
          <div className="note">{vp.notes.join(" · ")} · {t("correlation ≠ causation")}</div>
        </>
      )}
    </section>
  );
}
