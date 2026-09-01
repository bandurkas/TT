"use client";
import { useState } from "react";
import { EnHint, useLang, useT } from "@/lib/i18n";
import { dateTime, dayMon, idr, int, toISODate } from "@/lib/format";
import { apiPost } from "@/lib/api";
import type { Advertising, ManualAdIn, ManualAdOut } from "@/lib/types";
import { Pill } from "./ui";
import { recomputedText } from "@/lib/orders";

const jakartaToday = () => toISODate(new Date(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta" }).format(new Date()) + "T00:00:00Z"));

export default function AdCost({ adv, onApplied }: { adv: Advertising | null | undefined; onApplied: () => void }) {
  const lang = useLang(), t = useT();
  const [f, setF] = useState({ date: jakartaToday(), cost: "", sku_orders: "", gross_revenue: "", final: false, note: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<ManualAdOut | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null); setOk(null);
    const body: ManualAdIn = { date: f.date, cost: f.cost || "0", sku_orders: Number(f.sku_orders || 0), gross_revenue: f.gross_revenue || "0", final: f.final, note: f.note || null };
    try {
      const res = await apiPost<ManualAdOut>("/api/advertising/manual", body);
      setOk(res); setF((x) => ({ ...x, cost: "", sku_orders: "", gross_revenue: "", note: "" })); onApplied();
    } catch (x) { setErr(x instanceof Error ? x.message : String(x)); }
    setBusy(false);
  };
  const days = adv?.days ?? [];
  return (
    <div className="card" style={{ padding: 14 }}>
      <div className="k lbl">{t("Ad cost source")} · <span style={{ textTransform: "none", letterSpacing: 0 }}>{adv?.source ?? "—"}</span>{adv && <> · {int(adv.manual_days, lang)} {t("manual days")}</>}</div>
      <form className="form" style={{ padding: "10px 0 0", gridTemplateColumns: "repeat(6, 1fr)" }} onSubmit={submit} aria-label={t("Enter today's ad Cost from Ads Manager")}>
        <div className="wide" style={{ fontWeight: 600 }}>{t("Enter today's ad Cost from Ads Manager")} <Pill tone="warn">{t("Manual entry")}</Pill></div>
        <label>{t("Date")}<input type="date" required max={jakartaToday()} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
        <label>{t("Cost (IDR)")}<input type="number" min="0" step="1" required inputMode="numeric" value={f.cost} onChange={(e) => setF({ ...f, cost: e.target.value })} /></label>
        <label>{t("SKU orders")}<input type="number" min="0" step="1" inputMode="numeric" value={f.sku_orders} onChange={(e) => setF({ ...f, sku_orders: e.target.value })} /></label>
        <label>{t("Gross revenue")}<input type="number" min="0" step="1" inputMode="numeric" value={f.gross_revenue} onChange={(e) => setF({ ...f, gross_revenue: e.target.value })} /></label>
        <label>{t("Note (optional)")}<input maxLength={500} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
        <label style={{ textTransform: "none", letterSpacing: 0, justifyContent: "flex-end" }}><span style={{ display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={f.final} onChange={(e) => setF({ ...f, final: e.target.checked })} />{t("Day complete (final figures)")}</span></label>
        <div className="actions">
          {err && <span className="err" role="alert">{err}</span>}
          {ok && <span className="up small" style={{ marginRight: "auto" }}>{t("Applied")}{ok.recomputed ? ` — ${recomputedText(ok.recomputed.orders, lang)}` : ""}{ok.day?.partial ? ` · ${t("Partial")}` : ""}</span>}
          <button className="btn pri" disabled={busy}>{busy ? t("Applying…") : t("Apply")}</button>
        </div>
      </form>
      <div className="k lbl" style={{ marginTop: 10 }}>{t("Ad cost by day")}</div>
      <div className="scroll" style={{ maxHeight: 220, overflowY: "auto" }}>
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
    </div>
  );
}
