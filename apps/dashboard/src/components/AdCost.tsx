"use client";
import { useState } from "react";
import { EnHint, useLang, useT } from "@/lib/i18n";
import { dateTime, dayMon, idr, int, toISODate } from "@/lib/format";
import { shopToday } from "@/lib/period";
import { ApiError, apiPost } from "@/lib/api";
import type { Advertising, ManualAdIn, ManualAdOut } from "@/lib/types";
import { Pill } from "./ui";
import { recomputedText } from "@/lib/orders";

export default function AdCost({ adv, onApplied, timezone }: { adv: Advertising | null | undefined; onApplied: () => void; timezone?: string }) {
  const lang = useLang(), t = useT();
  const today = toISODate(shopToday(timezone));   // the business day is the shop's, never the browser's
  const [f, setF] = useState({ date: today, cost: "", sku_orders: "", gross_revenue: "", final: false, note: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Set when the server refused figures that look like a period's totals, or that would thin out a
  // fuller record. Nothing is saved until the operator re-sends the same figures with confirm.
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const [ok, setOk] = useState<ManualAdOut | null>(null);
  const post = async (confirm: boolean) => {
    setBusy(true); setErr(null); setOk(null);
    // An empty field is "leave it alone", not zero — the day's Cost is re-entered several times.
    const body: ManualAdIn = { date: f.date, cost: f.cost || "0", sku_orders: f.sku_orders === "" ? null : Number(f.sku_orders), gross_revenue: f.gross_revenue === "" ? null : f.gross_revenue, final: f.final, note: f.note || null, ...(confirm ? { confirm: true } : {}) };
    try {
      const res = await apiPost<ManualAdOut>("/api/advertising/manual", body);
      setOk(res); setNeedsConfirm(false); setF((x) => ({ ...x, cost: "", sku_orders: "", gross_revenue: "", note: "" })); onApplied();
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
      setNeedsConfirm(x instanceof ApiError && x.confirmable);
    }
    setBusy(false);
  };
  const submit = (e: React.FormEvent) => { e.preventDefault(); void post(false); };
  // Any edit invalidates the warning: the operator is now confirming different figures.
  const edit = (patch: Partial<typeof f>) => { setF({ ...f, ...patch }); setNeedsConfirm(false); setErr(null); };
  const days = adv?.days ?? [];
  const last = days.length ? days[days.length - 1] : null;
  const onFile = days.find((d) => d.date === f.date);   // an empty input keeps whatever this holds
  const keep = (v: string | number | null | undefined) => (onFile && v !== null && v !== undefined ? `${t("keep")} ${v}` : undefined);
  return (
    <div className="card" style={{ padding: 14 }}>
      <form className="form" style={{ padding: "10px 0 0", gridTemplateColumns: "repeat(6, 1fr)" }} onSubmit={submit} aria-label={t("Enter today's ad Cost from Ads Manager")}>
        <div className="wide" style={{ fontWeight: 600 }}>{t("Enter today's ad Cost from Ads Manager")} <Pill tone="warn">{t("Manual entry")}</Pill> <Pill tone="gray">{t("One day only — not a date range")}</Pill></div>
        <div className="wide tiny">{t("Ads Manager shows the date range you selected. Select this one day there before copying the figures.")}</div>
        <label>{t("Date")}<input type="date" required max={today} value={f.date} onChange={(e) => edit({ date: e.target.value })} /></label>
        <label>{t("Cost (IDR)")}<input type="number" min="0" step="1" required inputMode="numeric" value={f.cost} onChange={(e) => edit({ cost: e.target.value })} /></label>
        <label>{t("SKU orders")}<input type="number" min="0" step="1" inputMode="numeric" placeholder={keep(onFile?.sku_orders)} value={f.sku_orders} onChange={(e) => edit({ sku_orders: e.target.value })} /></label>
        <label>{t("Gross revenue")}<input type="number" min="0" step="1" inputMode="numeric" placeholder={keep(onFile?.gross_revenue)} value={f.gross_revenue} onChange={(e) => edit({ gross_revenue: e.target.value })} /></label>
        <label>{t("Note (optional)")}<input maxLength={500} value={f.note} onChange={(e) => edit({ note: e.target.value })} /></label>
        <label className="inline"><input type="checkbox" checked={f.final} onChange={(e) => edit({ final: e.target.checked })} />{t("Day complete (final figures)")}</label>
        <div className="actions">
          {err && <span className="err" role="alert">{err}</span>}
          {needsConfirm && <button type="button" className="btn" disabled={busy} onClick={() => void post(true)}>{t("Save as entered")}</button>}
          {ok && <span className="up small" style={{ marginRight: "auto" }}>{t("Applied")}{ok.recomputed ? ` — ${recomputedText(ok.recomputed.orders, lang)}` : ""}{ok.day?.partial ? ` · ${t("Partial")}` : ""}</span>}
          <button className="btn pri" disabled={busy}>{busy ? t("Applying…") : t("Apply")}</button>
        </div>
      </form>
      <details className="drawer">
        <summary><span className="k lbl">{t("Ad cost by day")}</span><span className="tiny">{int(days.length, lang)} {t("days")}{last && <> · {t("last")}: {dayMon(last.date, lang)}</>}</span></summary>
      <div className="scroll" style={{ maxHeight: 260, overflowY: "auto" }}>
        <table className="tbl">
          <thead><tr><th>{t("Date")}</th><th className="r">{t("Cost (IDR)")}</th><th className="r">{t("SKU orders")}</th><th className="r">{t("Gross revenue")}</th><th>{t("Source")}</th><th>{t("Status")}</th><th>{t("Observed")}</th></tr></thead>
          <tbody>
            {days.length === 0 && <tr><td colSpan={7} className="empty">{t("No ad-cost days in this period.")}</td></tr>}
            {days.map((d) => (
              <tr key={d.date} title={d.note ?? undefined}>
                <td>{dayMon(d.date, lang)}</td>
                <td className="r">{idr(d.cost, lang)}</td>
                <td className="r">{int(d.sku_orders, lang)}</td>
                <td className="r">{idr(d.gross_revenue, lang)}</td>
                <td>{d.source === "manual_entry" ? <Pill tone="warn">{t("Manual entry")}</Pill> : <Pill tone="info">{t("Campaign overview export")}</Pill>}</td>
                <td>{d.partial ? <Pill tone="gray">{t("Partial")} · {t("still moving")}</Pill> : <Pill tone="good">{t("Final")}</Pill>}</td>
                <td className="tiny">{dateTime(d.observed_at, lang)}{d.note ? ` · ${d.note}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tiny" style={{ marginTop: 8 }}>{t(adv?.entry_note ?? "Manual entry = operator-transcribed Ads Manager figures; replaced only by a newer observation; superseded automatically once the Ads API is connected.")} · {t("BLENDED estimate · LOW confidence")}{adv?.entry_note && t(adv.entry_note) === adv.entry_note && <EnHint lang={lang} />}</div>
      </details>
    </div>
  );
}
