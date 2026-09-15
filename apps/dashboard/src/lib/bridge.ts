import type { BridgeProduct, BridgeVideo } from "./types";

// TikTok resolves a watch URL by video id alone, so a stale/placeholder handle still lands
// on the right video (verified live 2026-09-15 against a real GMV Max post). Caller-supplied
// ids can be missing (BridgeVideo.external_video_id is nullable); "" keeps that a dead but
// inert link instead of a URL literally ending in "/video/null".
export const videoWatchUrl = (v: Pick<BridgeVideo, "video_reference" | "external_video_id">): string =>
  `https://www.tiktok.com/@${v.video_reference || "tiktok"}/video/${v.external_video_id ?? ""}`;

export type VideoSignal = { tone: "good" | "warn" | "bad" | "gray"; label: string };

// No per-video ad Cost exists (GMV Max leaves 96% of orders unattributed), so "invest more" is
// read off proven organic sales plus the verdict already earned by the products this video
// carries — not a new number.
export function videoSignal(v: Pick<BridgeVideo, "orders" | "products">,
                            byProduct: Map<number, Pick<BridgeProduct, "verdict">>, ru: boolean): VideoSignal {
  if (v.orders === 0) return { tone: "gray", label: ru ? "без продаж" : "no sales" };
  const verdicts = new Set(v.products.map((pid) => byProduct.get(pid)?.verdict).filter(Boolean));
  const hasScale = verdicts.has("scale"), hasHold = verdicts.has("hold");
  // "cut"/"no_orders" is real, measured evidence of a loss; "no_data" (or no linked product at
  // all) is missing evidence, not evidence of loss, and must not collapse into the same label.
  const hasLoss = verdicts.has("cut") || verdicts.has("no_orders");
  // Ad exposure is bought per video, not per product: boosting a video that also carries a
  // losing product feeds that loss too. A coexisting loss must never be silently outvoted by
  // a "scale"/"hold" product into a plain "invest more".
  if (hasLoss && (hasScale || hasHold)) {
    return { tone: "warn", label: ru ? "продажи есть — но несёт и убыточный товар" : "proven — but also carries a losing product" };
  }
  if (hasLoss) return { tone: "bad", label: ru ? "продажи есть, но в минус" : "sells, but at a loss" };
  if (hasScale) return { tone: "good", label: ru ? "продажи есть — лить бюджет" : "proven — invest more" };
  if (hasHold) return { tone: "warn", label: ru ? "продажи есть — на грани" : "proven — at the edge" };
  return { tone: "gray", label: ru ? "продажи есть, товар не оценён" : "sales, product not scored" };
}
