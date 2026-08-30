"use client";
import { useLang, useT } from "@/lib/i18n";
import { idr, int, num, pct, ratio } from "@/lib/format";
import type { Card, Overview } from "@/lib/types";
import { ErrorNote, Pill, Skeleton, Sparkline, ZoneHeader, statusTone } from "./ui";

const MAIN = ["net_profit", "gmv", "net_seller_revenue", "orders", "ad_spend", "net_margin"];
const SEC = ["reported_roas", "blended_roas", "aov", "cvr", "refund_rate", "settlement_coverage"];
const LABEL: Record<string, string> = {
  net_profit: "Net profit", gmv: "GMV", net_seller_revenue: "Net seller revenue", orders: "Orders",
  ad_spend: "Ad spend (GMV Max)", net_margin: "Net margin", reported_roas: "Reported ROAS", blended_roas: "Blended ROAS",
  aov: "AOV", cvr: "CVR (click→order)", refund_rate: "Refund rate", settlement_coverage: "Settlement coverage",
};

function KpiCard({ c, ov }: { c: Card; ov: Overview }) {
  const lang = useLang(), t = useT();
  const v = num(c.value);
  const fmt = (x: typeof c.value) => c.kind === "money" ? idr(x, lang) : c.kind === "pct" ? pct(x, lang) : c.kind === "ratio" ? ratio(x, lang) : int(x, lang);
  const tone = statusTone(c.status);
  const cls = c.kind === "money" || c.kind === "pct" ? (v !== null && v < 0 ? "dn" : "") : "";
  const chg = num(c.change_pct);
  const chgAbs = num(c.change_abs);
  const na = c.key === "reported_roas";
  return (
    <div className="card kpi" title={c.note ?? undefined}>
      <span className="k">{t(LABEL[c.key] ?? c.key)}</span>
      <span className={`n ${cls}`}>{na ? "—" : fmt(c.value)}</span>
      <span className="d">
        {na ? <Pill tone="gray">{t("NOT AVAILABLE — Ads API pending")}</Pill> : <>
          {chg !== null ? (
            <span className={tone === "good" ? "up" : tone === "bad" ? "dn" : "muted"}>{chg >= 0 ? "▲" : "▼"} {pct(c.change_pct, lang, { sign: true })} {t("vs previous")}</span>
          ) : chgAbs !== null && c.kind === "pct" ? (
            <span className={tone === "good" ? "up" : tone === "bad" ? "dn" : "muted"}>{chgAbs >= 0 ? "▲" : "▼"} {pct(c.change_abs, lang, { sign: true })}</span>
          ) : null}
          <Note c={c} ov={ov} />
        </>}
      </span>
      {c.sparkline.length > 1 && <Sparkline values={c.sparkline} tone={tone === "bad" ? "bad" : tone === "good" ? "good" : "accent"} />}
    </div>
  );
}

function Note({ c, ov }: { c: Card; ov: Overview }) {
  const lang = useLang(), t = useT();
  const tone = statusTone(c.status);
  switch (c.key) {
    case "net_profit": return <>{tone === "bad" ? <Pill tone="bad">{t("Losing")}</Pill> : tone === "good" ? <Pill tone="good">{t("Profitable")}</Pill> : null}<span className="tiny">{c.provisional ? t("provisional ≠ settled") : ""}</span></>;
    case "gmv": return <span>{int(ov.totals.units, lang)} {t("units")}</span>;
    case "net_seller_revenue": return <span>{t("after fees & refunds")}</span>;
    case "orders": return <span>{int(ov.totals.refunded_orders, lang)} {t("refunded")}</span>;
    case "ad_spend": {
      const m = /^([\d.]+) of net revenue$/.exec(c.note ?? "");
      return <><span className="dn">{m ? `${pct(m[1], lang)} ${t("of net revenue")}` : ""}</span><Pill tone="warn">{t("BLENDED estimate · LOW confidence")}</Pill></>;
    }
    case "net_margin": {
      const m = /^floor ([\d.]+)$/.exec(c.note ?? "");
      return <>{m && <span>{t("floor")} {pct(m[1], lang, { frac: 0 })}</span>}{tone === "bad" ? <Pill tone="bad">{t("Below floor")}</Pill> : tone === "good" ? <Pill tone="good">{t("Above floor")}</Pill> : null}</>;
    }
    case "blended_roas": {
      const m = /^break-even ([\d.]+)$/.exec(c.note ?? "");
      return <span>{m ? `${t("break-even")} ${ratio(m[1], lang)}` : t("net revenue / ad spend")} · <span className="tiny">{t("estimate")}</span></span>;
    }
    case "cvr": return <span>{t("orders / product clicks")}</span>;
    case "refund_rate": return <span>{t("refunded orders / orders")}</span>;
    case "settlement_coverage": return <Pill tone={tone === "good" ? "good" : "warn"}>{int(ov.totals.settled_orders, lang)} {t("settled")} · {int(ov.totals.provisional_orders, lang)} {t("provisional")}</Pill>;
    default: return c.note ? <span>{t(c.note)}</span> : null;
  }
}

