"use client";
import { EnHint, noteKey, useLang, useT } from "@/lib/i18n";
import { dateTime, idr, int, num, pct, ratio } from "@/lib/format";
import type { Card, Overview } from "@/lib/types";
import { kpiChange } from "@/lib/kpi";
import { orderMoney } from "@/lib/orders";
import { ErrorNote, Pill, Skeleton, Sparkline, ZoneHeader, statusTone } from "./ui";
import AdCost from "./AdCost";
import Costs from "./Costs";
import AdvertisingSource from "./AdvertisingSource";
import WhatIf, { whatIfNet } from "./WhatIf";
import { useState } from "react";

const MAIN = ["net_profit", "gmv", "net_seller_revenue", "orders", "ad_spend", "net_margin"];
const SEC = ["reported_roas", "blended_roas", "aov", "cvr", "refund_rate", "settlement_coverage"];
const LABEL: Record<string, string> = {
  net_profit: "Net profit", gmv: "GMV", net_seller_revenue: "Net seller revenue", orders: "Orders",
  ad_spend: "Ad spend (GMV Max)", net_margin: "Net margin", reported_roas: "Reported ROAS", blended_roas: "Blended ROAS",
  aov: "AOV", cvr: "CVR (click→order)", refund_rate: "Refund rate", settlement_coverage: "Settlement coverage",
};

const EXPLAIN: Record<string, string> = {
  net_profit: "Revenue after TikTok fees and refunds, minus product costs and allocated advertising. Preliminary fees may still change. This is profit by order date, not cash received.",
  gmv: "Total order value before fees and costs. GMV is sales volume, not profit.",
  net_seller_revenue: "Revenue after platform fees, refunds and adjustments. Product costs and advertising have not yet been deducted.",
  orders: "Orders included in the profit calculation, excluding cancelled orders. Refunds are shown separately.",
  ad_spend: "Shop-level GMV Max deductions from payouts. Allocation to orders is estimated (BLENDED, LOW confidence); spend by campaign requires the Ads API.",
  net_margin: "Net profit divided by net seller revenue. The threshold describes the current level; the arrow separately shows the change from the comparison period.",
  reported_roas: "TikTok-reported return on ad spend is unavailable until Ads data is connected. Missing data is not zero.",
  blended_roas: "Net seller revenue divided by shop ad spend. This includes all shop revenue, so it is not proof that advertising generated every sale. Break-even is the ratio needed to cover recorded costs.",
  aov: "GMV divided by the number of orders. A larger average order does not necessarily mean more profit.",
  cvr: "Video-attributed orders divided by estimated video clicks (views × CTR). This does not measure conversion for all shop traffic.",
  refund_rate: "Refunded orders divided by all orders in the calculation. A rising refund rate is deterioration, even when the current rate is below the warning threshold.",
  settlement_coverage: "Orders with final settlement data divided by final plus preliminary orders. Fees on preliminary orders are estimated. Final settlement does not mean the money has reached your bank.",
};

