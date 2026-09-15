"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { idr, int, neg, num, pct } from "@/lib/format";
import { filterProducts, marginTone, PRODUCT_SORT_KEYS, sortProducts, type ProductSortKey } from "@/lib/productsSplit";
import type { Products } from "@/lib/types";
import type { Loaded } from "@/lib/api";
import { ProductPill } from "./ui";

/** Loading/error states are handled once at the Explorer level, shared across its tabs. */
export default function ProductsSplit({ products }: { products: Loaded<Products> }) {
  const lang = useLang(), t = useT();
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<ProductSortKey>("net_profit");
  const [selected, setSelected] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const hasRows = (products.data?.rows.length ?? 0) > 0;
  const visible = useMemo(
    () => sortProducts(filterProducts(products.data?.rows ?? [], query), sortKey),
    [products.data, query, sortKey],
  );

  useEffect(() => {
    if (!visible.some((r) => r.product_id === selected)) setSelected(visible[0]?.product_id ?? null);
  }, [visible, selected]);

  useEffect(() => {
    listRef.current?.querySelector(".split-item.active")?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const focus = visible.find((r) => r.product_id === selected) ?? null;

  const move = (dir: 1 | -1) => {
    if (visible.length === 0) return;
    const i = visible.findIndex((r) => r.product_id === selected);
    const next = i < 0 ? visible[0] : visible[(i + dir + visible.length) % visible.length];
    setSelected(next.product_id);
  };

  return (
    <div className="split" id="panel-products" role="tabpanel" aria-labelledby="tab-products">
      <div>
        <div className="split-controls">
          <input type="text" placeholder={t("Search products…")} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={t("Search products…")} />
          <select value={sortKey} onChange={(e) => setSortKey(e.target.value as ProductSortKey)} aria-label={t("Sort by")}>
            {PRODUCT_SORT_KEYS.map(({ key, label }) => <option key={key} value={key}>{t(label)}</option>)}
          </select>
        </div>
        <div className="split-list" ref={listRef} role="listbox" aria-label={t("Products")}
          onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); move(1); } if (e.key === "ArrowUp") { e.preventDefault(); move(-1); } }}>
          {visible.length === 0 && (
            <div className="empty muted" style={{ padding: 20, textAlign: "center" }}>
              {hasRows ? t("No products match your search.") : t("No products in this period.")}
            </div>
          )}
          {visible.map((r) => {
            const np = num(r.net_profit);
            return (
              <button key={r.product_id} type="button" role="option" aria-selected={r.product_id === selected}
                className={`split-item${r.product_id === selected ? " active" : ""}`} onClick={() => setSelected(r.product_id)}>
                <span className="title">{r.title}</span>
                <span className="meta">
                  <span className={np === null ? "" : np < 0 ? "dn" : "up"}>{idr(r.net_profit, lang)}</span>
                  <span className={marginTone(num(r.net_margin))}>{pct(r.net_margin, lang)}</span>
                  <ProductPill s={r.status} />
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="card split-focus">
        {!focus && (
          <div className="empty muted" style={{ padding: 20, textAlign: "center" }}>
            {hasRows ? t("No products match your search.") : t("No products in this period.")}
          </div>
        )}
        {focus && (
          <>
            <div className="split-focus-head">
              <h3 style={{ margin: 0 }}>{focus.title}</h3>
              {focus.external_product_id && <span className="tiny mono">{focus.external_product_id}</span>}
              <ProductPill s={focus.status} />
            </div>
            {focus.status_reason && <p className="hint" style={{ marginTop: 4 }}>{focus.status_reason}</p>}

            <div className="split-metrics">
              <div className="split-metric"><span className="k">{t("GMV")}</span><span className="v">{idr(focus.gmv, lang)}</span></div>
              <div className="split-metric"><span className="k">{t("Net seller revenue")}</span><span className="v">{idr(focus.net_seller_revenue, lang)}</span></div>
              <div className="split-metric"><span className="k">{t("Orders")}</span><span className="v">{int(focus.orders, lang)}</span></div>
              <div className="split-metric"><span className="k">{t("Units")}</span><span className="v">{int(focus.units, lang)}</span></div>
              <div className="split-metric"><span className="k">{t("Fees")}</span><span className="v dn">{neg(focus.fees, lang)}</span></div>
              <div className="split-metric"><span className="k">{t("COGS")}</span><span className="v dn">{neg(focus.cogs, lang)}</span></div>
              <div className="split-metric" title={products.data?.ad_cost_note}>
                <span className="k">{t("Ads (est.)")}</span>
                <span className="v dn">{neg(focus.ad_cost, lang)}{focus.ad_cost_is_estimate && <span className="tiny"> {t("est.")}</span>}</span>
              </div>
              <div className="split-metric"><span className="k">{t("Net profit")}</span>{num(focus.net_profit) === null
                ? <span className="v tiny muted">{t("Not computed yet")}</span>
                : <span className={`v ${(num(focus.net_profit) ?? 0) < 0 ? "dn" : "up"}`}>{idr(focus.net_profit, lang)}</span>}</div>
              <div className="split-metric"><span className="k">{t("Margin")}</span>{num(focus.net_margin) === null
                ? <span className="v tiny muted">{t("Not computed yet")}</span>
                : <span className={`v ${marginTone(num(focus.net_margin))}`}>{pct(focus.net_margin, lang)}</span>}</div>
              <div className="split-metric" title={products.data?.cvr_note}><span className="k">CVR</span><span className="v">{pct(focus.cvr, lang)}</span></div>
              <div className="split-metric"><span className="k">CTR</span><span className="v">{pct(focus.ctr, lang)}</span></div>
            </div>

            <p className="tiny">{t("Ads (est.)")}: {t("BLENDED estimate · LOW confidence")} — {products.data?.ad_cost_note}. CVR: {products.data?.cvr_note}.</p>
          </>
        )}
      </div>
    </div>
  );
}
