"use client";
import { useLang, useT } from "@/lib/i18n";
import { dayMon, idr, int, neg, pct, ratio, shortId } from "@/lib/format";
import type { Campaigns, CreativeBridge, Creators, Products, Videos } from "@/lib/types";
import type { Loaded } from "@/lib/api";
import { ErrorNote, Pill, Skeleton, VideoPill, ZoneHeader } from "./ui";
import AdvertisingSource from "./AdvertisingSource";
import Bridge from "./Bridge";
import ProductsSplit from "./ProductsSplit";
import { VideoTrigger } from "./VideoPreview";

// Re-exported for Performers.tsx/VideoProducts.tsx, which import these from here.
export { PSTATUS, ProductPill, VCLASS, VideoPill } from "./ui";

interface Props {
  tab: string; setTab: (t: string) => void; apiDown?: boolean;
  products: Loaded<Products>; videos: Loaded<Videos>; campaigns: Loaded<Campaigns>;
  bridge: Loaded<CreativeBridge>; creators: Loaded<Creators>;
}

export default function Explorer({ tab, setTab, apiDown, products, videos, campaigns, bridge, creators }: Props) {
  const lang = useLang(), t = useT(), ru = lang === "ru";
  const TABS = [["products", "Products"], ["videos", "Videos"], ["campaigns", "Campaigns"], ["bridge", "Video → product → cost"], ["creators", "Creators"]] as const;
  const cur = TABS.some(([k]) => k === tab) ? tab : "products";
  const L = cur === "products" ? products : cur === "videos" ? videos : cur === "campaigns" ? campaigns : cur === "bridge" ? bridge : creators;
  return (
    <section className="zone">
      <ZoneHeader id="z4" eyebrow={t("4 · Performance explorer")} title={t("Campaigns · Products · Videos · Creators")} hint={t("Sorted by net profit")} />
      <div className="card">
        <div className="tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} id={`tab-${k}`} role="tab" aria-selected={cur === k} aria-controls={`panel-${k}`} className={cur === k ? "on" : ""} onClick={() => setTab(k)}>{t(l)}</button>)}</div>
        {L.error && !apiDown && <div style={{ padding: 12 }}><ErrorNote error={L.error} onRetry={L.reload} /></div>}
        {L.loading && !L.data ? <div style={{ padding: 12 }}><Skeleton h={120} /></div> : (
          <>
            {cur === "products" && products.data && <ProductsSplit products={products} />}
            {cur === "videos" && videos.data && (
              <>
                {videos.data.cards.length === 0 && <div className="empty muted" style={{ padding: 26, textAlign: "center" }}>{t("No videos with metrics in this period.")}</div>}
                <div className="gallery" id="panel-videos" role="tabpanel" aria-labelledby="tab-videos">
                  {videos.data.cards.map((v) => (
                    <div className="vcard" key={v.video_id}>
                      <div className="thumb">
                        <VideoTrigger v={v} ru={ru} className="thumb-trigger">
                          <VideoPill c={v.classification} />{v.duration_seconds ? `${v.duration_seconds} s` : ""}{v.caption ? ` · ${v.caption}` : ""}
                        </VideoTrigger>
                      </div>
                      <div className="vb">
                        <span className="id">{t("Video")} {shortId(v.external_video_id ?? v.video_id)}</span>
                        <span className="k">{t("Views count")}</span><span className="v">{int(v.views, lang)}</span>
                        <span className="k">CTR</span><span className={`v ${v.classification === "PROMISING" || v.classification === "WINNER" ? "up" : v.classification === "LOW_ATTENTION" ? "dn" : ""}`}>{pct(v.ctr, lang)}</span>
                        <span className="k" title={v.clicks_note ?? videos.data?.clicks_note}>{t("Clicks")} <span className="tiny">({t("derived")}{lang === "ru" ? " · EN" : ""}: {v.clicks_note ?? videos.data?.clicks_note})</span></span><span className="v">{int(v.clicks, lang)}</span>
                        <span className="k">{t("Orders")}</span><span className={`v ${v.orders === 0 ? "dn" : ""}`}>{int(v.orders, lang)}</span>
                        <span className="k">{t("GMV")}</span><span className="v">{idr(v.gmv, lang)}</span>
                        <span className="k">GPM</span><span className="v">{idr(v.gpm, lang)}</span>
                        <span className="k">{t("Ad spend")}</span><span className="v muted" title={v.ad_spend_note}>{lang === "ru" ? "нет разбивки по видео" : "no per-video split"}</span>
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
                <thead><tr><th>{t("Campaign")}</th><th className="r">{t("Spend")}</th><th className="r">{lang === "ru" ? "Заказы TikTok" : "TikTok orders"}</th><th className="r">{lang === "ru" ? "Выручка TikTok" : "TikTok revenue"}</th><th className="r">{lang === "ru" ? "Цена заказа" : "Cost per order"}</th><th className="r">ROI</th><th>{t("Status")}</th></tr></thead>
                <tbody>
                  {campaigns.data.rows.map((r) => (
                    <tr key={r.campaign_id}>
                      <td>{r.name}<br /><span className="tiny mono">{r.campaign_id}</span></td>
                      <td className="r">{idr(r.spend, lang)}</td>
                      <td className={`r ${r.attributed_orders === 0 ? "dn" : ""}`}>{int(r.attributed_orders, lang)}</td>
                      <td className="r">{idr(r.attributed_revenue, lang)}</td>
                      <td className="r">{r.cost_per_order === null ? "—" : idr(r.cost_per_order, lang)}</td>
                      <td className="r">{r.reported_roi === null ? "—" : ratio(r.reported_roi, lang)}</td>
                      <td>{r.final ? <Pill tone="gray">{lang === "ru" ? "закрыт" : "settled"}</Pill> : <Pill tone="warn">{lang === "ru" ? "день идёт" : "day open"}</Pill>}</td>
                    </tr>
                  ))}
                  {!campaigns.data.rows.length && <tr><td colSpan={7} className="empty">{campaigns.data.reason}</td></tr>}
                  <tr><td colSpan={7} className="empty">
                    <AdvertisingSource data={campaigns.data.advertising} currency={campaigns.data.shop.currency} />
                    <b>{lang === "ru" ? "Заказы и выручка — атрибуция самого TikTok, а не бухгалтерия магазина." : "Orders and revenue are TikTok's own attribution, not the shop's booked figures."}</b>
                    <p>{lang === "ru" ? "Сравнивать их с прибылью напрямую нельзя: платформа засчитывает заказ кампании по своим правилам. Расход (Cost) — точный. Платежи GMV Pay ниже — движение денег, а не дополнительный расход." : "They are not comparable with booked profit: the platform credits a campaign by its own rules. Cost is exact. GMV Pay payments below are cash movement, not a second expense."}</p>
                    {campaigns.data.deductions.length > 0 && <div className="small" style={{ marginTop: 8 }}>{campaigns.data.deductions.map((d, i) => <span key={i} style={{ marginRight: 12 }}>◆ {dayMon(d.date, lang)} {idr(d.amount, lang)}</span>)}</div>}
                  </td></tr>
                </tbody>
              </table></div>
            )}
            {cur === "bridge" && bridge.data && <Bridge data={bridge.data} />}
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