function KpiCard({ c, ov, whatIf }: { c: Card; ov: Overview; whatIf?: number | null }) {
  const lang = useLang(), t = useT();
  const v = num(c.value);
  const fmt = (x: typeof c.value) => c.kind === "money" ? idr(x, lang) : c.kind === "pct" ? pct(x, lang) : c.kind === "ratio" ? ratio(x, lang) : int(x, lang);
  const tone = statusTone(c.status);
  const cls = c.kind === "money" || c.kind === "pct" ? (v !== null && v < 0 ? "dn" : "") : "";
  const change = kpiChange(c);
  const na = c.key === "reported_roas" && v === null;
  const explanation = EXPLAIN[c.key];
  const wi = whatIf ?? null;
  const wiCls = wi !== null && wi < 0 ? "dn" : "";
  return (
    <div className={`card kpi ${wi !== null ? "wi" : ""}`}>
      <span className="k">{c.key === "ad_spend" ? (lang === "ru" ? "Расход рекламы · Cost" : "Advertising Cost") : t(LABEL[c.key] ?? c.key)}
        {wi !== null && <span className="wi-tag">{t("what if")}</span>}</span>
      <span className={`n ${wi !== null ? wiCls : cls}`}>{wi !== null ? fmt(String(wi)) : na ? "—" : fmt(c.value)}</span>
      {wi !== null && (() => {
        const base = num(c.value);
        const d = base === null ? null : wi - base;
        return <>
          {d !== null && d !== 0 && <div className={`kpi-change ${d > 0 ? "up" : "dn"}`}>
            {d > 0 ? "▲" : "▼"} {c.kind === "pct" ? `${pct(Math.abs(d), lang, { frac: 2 })} ${t("pp")}` : fmt(String(Math.abs(d)))} {t("vs actual")}
          </div>}
          <div className="kpi-previous">{t("Actual")}: <b>{fmt(c.value)}</b></div>
        </>;
      })()}
      {change && !na && wi === null && <div className={`kpi-change ${change.tone}`}>
        {change.direction > 0 ? "▲" : change.direction < 0 ? "▼" : "="}{" "}
        {change.points ? `${pct(change.raw, lang, { sign: true }).replace("%", "")} ${t("pp")}` : pct(change.raw, lang, { sign: true })} {t("vs previous")}
      </div>}
      {!na && c.prev !== null && wi === null && <div className="kpi-previous">{t("Previously")}: {fmt(c.prev)}</div>}
      {wi === null && <div className="d">{na ? <Pill tone="gray">{t("Ads data not connected")}</Pill> : <Note c={c} ov={ov} />}</div>}
      {wi === null && c.sparkline.length > 1 && <Sparkline values={c.sparkline} tone={tone === "bad" ? "bad" : tone === "good" ? "good" : "accent"} />}
      {explanation && <details className="kpi-help">
        <summary aria-label={`${t("How to read this")}: ${t(LABEL[c.key] ?? c.key)}`}>{t("How to read this")}</summary>
        <p>{c.key === "ad_spend" ? (lang === "ru" ? "Cost из дневного рекламного отчёта. Платежи GMV Pay показаны отдельно. Расход не теряется в дни без заказов." : "Cost from the daily ad report. GMV Pay is separate. Days without orders remain included.") : c.key === "net_profit" ? (lang === "ru" ? "Прибыль до рекламы по датам заказов минус Cost по датам расхода. Комиссии могут быть предварительными; сверка рекламных налогов и кредитов ещё не завершена." : "Contribution by order date less Cost by spending date. Fees may be preliminary; ad taxes and credits are not yet reconciled.") : t(explanation)}</p>
      </details>}
    </div>
  );
}

function Note({ c, ov }: { c: Card; ov: Overview }) {
  const lang = useLang(), t = useT();
  const tone = statusTone(c.status);
  switch (c.key) {
    case "net_profit": return <>{tone === "bad" ? <Pill tone="bad">{t("Losing")}</Pill> : tone === "good" ? <Pill tone="good">{t("Profitable")}</Pill> : null}{c.provisional && <span>{t("Some fees are preliminary")}</span>}</>;
    case "gmv": return <span>{int(c.meta?.units ?? ov.totals.units, lang)} {t("units")}</span>;
    case "net_seller_revenue": return <span>{t("after fees & refunds")}</span>;
    case "orders": return <span>{int(c.meta?.refunded ?? ov.totals.refunded_orders, lang)} {t("refunded")}</span>;
    case "ad_spend": {
      const share = c.meta?.ad_share ?? null;
      return <>{share !== null && <span>{pct(share, lang)} {t("of net revenue")}</span>}<Pill tone="warn">{lang === "ru" ? (c.value === null ? "Отчёт неполный" : c.provisional ? "Неполный день" : "Источник: выгрузка") : (c.value === null ? "Missing report" : c.provisional ? "Partial day" : "Export source")}</Pill></>;
    }
    case "net_margin": {
      const floor = c.meta?.floor ?? null;
      return <>{floor !== null && <span>{t("floor")} {pct(floor, lang, { frac: 0 })}</span>}{tone === "bad" ? <Pill tone="bad">{t("Below floor")}</Pill> : tone === "good" ? <Pill tone="good">{t("Above floor")}</Pill> : null}</>;
    }
    case "blended_roas": {
      const be = c.meta?.break_even ?? null;
      return <span>{be !== null ? `${t("break-even")} ${ratio(be, lang)}` : t("net revenue / ad spend")} · <span className="tiny">{t("estimate")}</span></span>;
    }
    case "cvr": return <span>{t("video orders / derived clicks")}</span>;
    case "refund_rate": return <span>{t("refunded orders / orders")}</span>;
    case "settlement_coverage": return <><Pill tone={tone === "good" ? "good" : "warn"}>{int(c.meta?.settled ?? ov.totals.settled_orders, lang)} {t("final orders")}</Pill><span>{int(c.meta?.provisional ?? ov.totals.provisional_orders, lang)} {t("preliminary orders")}</span><span>{t("Final fees, not bank payouts")}</span></>;
    default: return c.note ? <span>{t(c.note)}</span> : null;
  }
}

