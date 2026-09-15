"use client";
import { useEffect, useRef, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { idr, int, num, ratio, shortId } from "@/lib/format";
import { videoSignal, videoWatchUrl } from "@/lib/bridge";
import type { BridgeVerdict, BridgeVideo, CreativeBridge } from "@/lib/types";
import { Pill, useDialogAutoOpen } from "./ui";

const TONE: Record<BridgeVerdict, "good" | "warn" | "bad" | "gray"> =
  { scale: "good", hold: "warn", cut: "bad", no_orders: "bad", no_data: "gray" };

function verdictLabel(v: BridgeVerdict, ru: boolean) {
  if (v === "scale") return ru ? "есть запас" : "room to scale";
  if (v === "hold") return ru ? "на грани" : "at the edge";
  if (v === "cut") return ru ? "в минус" : "buying at a loss";
  if (v === "no_orders") return ru ? "без заказов" : "no orders";
  return ru ? "нет данных" : "no data";
}

function VideoDialog({ v, close, ru }: { v: BridgeVideo; close: () => void; ru: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useDialogAutoOpen(ref);
  // The trigger only opens this for a row with an id (see the table cell below); falling back to
  // "" rather than interpolating null keeps a freak call inert instead of requesting .../null.
  const id = v.external_video_id ?? "";
  return (
    <dialog className="video-dialog" ref={ref} onClose={close} aria-labelledby="video-dialog-title">
      <div className="order-dialog-head">
        <h2 id="video-dialog-title">{v.caption || shortId(id)}</h2>
        <button className="btn" onClick={() => ref.current?.close()}>{ru ? "Закрыть" : "Close"}</button>
      </div>
      <iframe src={`https://www.tiktok.com/embed/v2/${id}`} allow="encrypted-media;" allowFullScreen />
      <div style={{ padding: "12px 24px" }}>
        <a href={videoWatchUrl(v)} target="_blank" rel="noopener noreferrer">{ru ? "Открыть в TikTok ↗" : "Open on TikTok ↗"}</a>
      </div>
    </dialog>
  );
}

export default function Bridge({ data }: { data: CreativeBridge }) {
  const lang = useLang(), t = useT(), ru = lang === "ru";
  // Videos with no views in the period say nothing; an empty row is not a weak result.
  const videos = data.videos.filter((v) => v.views > 0);
  const byProduct = new Map(data.products.map((p) => [p.product_id, p]));
  const [openVideo, setOpenVideo] = useState<number | null>(null);
  const openVideoRow = openVideo === null ? null : videos.find((v) => v.video_id === openVideo) ?? null;
  // A refresh can drop the open video from the period's data (e.g. its views fall to 0); when
  // that happens the dialog would otherwise vanish with openVideo still pointing at a dead row.
  useEffect(() => {
    if (openVideo !== null && !openVideoRow) setOpenVideo(null);
  }, [openVideo, openVideoRow]);

  return (
    <div className="scroll" id="panel-bridge" role="tabpanel" aria-labelledby="tab-bridge">
      <div className="note" style={{ margin: 12 }}>
        <b>{ru ? "Расход по товарам измерен, а не распределён." : "Product Cost is measured, not allocated."}</b>{" "}
        <span>{ru ? `Из ${idr(data.total_ad_cost, lang)} привязано к товарам ${idr(data.measured_ad_cost, lang)}, не привязано ${idr(data.unattributed_ad_cost, lang)} — эта часть показана отдельно, а не размазана по товарам.`
                 : `Of ${idr(data.total_ad_cost, lang)}, ${idr(data.measured_ad_cost, lang)} resolves to a product and ${idr(data.unattributed_ad_cost, lang)} does not. The remainder is shown, not spread.`}</span>
      </div>

      <table className="tbl">
        <thead><tr>
          <th>{t("Product")}</th>
          <th className="r">{ru ? "Расход" : "Ad cost"}</th>
          <th className="r">{ru ? "Вклад" : "Contribution"}</th>
          <th className="r">{ru ? "Прибыль" : "Profit"}</th>
          <th className="r">{ru ? "Заказы" : "Orders"}</th>
          <th className="r">CPO</th>
          <th className="r">{ru ? "Безубыточный CPO" : "Break-even CPO"}</th>
          <th className="r">{ru ? "Запас" : "Headroom"}</th>
          <th>{t("Status")}</th>
        </tr></thead>
        <tbody>
          {!data.products.length && <tr><td colSpan={9} className="empty">{ru ? "Нет данных за период." : "No data for this period."}</td></tr>}
          {data.products.map((p) => {
            const profit = num(p.profit) ?? 0;
            return (
              <tr key={p.product_id}>
                <td style={{ whiteSpace: "normal", minWidth: 220 }}>{p.title}</td>
                <td className="r">{idr(p.ad_cost, lang)}</td>
                <td className="r">{idr(p.contribution, lang)}</td>
                <td className={`r ${profit < 0 ? "dn" : "up"}`}>{idr(p.profit, lang)}</td>
                <td className="r">{int(p.orders, lang)}</td>
                <td className="r">{p.cpo === null ? "—" : idr(p.cpo, lang)}</td>
                <td className="r">{p.break_even_cpo === null ? "—" : idr(p.break_even_cpo, lang)}</td>
                <td className="r"><b>{p.headroom === null ? "—" : `×${ratio(p.headroom, lang)}`}</b></td>
                <td><Pill tone={TONE[p.verdict]}>{verdictLabel(p.verdict, ru)}</Pill></td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="note" style={{ margin: 12 }}>
        <b>{ru ? "Запас — это отношение безубыточного CPO к фактическому." : "Headroom is break-even CPO divided by actual CPO."}</b>{" "}
        <span>{ru ? "Больше единицы — товар выдержит более дорогой заказ и всё равно заработает. Меньше — каждый следующий заказ покупается в убыток. Порог у каждого товара свой: поштучная пара за 19 000 и комплект за 75 000 не могут жить под одной целью по CPO."
                 : "Above one the product can absorb a dearer order and still earn; below one every further order is bought at a loss. The threshold is per product: a 19,000 single pair and a 75,000 five-pack cannot share one CPO target."}</span>
      </div>

      <table className="tbl">
        <thead><tr>
          <th>{t("Video")}</th>
          <th className="r">{t("Views count")}</th>
          <th className="r">{t("Orders")}</th>
          <th className="r">{t("GMV")}</th>
          <th className="r">GPM</th>
          <th>{ru ? "Несёт товары" : "Carries products"}</th>
          <th>{ru ? "Сигнал" : "Signal"}</th>
        </tr></thead>
        <tbody>
          {!videos.length && <tr><td colSpan={7} className="empty">{ru ? "Ни одно видео не набрало просмотров за период." : "No video gathered views in this period."}</td></tr>}
          {videos.map((v) => {
            const signal = videoSignal(v, byProduct, ru);
            return (
              <tr key={v.video_id}>
                <td>
                  {v.external_video_id ? (
                    <button type="button" className="order-link" onClick={() => setOpenVideo(v.video_id)}
                            title={ru ? "Открыть креатив" : "Open the creative"}>
                      {Array.from(v.caption || shortId(v.external_video_id)).slice(0, 40).join("")}
                    </button>
                  ) : shortId(String(v.video_id))}
                </td>
                <td className="r">{int(v.views, lang)}</td>
                <td className={`r ${v.orders === 0 ? "dn" : ""}`}>{int(v.orders, lang)}</td>
                <td className="r">{idr(v.gmv, lang)}</td>
                <td className="r"><b>{v.gpm === null ? "—" : idr(v.gpm, lang)}</b></td>
                <td style={{ whiteSpace: "normal", minWidth: 200 }}>
                  {v.products.length === 0 ? <span className="muted">—</span> : v.products.map((pid) => {
                    const p = byProduct.get(pid);
                    if (!p) return null;
                    return <Pill key={pid} tone={TONE[p.verdict]}>{(p.title ?? "").slice(0, 26)}</Pill>;
                  })}
                </td>
                <td><Pill tone={signal.tone}>{signal.label}</Pill></td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="note dn" style={{ margin: 12 }}>
        <b>{ru ? "Прибыли на видео здесь нет, и это не упущение." : "There is no profit per video here, and that is not an omission."}</b>{" "}
        <span>{ru ? "GMV Max относит 96% заказов в неатрибутированную корзину, поэтому рекламный расход на конкретное видео не существует как измеримая величина. Видео судится по GPM — сколько денег приносит тысяча просмотров — и по тому, какие товары оно несёт: цветом отмечено, зарабатывает ли товар свою рекламу. «Сигнал» — то же самое одним ярлыком: были ли реальные заказы и тянут ли товары, которые несёт видео, свою рекламу."
                 : "GMV Max leaves 96% of orders in an unattributed bucket, so ad spend per video does not exist as a measurable quantity. A video is judged on GPM — money per thousand views — and on the products it carries, coloured by whether each earns its advertising. \"Signal\" is the same read as one label: whether real orders happened and whether the products this video carries earn their ad money."}</span>
      </div>

      {openVideoRow && <VideoDialog v={openVideoRow} close={() => setOpenVideo(null)} ru={ru} />}
    </div>
  );
}