const COMP = ["margin", "ad_efficiency", "conversion", "refunds", "data_quality"];
const COMP_LABEL: Record<string, string> = { margin: "Margin", ad_efficiency: "Ad efficiency", conversion: "Conversion", refunds: "Refunds", data_quality: "Data quality" };
const barColor = (v: number) => (v < 40 ? "var(--bad)" : v < 60 ? "var(--warn)" : v >= 75 ? "var(--good)" : "var(--accent)");

export default function Health({ ov, loading, error, reload }: { ov: Overview | null; loading: boolean; error: string | null; reload: () => void }) {
  const lang = useLang(), t = useT();
  const byKey = new Map((ov?.cards ?? []).map((c) => [c.key, c]));
  const health = ov?.health;
  const ue = ov?.unit_economics;
  const gradeCls = health?.grade === "POOR" ? "dn" : health?.grade === "GOOD" ? "up" : "";
  const ringColor = health ? barColor(health.score) : "var(--gray-soft)";
  return (
    <section className="zone" id="zone1">
      <ZoneHeader id="z1" eyebrow={t("1 · Business health")} title={t("Where the money went")} hint={t("Click any card for its diagnostic")} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !ov ? <Skeleton h={140} /> : ov && (
        <>
          <div className="kpis">{MAIN.map((k) => byKey.get(k)).filter((c): c is Card => !!c).map((c) => <KpiCard key={c.key} c={c} ov={ov} />)}</div>
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
              <div className="k lbl">{t("Unit economics · per unit")} {ue ? `· ${int(ue.units, lang)} ${t("units")}` : ""}</div>
              {ue ? (
                <table className="tbl" style={{ marginTop: 6 }}><tbody>
                  <tr><td>{t("Revenue after seller discount")}</td><td className="r">{idr(ue.revenue_per_unit, lang)}</td></tr>
                  <tr><td>{t("TikTok fees (commission, processing, logistics, affiliate)")}</td><td className="r dn">{idr(-(num(ue.fees_per_unit) ?? 0), lang)}</td></tr>
                  <tr><td>{t("COGS")}</td><td className="r dn">{idr(-(num(ue.cogs_per_unit) ?? 0), lang)}</td></tr>
                  <tr><td><b>{t("Contribution before ads")}</b></td><td className="r"><b>{idr(ue.contribution_per_unit, lang)}</b></td></tr>
                  <tr><td>{t("Ad cost per unit (blended)")} <span className="tiny">· {t("estimate")}</span></td><td className="r dn">{idr(-(num(ue.ad_cost_per_unit) ?? 0), lang)}</td></tr>
                  <tr><td><b>{t("Net per unit")}</b></td><td className={`r ${(num(ue.net_per_unit) ?? 0) < 0 ? "dn" : ""}`}><b>{idr(ue.net_per_unit, lang)}</b></td></tr>
                </tbody></table>
              ) : <div className="muted small" style={{ marginTop: 8 }}>—</div>}
            </div>
          </div>
          <div className="note"><b>{t("Notes")}:</b> {ov.notes.map((n) => t(n)).join(" ")}</div>
        </>
      )}
    </section>
  );
}
