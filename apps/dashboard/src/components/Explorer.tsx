"use client";
import { useLang, useT } from "@/lib/i18n";
import { dayMon, idr, int, num, pct, shortId } from "@/lib/format";
import type { Campaigns, Creators, ProductStatus, Products, VideoClass, Videos } from "@/lib/types";
import type { Loaded } from "@/lib/api";
import { ErrorNote, Pill, Skeleton, ZoneHeader } from "./ui";

export const PSTATUS: Record<ProductStatus | "NO_SALES", { label: string; tone: "good" | "bad" | "warn" | "info" | "gray" }> = {
  SCALE: { label: "Scale", tone: "good" }, HEALTHY: { label: "Healthy", tone: "good" }, WATCH: { label: "Watch", tone: "info" },
  INVESTIGATE: { label: "Investigate", tone: "warn" }, REDUCE: { label: "Reduce", tone: "bad" }, SMALL_SAMPLE: { label: "Small sample", tone: "gray" },
  NO_SALES: { label: "Small sample", tone: "gray" },
};
export const VCLASS: Record<VideoClass, { label: string; tone: "good" | "bad" | "warn" | "info" | "gray" }> = {
  WINNER: { label: "Winner", tone: "good" }, PROMISING: { label: "Promising", tone: "info" }, TRAFFIC_NO_SALES: { label: "Traffic, no sales", tone: "bad" },
  LOW_ATTENTION: { label: "Low attention", tone: "warn" }, LOSER: { label: "Loser", tone: "bad" }, FATIGUING: { label: "Fatiguing", tone: "warn" },
  NEUTRAL: { label: "Neutral", tone: "gray" }, WATCH: { label: "Watch", tone: "warn" }, INSUFFICIENT_DATA: { label: "Insufficient data", tone: "gray" },
};
export const ProductPill = ({ s }: { s: string }) => {
  const t = useT();
  const m = PSTATUS[s as ProductStatus] ?? PSTATUS.NO_SALES;
  return <Pill tone={m.tone}>{t(s) === s ? t(m.label) : t(s)}</Pill>;
};
export const VideoPill = ({ c }: { c: VideoClass | null | undefined }) => {
  const t = useT();
  const m = c ? VCLASS[c] : null;
  return m && c ? <Pill tone={m.tone}>{t(c) === c ? t(m.label) : t(c)}</Pill> : <Pill tone="gray">—</Pill>;
};

const neg = (v: string | null, lang: "en" | "ru") => idr(-(num(v) ?? 0), lang);

interface Props {
  tab: string; setTab: (t: string) => void; apiDown?: boolean;
  products: Loaded<Products>; videos: Loaded<Videos>; campaigns: Loaded<Campaigns>; creators: Loaded<Creators>;
}