const COMP = ["margin", "ad_efficiency", "conversion", "refunds", "data_quality"];
const COMP_LABEL: Record<string, string> = { margin: "Margin", ad_efficiency: "Ad efficiency", conversion: "Conversion", refunds: "Refunds", data_quality: "Data quality" };
const barColor = (v: number) => (v < 40 ? "var(--bad)" : v < 60 ? "var(--warn)" : v >= 75 ? "var(--good)" : "var(--accent)");

interface HealthProps { ov: Overview | null; loading: boolean; error: string | null; reload: () => void; query: string; tick: number; onAdApplied: () => void; onCostApplied: () => void }
export default function Health({ ov, loading, error, reload, query, tick, onAdApplied, onCostApplied }: HealthProps) {
  const lang = useLang(), t = useT();
  const byKey = new Map((ov?.cards ?? []).map((c) => [c.key, c]));
  const health = ov?.health;
  const ue = ov?.unit_economics;
  const gradeCls = health?.grade === "POOR" ? "dn" : health?.grade === "GOOD" ? "up" : "";
  const ringColor = health ? barColor(health.score) : "var(--gray-soft)";
  const previousOrders = num(byKey.get("orders")?.prev);
  const money = (value: string | null | undefined) => orderMoney(value, lang, ov?.shop.currency);
  const [pieces, setPieces] = useState("5");
  const [perPiece, setPerPiece] = useState("");
  const nPieces = Number(pieces) > 0 ? Number(pieces) : 0;
  const wiUnit = perPiece === "" || !nPieces ? null : Number(perPiece) * nPieces;
  const wiNet = whatIfNet(ue, byKey.get("net_profit")?.value, wiUnit);
  const wiBase = num(byKey.get("net_seller_revenue")?.value);
  const wiMargin = wiNet !== null && wiBase ? wiNet / wiBase : null;
  const wiFor = (k: string) => (k === "net_profit" ? wiNet : k === "net_margin" ? wiMargin : null);
  const [adOpen, setAdOpen] = useState(false);
  const [costOpen, setCostOpen] = useState(false);
  const adv = ov?.advertising;
  const lastDay = adv?.days?.length ? adv.days[adv.days.length - 1] : null;
  const gap = adv?.status === "missing" ? "bad" : adv?.status === "partial" ? "warn" : null;
  const expense = (value: string | null | undefined) =>
    value == null ? "—" : money(value.startsWith("-") ? value.slice(1) : `-${value}`);
  return (
    <section className="zone" id="zone1">
      <ZoneHeader id="z1" eyebrow={t("1 · Business health")} title={t("Where the money went")} hint={t("Open “How to read this” for definitions")} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !ov ? <Skeleton h={140} /> : ov && (
        <>
          {gap && !adOpen && (
            <div className={`banner ${gap}`} role="status">
              <b>{gap === "bad" ? t("Advertising Cost for this period has not been entered") : t("A day in this period is still open")}</b>
              <span>{gap === "bad" ? t("Profit is overstated until it is.") : t("Cost and profit will still change.")}</span>
              {!!adv?.missing_days?.length && <span className="mono tiny">{adv.missing_days.slice(0, 5).join(", ")}{adv.missing_days.length > 5 ? "…" : ""}</span>}
              <span className="sp" style={{ flex: 1 }} />
              <button className="btn sm" onClick={() => setAdOpen(true)}>{t("Enter Cost")}</button>
            </div>
          )}
          <div>
            <div className={`ctrl ${adOpen ? "on" : ""}`}>
              <span className="lab">{lang === "ru" ? "Реклама" : "Advertising"}</span>
              <b>{idr(adv?.cost, lang)}</b>
              <span>· {adv?.source ?? "—"}</span>
              {lastDay?.observed_at && <span className="tiny">· {t("last")}: {dateTime(lastDay.observed_at, lang, ov.shop.timezone)}</span>}
              <span className="sp" />
              <button className="btn sm" aria-expanded={adOpen} onClick={() => setAdOpen(!adOpen)}>{adOpen ? t("Done") : t("Change")}</button>
            </div>
            {adOpen && <div className="ctrl-body"><AdCost adv={ov.advertising} onApplied={onAdApplied} timezone={ov.shop.timezone} /></div>}
          </div>
          <div>
            <div className={`ctrl ${costOpen ? "on" : ""}`}>
              <span className="lab">{t("Product cost")}</span>
              <b>{idr(ue?.cogs_per_unit, lang)}</b>
              <span>{t("per unit")}{nPieces > 0 && num(ue?.cogs_per_unit) !== null && <> · {idr(num(ue!.cogs_per_unit)! / nPieces, lang)} {t("per piece")}</>}</span>
              {wiUnit !== null && <span className="wi-tag">{t("what if")} {idr(wiUnit, lang)}</span>}
              <span className="sp" />
              {wiUnit !== null && <button className="btn sm" onClick={() => setPerPiece("")}>{t("Reset")}</button>}
              <button className="btn sm" aria-expanded={costOpen} onClick={() => setCostOpen(!costOpen)}>{costOpen ? t("Done") : t("What if…")}</button>
            </div>
            {costOpen && <div className="ctrl-body">
              <WhatIf ue={ue ?? null} netProfit={byKey.get("net_profit")?.value ?? null} pieces={pieces} setPieces={setPieces} perPiece={perPiece} setPerPiece={setPerPiece} />
            </div>}
          </div>
          <AdvertisingSource data={ov.advertising} currency={ov.shop.currency} />
          <div className="note kpi-context">
            <span>{t("Comparison period")}: {ov.compare.start} — {ov.compare.end}.</span>{" "}
            <span>{t("Rate changes use percentage points (pp); other changes use percent.")}</span>
            {previousOrders !== null && previousOrders < 5 && <strong className="kpi-sample">{t("Few orders in the comparison period")}: {int(previousOrders, lang)}. {t("Large changes may reflect a small sample, not a stable trend.")}</strong>}
          </div>
          <div className="kpis">{MAIN.map((k) => byKey.get(k)).filter((c): c is Card => !!c).map((c) => <KpiCard key={c.key} c={c} ov={ov} whatIf={wiFor(c.key)} />)}</div>
          <div className="sec">{SEC.map((k) => byKey.get(k)).filter((c): c is Card => !!c).map((c) => <KpiCard key={c.key} c={c} ov={ov} />)}</div>
          <div className="health">
            <div className="card score">
              <div className="ring">
                <svg viewBox="0 0 84 84" aria-hidden="true">
                  <circle cx="42" cy="42" r="36" fill="none" stroke="var(--gray-soft)" strokeWidth="8" />
                  <circle cx="42" cy="42" r="36" fill="none" stroke={ringColor} strokeWidth="8" strokeDasharray="226" strokeDashoffset={226 - (226 * (health?.score ?? 0)) / 100} strokeLinecap="round" transform="rotate(-90 42 42)" />
                </svg>
                <div className="c">{health?.score ?? "—"}</div>
              </div>
              <div>
                <div style={{ font: "700 15px Manrope, sans-serif", marginBottom: 8 }}>{t("Profit health")} {health?.score ?? "—"}/100 · <span className={gradeCls}>{health ? t(health.grade) : "—"}</span></div>
                <div className="bars">
                  {COMP.map((k) => {
                    const v = health?.components[k] ?? null;
                    return (
                      <div className="bar" key={k}><span>{t(COMP_LABEL[k])}</span><i><b style={{ width: `${v ?? 0}%`, background: v === null ? "var(--gray-soft)" : barColor(v) }} /></i><span>{v ?? "—"}</span></div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="card pace">
              <div className="k lbl">{t("Unit economics · per unit")} {ue ? `· ${int(ue.units, lang)} ${t("units")}` : ""}{wiUnit !== null && <span className="wi-tag">{t("what if")}</span>}</div>
              {ue ? (
                <><table className="tbl" style={{ marginTop: 6 }}><tbody>
                  <tr><td>{lang === "ru" ? "Выручка с учётом возвратов и корректировок, до комиссий" : "Revenue after refunds and adjustments, before fees"}</td><td className="r">{money(ue.revenue_per_unit)}</td></tr>
                  <tr><td>{t("TikTok fees (commission, processing, logistics, affiliate)")}</td><td className="r dn">{expense(ue.fees_per_unit)}</td></tr>
                  <tr className={wiUnit !== null ? "wi-row" : ""}><td>{lang === "ru" ? "Товар, упаковка и прочие внесённые затраты" : "Product, packaging and other entered costs"}</td><td className="r dn">{expense(wiUnit !== null ? String(wiUnit) : ue.cogs_per_unit)}</td></tr>
                  {!!num(ue.contribution_rounding_per_unit) && <tr><td>{lang === "ru" ? "Округление на единицу" : "Per-unit rounding"}</td><td className="r">{money(ue.contribution_rounding_per_unit)}</td></tr>}
                  <tr className={wiUnit !== null ? "wi-row" : ""}><td><b>{t("Contribution before ads")}</b></td><td className="r"><b>{money(wiUnit !== null ? String(num(ue.revenue_per_unit)! - num(ue.fees_per_unit)! - wiUnit) : ue.contribution_per_unit)}</b></td></tr>
                  <tr><td>{t("Ad cost per unit (blended)")} <span className="tiny">· {t("estimate")}</span></td><td className="r dn">{expense(ue.ad_cost_per_unit)}</td></tr>
                  {!!num(ue.rounding_per_unit) && <tr><td>{lang === "ru" ? "Округление на единицу" : "Per-unit rounding"}</td><td className="r">{money(ue.rounding_per_unit)}</td></tr>}
                  <tr className={wiUnit !== null ? "wi-row" : ""}><td><b>{t("Net per unit")}</b></td><td className={`r ${(wiUnit !== null ? wiNet !== null && wiNet < 0 : (num(ue.net_per_unit) ?? 0) < 0) ? "dn" : ""}`}><b>{money(wiUnit !== null && wiNet !== null && ue.units ? String(wiNet / ue.units) : ue.net_per_unit)}</b></td></tr>
                </tbody></table>
                  <p className="small muted">{lang === "ru" ? "Выручка и товарные расходы — по заказам периода; реклама — весь Cost периода, включая дни без заказов. Здесь среднее на единицу, а не точная прибыль конкретного заказа. Выручка учитывает возвраты и корректировки и отличается от GMV." : "Revenue and product costs use period orders; advertising includes all period Cost, even on days without orders. These are per-unit averages, not exact individual order profits. Revenue includes refunds and adjustments and differs from GMV."}</p>
                  {(!!num(ue.calculation_difference) || !!num(ue.contribution_difference)) && <p className="banner bad">{lang === "ru" ? "Исходные суммы не сходятся. Проверьте расчёты заказов; это не погрешность округления." : "Source amounts do not reconcile. Check order calculations; this is not a rounding difference."}</p>}
                  <a href="#zorders">{lang === "ru" ? "Открыть подробный журнал заказов →" : "Open detailed order journal →"}</a>
                </>
              ) : <div className="muted small" style={{ marginTop: 8 }}>—</div>}
            </div>
          </div>
          <Costs query={query} tick={tick} onApplied={onCostApplied} />
          <div className="note"><b>{t("Notes")}:</b> {ov.notes.map((n, i) => { const k = noteKey(n); return <span key={i}>{k ? t(k) : n}{!k && <EnHint lang={lang} />} </span>; })}</div>
        </>
      )}
    </section>
  );
}
