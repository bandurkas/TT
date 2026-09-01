"use client";
import { useEffect, useState } from "react";
import { EnHint, useLang, useT } from "@/lib/i18n";
import { dayMon, idr, int, num } from "@/lib/format";
import { apiPatch, apiPost, useApi } from "@/lib/api";
import type { CostLot, CostSku, CostWriteOut, Costs as CostsT, LotIn, LotPatch } from "@/lib/types";
import { recomputedText } from "@/lib/orders";
import { ErrorNote, Pill, Skeleton } from "./ui";

const lotState = (l: CostLot, skus: CostSku[]): { label: string; tone: "good" | "gray" | "warn" | "bad" } => {
  if (!l.active) return { label: "inactive", tone: "bad" };
  if (l.remaining === 0) return { label: "sold out", tone: "gray" };
  if (skus.some((s) => s.source === "lot" && s.lot_id === l.id)) return { label: "active", tone: "good" };
  if (l.consumed === undefined) return { label: "queued", tone: "warn" };
  return { label: "active", tone: "good" };
};

const EMPTY_LOT = { scope: "all" as LotIn["scope"], product_id: "", sku_id: "", received_on: "", unit_cost: "", quantity: "", note: "" };

export default function Costs({ query, tick, onApplied }: { query: string; tick: number; onApplied: () => void }) {
  const lang = useLang(), t = useT();
  const c = useApi<CostsT>(`/api/costs${query}`, tick);
  const [locked, setLocked] = useState(true);
  const [def, setDef] = useState("");
  const [lot, setLot] = useState(EMPTY_LOT);
  const [edit, setEdit] = useState<{ id: number; received_on: string; unit_cost: string; quantity: string; note: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [openSku, setOpenSku] = useState<number | null>(null);
  useEffect(() => { if (locked) setDef(c.data?.default_cogs_per_unit ?? ""); }, [c.data, locked]);
  const run = async (fn: () => Promise<CostWriteOut>) => {
    setBusy(true); setErr(null); setOk(null);
    try {
      const r = await fn();
      setOk(`${t("Applied")} — ${recomputedText(r.recomputed.orders, lang)}`);
      setLocked(true); setEdit(null); setLot(EMPTY_LOT); onApplied();
    } catch (x) { setErr(x instanceof Error ? x.message : String(x)); }
    setBusy(false);
  };
  const d = c.data;
  const products = d ? [...new Map(d.skus.map((s) => [s.product_id, s.product_title])).entries()] : [];
  const ro = locked || busy;
  return (
    <div className="card" style={{ padding: 14 }}>
      <div className="panel-h">
        <span className="k lbl">{t("Product cost")} · {t("FIFO")}</span>
        <label className={`lockbox ${locked ? "on" : ""}`}><input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} aria-label={t("Locked")} />{locked ? <>{t("Locked")} <span className="locked-hint">· {t("Unlock to edit")}</span></> : t("Editing")}</label>
      </div>
      {c.error && <ErrorNote error={c.error} onRetry={c.reload} />}
      {err && <div className="banner bad" role="alert" style={{ marginTop: 8 }}>{err}</div>}
      {ok && <div className="banner warn up" style={{ marginTop: 8, background: "var(--good-soft)", color: "var(--good)" }}>{ok}</div>}
      {c.loading && !d ? <Skeleton h={120} /> : d && (
        <>
          <div style={{ display: "flex", gap: 8, alignItems: "end", marginTop: 10, flexWrap: "wrap" }}>
            <label className="field">{t("Default cost per unit")}
              <input type="number" min="0" step="1" inputMode="numeric" readOnly={ro} aria-readonly={ro} value={def} onChange={(e) => setDef(e.target.value)} style={{ width: 140 }} /></label>
            <span className="small" style={{ paddingBottom: 8 }}>{idr(d.default_cogs_per_unit, lang)}</span>
            {!locked && <button className="btn sm" disabled={busy} onClick={() => run(() => apiPost<CostWriteOut>("/api/costs/default", { default_cogs_per_unit: def === "" ? null : def }))}>{t("Set")}</button>}
          </div>
          <div className="k lbl" style={{ marginTop: 12 }}>{t("Lots (purchase batches)")}</div>
          <div className="scroll"><table className="tbl">
            <thead><tr><th>#</th><th>{t("Scope")}</th><th>{t("Received on")}</th><th className="r">{t("Unit cost")}</th><th className="r">{t("Quantity (optional)")}</th><th className="r">{t("consumed")} / {t("remaining")}</th><th>{t("Status")}</th><th></th></tr></thead>
            <tbody>
              {d.lots.length === 0 && <tr><td colSpan={8} className="empty">{t("No lots yet.")}</td></tr>}
              {d.lots.map((l) => {
                const st = lotState(l, d.skus);
                const scope = l.scope === "all" ? t("all SKUs") : l.scope === "product" ? `${t("product")} ${d.skus.find((s) => s.product_id === l.product_id)?.product_title ?? l.product_id}` : `${t("sku")} ${d.skus.find((s) => s.sku_id === l.sku_id)?.sku_title ?? l.sku_id}`;
                const shared = l.scope !== "sku" && l.quantity !== null && l.shared_skus ? l.shared_skus : null;
                const e = edit?.id === l.id ? edit : null;
                return (
                  <tr key={l.id} title={l.note ?? undefined}>
                    <td className="mono">{l.id}</td><td style={{ whiteSpace: "normal" }}>{scope}{shared !== null && <><br /><span className="tiny">{t("shared batch across")} {int(shared, lang)} SKU</span></>}</td>
                    <td>{e ? <input type="date" value={e.received_on} onChange={(x) => setEdit({ ...e, received_on: x.target.value })} /> : dayMon(l.received_on, lang)}</td>
                    <td className="r">{e ? <input type="number" min="0" step="1" value={e.unit_cost} style={{ width: 110 }} onChange={(x) => setEdit({ ...e, unit_cost: x.target.value })} /> : idr(l.unit_cost, lang)}</td>
                    <td className="r">{e ? <input type="number" min="0" step="1" value={e.quantity} placeholder={t("Clear quantity (0)")} style={{ width: 110 }} onChange={(x) => setEdit({ ...e, quantity: x.target.value })} /> : l.quantity === null ? <span className="tiny">{t("until next lot")}</span> : int(l.quantity, lang)}</td>
                    <td className="r">{l.consumed === undefined ? "—" : `${int(l.consumed, lang)} / ${l.remaining === null || l.remaining === undefined ? "∞" : int(l.remaining, lang)}`}</td>
                    <td><Pill tone={st.tone}>{t(st.label)}</Pill></td>
                    <td>{!locked && (e ? (
                      <span style={{ display: "flex", gap: 4 }}>
                        <button className="btn xs pri" disabled={busy} onClick={() => { const b: LotPatch = { received_on: e.received_on, unit_cost: e.unit_cost, note: e.note || null }; if (e.quantity !== "") b.quantity = Number(e.quantity); run(() => apiPatch<CostWriteOut>(`/api/costs/lots/${l.id}`, b)); }}>{t("Save")}</button>
                        <button className="btn xs" onClick={() => setEdit(null)}>{t("Cancel")}</button>
                      </span>
                    ) : (
                      <span style={{ display: "flex", gap: 4 }}>
                        <button className="btn xs" disabled={busy} onClick={() => setEdit({ id: l.id, received_on: l.received_on, unit_cost: l.unit_cost, quantity: l.quantity === null ? "" : String(l.quantity), note: l.note ?? "" })}>{t("Edit")}</button>
                        <button className="btn xs" disabled={busy} onClick={() => run(() => apiPatch<CostWriteOut>(`/api/costs/lots/${l.id}`, { active: !l.active }))}>{l.active ? t("Deactivate") : t("Activate")}</button>
                      </span>
                    ))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
          {!locked && (
            <form className="form" style={{ padding: "10px 0 0", gridTemplateColumns: "repeat(6, 1fr)" }} onSubmit={(e) => { e.preventDefault(); const b: LotIn = { scope: lot.scope, received_on: lot.received_on, unit_cost: lot.unit_cost, quantity: lot.quantity ? Number(lot.quantity) : null, note: lot.note || null, product_id: lot.scope === "product" ? Number(lot.product_id) : null, sku_id: lot.scope === "sku" ? Number(lot.sku_id) : null }; run(() => apiPost<CostWriteOut>("/api/costs/lots", b)); }} aria-label={t("Add lot")}>
              <div className="wide" style={{ fontWeight: 600 }}>{t("Add lot")}</div>
              <label>{t("Scope")}<select value={lot.scope} onChange={(e) => setLot({ ...lot, scope: e.target.value as LotIn["scope"] })}><option value="all">{t("all SKUs")}</option><option value="product">{t("product")}</option><option value="sku">{t("sku")}</option></select></label>
              {lot.scope === "product" && <label>{t("Choose product")}<select required value={lot.product_id} onChange={(e) => setLot({ ...lot, product_id: e.target.value })}><option value="">—</option>{products.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>}
              {lot.scope === "sku" && <label>{t("Choose SKU")}<select required value={lot.sku_id} onChange={(e) => setLot({ ...lot, sku_id: e.target.value })}><option value="">—</option>{d.skus.map((s) => <option key={s.sku_id} value={s.sku_id}>{s.product_title} · {s.sku_title ?? s.external_sku_id}</option>)}</select></label>}
              <label>{t("Received on")}<input type="date" required value={lot.received_on} onChange={(e) => setLot({ ...lot, received_on: e.target.value })} /></label>
              <label>{t("Unit cost")}<input type="number" min="0" step="1" required inputMode="numeric" value={lot.unit_cost} onChange={(e) => setLot({ ...lot, unit_cost: e.target.value })} /></label>
              <label>{t("Quantity (optional)")}<input type="number" min="1" step="1" inputMode="numeric" value={lot.quantity} onChange={(e) => setLot({ ...lot, quantity: e.target.value })} /></label>
              <label>{t("Note (optional)")}<input maxLength={500} value={lot.note} onChange={(e) => setLot({ ...lot, note: e.target.value })} /></label>
              <div className="actions"><button className="btn pri" disabled={busy}>{busy ? t("Applying…") : t("Add lot")}</button></div>
            </form>
          )}
          <details className="drawer">
            <summary><span className="k lbl">{t("Per-SKU cost")}</span><span className="tiny">{int(d.skus.length, lang)} SKU</span></summary>
          <div className="scroll"><table className="tbl">
            <thead><tr><th></th><th>{t("Product")} / {t("sku")}</th><th className="r">{t("Current cost")}</th><th>{t("Source")}</th><th>{t("Effective from")}</th></tr></thead>
            <tbody>
              {d.skus.length === 0 && <tr><td colSpan={5} className="empty">{t("No SKUs.")}</td></tr>}
              {d.skus.map((s) => {
                const open = openSku === s.sku_id;
                const canOpen = s.history.length > 0;
                return [
                  <tr key={s.sku_id} style={{ cursor: canOpen ? "pointer" : "default" }} onClick={() => canOpen && setOpenSku(open ? null : s.sku_id)} {...(canOpen ? { tabIndex: 0, role: "button", "aria-expanded": open, "aria-label": `${t("History")}: ${s.product_title}`, onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpenSku(open ? null : s.sku_id); } } } : {})}>
                    <td className="muted">{canOpen ? (open ? "▾" : "▸") : ""}</td>
                    <td style={{ whiteSpace: "normal" }}>{s.product_title}<br /><span className="tiny">{s.sku_title ?? ""} {s.external_sku_id ? `· ${s.external_sku_id}` : ""}</span></td>
                    <td className="r">{idr(s.current_cost, lang)}</td>
                    <td><Pill tone={s.source === "lot" ? "good" : s.source === "seed" ? "info" : s.source === "default" ? "gray" : "bad"}>{s.source === "lot" ? `${t("lot")} #${s.lot_id}` : t(s.source)}</Pill></td>
                    <td>{s.effective_from ? dayMon(s.effective_from, lang) : "—"}</td>
                  </tr>,
                  open && s.history.map((h, i) => (
                    <tr key={`${s.sku_id}-${i}`} style={{ background: "var(--surface2)" }}>
                      <td></td><td className="tiny" style={{ whiteSpace: "normal" }}>↳ {h.notes ?? ""}</td><td className="r">{idr(h.cogs_per_unit, lang)}</td><td className="tiny">{t("History")}</td><td className="tiny">{dayMon(h.effective_from, lang)} – {h.effective_to ? dayMon(h.effective_to, lang) : "…"}</td>
                    </tr>
                  )),
                ];
              })}
            </tbody>
          </table></div>
          </details>
          <div className="tiny" style={{ marginTop: 8 }}>{d.note}<EnHint lang={lang} /> {num(d.default_cogs_per_unit) === null && `· ${t("none")}`}</div>
        </>
      )}
    </div>
  );
}