export default function Explorer({ tab, setTab, apiDown, products, videos, campaigns, creators }: Props) {
  const lang = useLang(), t = useT();
  const TABS = [["products", "Products"], ["videos", "Videos"], ["campaigns", "Campaigns"], ["creators", "Creators"]] as const;
  const cur = TABS.some(([k]) => k === tab) ? tab : "products";
  const L = cur === "products" ? products : cur === "videos" ? videos : cur === "campaigns" ? campaigns : creators;
  return (
    <section className="zone">
      <ZoneHeader id="z4" eyebrow={t("4 · Performance explorer")} title={t("Campaigns · Products · Videos · Creators")} hint={t("Sorted by net profit")} />
      <div className="card">
        <div className="tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} id={`tab-${k}`} role="tab" aria-selected={cur === k} aria-controls={`panel-${k}`} className={cur === k ? "on" : ""} onClick={() => setTab(k)}>{t(l)}</button>)}</div>
        {L.error && !apiDown && <div style={{ padding: 12 }}><ErrorNote error={L.error} onRetry={L.reload} /></div>}
        {L.loading && !L.data ? <div style={{ padding: 12 }}><Skeleton h={120} /></div> : (
          <>
            {cur === "products" && products.data && (
              <div className="scroll" id="panel-products" role="tabpanel" aria-labelledby="tab-products"><table className="tbl">
                <thead><tr><th>{t("Product")}</th><th className="r">{t("Units")}</th><th className="r">{t("Orders")}</th><th className="r">{t("GMV")}</th><th className="r">{t("Net revenue")}</th><th className="r">{t("Fees")}</th><th className="r">{t("COGS")}</th><th className="r">{t("Ads (est.)")}</th><th className="r">{t("Net profit")}</th><th className="r">{t("Margin")}</th><th className="r">CVR</th><th>{t("Status")}</th></tr></thead>
                <tbody>
                  {products.data.rows.length === 0 && <tr><td colSpan={12} className="empty">{t("No products in this period.")}</td></tr>}
                  {products.data.rows.map((r) => {
                    const np = num(r.net_profit) ?? 0;
                    return (
                      <tr key={r.product_id} title={r.status_reason}>
                        <td style={{ whiteSpace: "normal", minWidth: 220 }}>{r.title}</td>
                        <td className="r">{int(r.units, lang)}</td><td className="r">{int(r.orders, lang)}</td>
                        <td className="r">{idr(r.gmv, lang)}</td><td className="r">{idr(r.net_seller_revenue, lang)}</td>
                        <td className="r">{neg(r.fees, lang)}</td><td className="r">{neg(r.cogs, lang)}</td>
                        <td className="r" title={products.data?.ad_cost_note}>{neg(r.ad_cost, lang)} <span className="tiny">{t("est.")}</span></td>
                        <td className={`r ${np < 0 ? "dn" : "up"}`}>{idr(r.net_profit, lang)}</td>
                        <td className={`r ${(num(r.net_margin) ?? 0) < 0 ? "dn" : ""}`}>{pct(r.net_margin, lang)}</td>
                        <td className="r" title={products.data?.cvr_note}>{pct(r.cvr, lang)}</td>
                        <td><ProductPill s={r.status} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="tiny" style={{ padding: "8px 12px" }}>{t("Ads (est.)")}: {t("BLENDED estimate · LOW confidence")} — {products.data.ad_cost_note}. CVR: {products.data.cvr_note}.</div>
              </div>
            )}
            {cur === "videos" && videos.data && (
              <>
                {videos.data.cards.length === 0 && <div className="empty muted" style={{ padding: 26, textAlign: "center" }}>{t("No videos with metrics in this period.")}</div>}
                <div className="gallery" id="panel-videos" role="tabpanel" aria-labelledby="tab-videos">
                  {videos.data.cards.map((v) => (
                    <div className="vcard" key={v.video_id}>
                      <div className="thumb"><VideoPill c={v.classification} />{v.duration_seconds ? `${v.duration_seconds} s` : ""}{v.caption ? ` · ${v.caption}` : ""}</div>
                      <div className="vb">
                        <span className="id">{t("Video")} {shortId(v.external_video_id ?? v.video_id)}</span>
                        <span className="k">{t("Views count")}</span><span className="v">{int(v.views, lang)}</span>
                        <span className="k">CTR</span><span className={`v ${v.classification === "PROMISING" || v.classification === "WINNER" ? "up" : v.classification === "LOW_ATTENTION" ? "dn" : ""}`}>{pct(v.ctr, lang)}</span>
                        <span className="k" title={v.clicks_note ?? videos.data?.clicks_note}>{t("Clicks")} <span className="tiny">({t("derived")}{lang === "ru" ? " · EN" : ""}: {v.clicks_note ?? videos.data?.clicks_note})</span></span><span className="v">{int(v.clicks, lang)}</span>
                        <span className="k">{t("Orders")}</span><span className={`v ${v.orders === 0 ? "dn" : ""}`}>{int(v.orders, lang)}</span>
                        <span className="k">{t("GMV")}</span><span className="v">{idr(v.gmv, lang)}</span>
                        <span className="k">GPM</span><span className="v">{idr(v.gpm, lang)}</span>
                        <span className="k">{t("Ad spend")}</span><span className="v muted" title={v.ad_spend_note}>{t("NOT AVAILABLE — Ads API pending")}</span>
                        <span className="k">{t("Age")}</span><span className="v">{v.age_days} {t("d")}</span>
                        <span className="rs">{t("Confidence")} {t(v.confidence)} · {v.reasons.join("; ")}{lang === "ru" && " · EN"}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="tiny" style={{ padding: "0 12px 10px" }}>{videos.data.clicks_note} · {videos.data.ad_spend_note}</div>
              </>
            )}
            {cur === "campaigns" && campaigns.data && (
              <div className="scroll" id="panel-campaigns" role="tabpanel" aria-labelledby="tab-campaigns"><table className="tbl">
                <thead><tr><th>{t("Campaign")}</th><th>{t("Status")}</th><th className="r">{t("Spend")}</th><th className="r">{t("Orders")}</th><th className="r">{t("GMV")}</th><th className="r">{t("Reported ROAS")}</th><th className="r">{t("Adjusted ROAS")}</th><th className="r">{t("Net profit")}</th><th>{t("AI status")}</th></tr></thead>
                <tbody>
                  <tr><td colSpan={9} className="empty">
                    <b>{t("NOT AVAILABLE — Ads API pending")}</b> — {t("Campaign breakdown appears after the TikTok Ads app is approved")} ({campaigns.data.reason}). {t("Until then ad cost is shop-level")}: <b>{idr(campaigns.data.shop_level_ad_cost, lang)}</b> {t("in")} {campaigns.data.deductions.length} {t("deductions")}.
                    {campaigns.data.deductions.length > 0 && <div className="small" style={{ marginTop: 8 }}>{campaigns.data.deductions.map((d, i) => <span key={i} style={{ marginRight: 12 }}>◆ {dayMon(d.date, lang)} {idr(d.amount, lang)}</span>)}</div>}
                  </td></tr>
                </tbody>
              </table></div>
            )}
            {cur === "creators" && creators.data && (
              <div className="scroll" id="panel-creators" role="tabpanel" aria-labelledby="tab-creators"><table className="tbl">
                <thead><tr><th>{t("Creator")}</th><th className="r">{t("Orders")}</th><th className="r">{t("GMV")}</th><th className="r">{t("Affiliate commission")}</th><th className="r">{t("Profit after commission")}</th></tr></thead>
                <tbody>
                  {creators.data.rows.map((r, i) => (
                    <tr key={i}><td>{t(r.creator)}</td><td className="r">{int(r.orders, lang)}</td><td className="r">{idr(r.gmv, lang)}</td><td className="r dn">{r.affiliate_commission == null ? "—" : neg(r.affiliate_commission, lang)}</td><td className="r">{idr(r.profit_after_commission, lang)}</td></tr>
                  ))}
                </tbody>
              </table><div className="tiny" style={{ padding: "8px 12px" }}>{creators.data.note}</div></div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
