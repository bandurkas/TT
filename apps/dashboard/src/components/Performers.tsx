"use client";
import { useLang, useT } from "@/lib/i18n";
import { idr, int, pct } from "@/lib/format";
import { bestProducts, bestVideos, worstProducts, worstVideos } from "@/lib/performers";
import type { Products, Videos } from "@/lib/types";
import type { Loaded } from "@/lib/api";
import { ErrorNote, Skeleton, ZoneHeader } from "./ui";
import { ProductPill, VideoPill } from "./Explorer";
import { VideoTrigger } from "./VideoPreview";

interface Props { apiDown?: boolean; products: Loaded<Products>; videos: Loaded<Videos> }

export default function Performers({ apiDown, products, videos }: Props) {
  const lang = useLang(), t = useT(), ru = lang === "ru";
  const pRows = products.data?.rows ?? [];
  const vCards = videos.data?.cards ?? [];
  const loading = (products.loading && !products.data) || (videos.loading && !videos.data);
  const error = (products.error && !apiDown) ? products.error : (videos.error && !apiDown) ? videos.error : null;
  const bestP = bestProducts(pRows), worstP = worstProducts(pRows);
  const bestV = bestVideos(vCards), worstV = worstVideos(vCards);

  return (
    <section className="zone">
      <ZoneHeader id="z3b" eyebrow={t("3b · Best / worst")} title={t("Best & worst performers")}
                 hint={t("Same status/classification as the tables below — this is the headline, not a new score")} />
      {error && <ErrorNote error={error} onRetry={() => { products.reload(); videos.reload(); }} />}
      {loading ? <Skeleton h={200} /> : (
        <div className="two">
          <div>
            <div className="k lbl" style={{ margin: "10px 0 6px" }}>{t("Best products")}</div>
            <div className="card"><table className="tbl">
              <tbody>
                {bestP.length === 0 && <tr><td colSpan={3} className="empty">{t("None detected.")}</td></tr>}
                {bestP.map((r) => (
                  <tr key={r.product_id}>
                    <td style={{ whiteSpace: "normal", minWidth: 160 }}>{r.title}</td>
                    <td className="r up">{idr(r.net_profit, lang)}</td>
                    <td><ProductPill s={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <div className="k lbl" style={{ margin: "16px 0 6px" }}>{t("Best videos")}</div>
            <div className="card"><table className="tbl">
              <tbody>
                {bestV.length === 0 && <tr><td colSpan={5} className="empty">{t("None detected.")}</td></tr>}
                {bestV.map((v) => (
                  <tr key={v.video_id}>
                    <td style={{ whiteSpace: "normal", minWidth: 160 }}>
                      <VideoTrigger v={v} ru={ru}>{v.caption || t("Video") + " " + v.video_id}</VideoTrigger>
                    </td>
                    <td className="r">{int(v.orders, lang)} {t("Orders").toLowerCase()}</td>
                    <td className="r">{idr(v.gmv, lang)}</td>
                    <td className="r">{pct(v.ctr, lang)}</td>
                    <td><VideoPill c={v.classification} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </div>
          <div>
            <div className="k lbl" style={{ margin: "10px 0 6px" }}>{t("Worst products")}</div>
            <div className="card"><table className="tbl">
              <tbody>
                {worstP.length === 0 && <tr><td colSpan={3} className="empty">{t("None detected.")}</td></tr>}
                {worstP.map((r) => (
                  <tr key={r.product_id}>
                    <td style={{ whiteSpace: "normal", minWidth: 160 }}>{r.title}</td>
                    <td className="r dn">{idr(r.net_profit, lang)}</td>
                    <td><ProductPill s={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <div className="k lbl" style={{ margin: "16px 0 6px" }}>{t("Worst videos")}</div>
            <div className="card"><table className="tbl">
              <tbody>
                {worstV.length === 0 && <tr><td colSpan={5} className="empty">{t("None detected.")}</td></tr>}
                {worstV.map((v) => (
                  <tr key={v.video_id}>
                    <td style={{ whiteSpace: "normal", minWidth: 160 }}>
                      <VideoTrigger v={v} ru={ru}>{v.caption || t("Video") + " " + v.video_id}</VideoTrigger>
                    </td>
                    <td className={`r ${v.orders === 0 ? "dn" : ""}`}>{int(v.orders, lang)} {t("Orders").toLowerCase()}</td>
                    <td className="r">{idr(v.gmv, lang)}</td>
                    <td className="r">{pct(v.ctr, lang)}</td>
                    <td><VideoPill c={v.classification} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </div>
        </div>
      )}
    </section>
  );
}
