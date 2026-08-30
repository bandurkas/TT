"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { dateTime, pct } from "@/lib/format";
import { orderMoney, orderText, type OrderDetail, type OrderPage, type OrderRow, type OrderState } from "@/lib/orders";
import { ErrorNote, Skeleton, ZoneHeader } from "./ui";
import AdvertisingSource from "./AdvertisingSource";

function Evidence({ value }: { value: string }) {
  const lang = useLang();
  return <span className={`order-evidence evidence-${value}`}>{orderText(lang, value)}</span>;
}

function Items({ order }: { order: OrderRow }) {
  const lang = useLang();
  return <div className="order-items">{order.items.length ? order.items.map((i, n) => <div key={n}>
    {i.title ?? i.sku_id ?? "SKU"}{i.sku_title ? ` · ${i.sku_title}` : ""} × {i.quantity}
  </div>) : orderText(lang, "noItems")}</div>;
}

export default function Orders({ query, shopId, tick }: { query: string; shopId?: string; tick: number }) {
  const lang = useLang(), t = (key: string) => orderText(lang, key);
  const [draft, setDraft] = useState(""), [search, setSearch] = useState("");
  const [state, setState] = useState<OrderState | "all">("all");
  const [loss, setLoss] = useState(false), [offset, setOffset] = useState(0), [selected, setSelected] = useState<number | null>(null);
  const params = new URLSearchParams(query);
  params.set("search", search); params.set("state", state); params.set("loss_only", String(loss));
  params.set("offset", String(offset)); params.set("limit", "25");
  const path = `/api/orders?${params}`;
  const changed = () => { setOffset(0); setSelected(null); };
  return <section className="zone order-zone" id="order-journal">
    <ZoneHeader id="zorders" eyebrow={t("journal")} title={t("title")} />
    <p className="note">{t("basis")} {t("profitNote")}</p>
    <form className="order-filters" onSubmit={e => { e.preventDefault(); setSearch(draft.trim()); changed(); }}>
      <label className="order-search">{t("search")}<input maxLength={100} value={draft} onChange={e => setDraft(e.target.value)} placeholder={t("search")} /></label>
      <button className="btn" type="submit">{t("find")}</button>
      <label>{t("state")}<select value={state} onChange={e => { setState(e.target.value as typeof state); changed(); }}>
        {["all", "final", "preliminary", "not_calculated"].map(s => <option value={s} key={s}>{t(s)}</option>)}
      </select></label>
      <label className="order-checkbox"><input type="checkbox" checked={loss} onChange={e => { setLoss(e.target.checked); changed(); }} />{t("loss")}</label>
      <button className="btn ghost" type="button" onClick={() => { setDraft(""); setSearch(""); setState("all"); setLoss(false); changed(); }}>{t("reset")}</button>
    </form>
    <JournalPage key={path} path={path} tick={tick} setOffset={setOffset} open={setSelected} />
    {selected !== null && <OrderDialog key={`${shopId}:${selected}:${tick}`} id={selected} shopId={shopId} close={() => setSelected(null)} />}
  </section>;
}

function JournalPage({ path, tick, setOffset, open }: { path: string; tick: number; setOffset: (n: number) => void; open: (n: number) => void }) {
  const { data: d, loading, error, reload } = useApi<OrderPage>(path, tick);
  const lang = useLang(), t = (key: string) => orderText(lang, key);
  if (error) return <ErrorNote error={error} onRetry={reload} />;
  if (loading || !d) return <div role="status"><p>{t("loading")}</p><Skeleton h={180} /></div>;
  const summary = d.summary, currency = summary?.currency ?? d.shop.currency;
  return <>
    {d.demo && <div className="banner warn">{t("demo")}</div>}
    <div className="order-results" aria-live="polite"><b>{t("found")}: {d.total}</b><span>{d.period.start} — {d.period.end} · {d.shop.timezone}</span></div>
    <AdvertisingSource data={d.advertising} currency={currency} />
    {summary && <p className="small muted">{lang === "ru" ? (summary.basis === "calendar" ? "Общий итог: реклама по дате расхода, включая дни без заказов. Сумма прибыли строк может отличаться на нераспределённый расход." : "Включены фильтры: ниже только оценка выбранных заказов. Расход всего магазина показан отдельно выше.") : (summary.basis === "calendar" ? "Calendar total includes advertising on days without orders; row profits exclude unallocated cost." : "Filtered cohort: estimated allocation only; full shop Cost is shown above.")}</p>}
    {d.mixed_currencies && <p className="banner warn">{t("mixed")}</p>}
    {summary && <>
      <p className="small muted">{t("totals")}. {t("included")}: {summary.calculated_orders} · {t("missing")}: {summary.missing_orders}</p>
      {summary.uncertain_orders > 0 && <p className="banner warn">{t("uncertain")}: {summary.uncertain_orders}</p>}
      <div className="order-totals">
        {([['revenue', 'revenue_base'], ['other_effect', 'other_effect'], ['fees', 'fees'], ['costs', 'costs'], ['ads', 'ad_cost'], ['profit', 'net_profit']] as const).map(([label, field]) => <div className="card" key={field}>
          <span className="small muted">{field === "ad_cost" && summary.basis === "calendar" ? (lang === "ru" ? "Расход рекламы · Cost" : "Reported advertising Cost") : t(label)}</span><strong>{orderMoney(summary.calculated_orders || summary.basis === "calendar" ? summary[field] : null, lang, currency)}</strong>
          <span className="small muted">{field === "revenue_base" ? t("basisShort") : pct(summary.shares[field], lang, { frac: 2 })}</span>
        </div>)}
      </div>
    </>}
    {!d.rows.length ? <p className="note">{t("empty")}</p> : <div className="card order-scroll" tabIndex={0} role="region" aria-label={t("journal")}>
      <table className="tbl order-table"><thead><tr>
        {["order", "revenue", "fees", "costs", "ads", "profit", "state"].map(k => <th key={k}>{t(k)}</th>)}
      </tr></thead><tbody>{d.rows.map(row => <tr key={row.id}>
        <td><button className="order-link" onClick={() => open(row.id)} aria-label={`${t("open")} ${row.external_order_id}`}>{row.external_order_id}</button>
          <div className="tiny">{dateTime(row.created_at, lang, d.shop.timezone)} · {row.order_status}</div><Items order={row} /></td>
        {(["revenue_base", "fees", "costs", "ad_cost", "net_profit"] as const).map(field => <td className="r" key={field}>
          <b className={field === "net_profit" && row.amounts?.net_profit?.startsWith("-") ? "dn" : ""}>{row.unconfirmed_fields.includes(field) ? "—" : orderMoney(row.amounts?.[field], lang, row.currency)}</b>
          {row.unconfirmed_fields.includes(field) ? <div className="tiny">{t("assumed")}: {orderMoney(row.amounts?.[field], lang, row.currency)}</div> : field !== "revenue_base" && <div className="tiny">{pct(row.amounts?.shares[field], lang, { frac: 2 })}</div>}
        </td>)}
        <td><Evidence value={row.state} /><button className="btn sm" onClick={() => open(row.id)}>{t("open")}</button></td>
      </tr>)}</tbody></table>
    </div>}
    <div className="order-pagination">
      <button className="btn" disabled={d.offset === 0} onClick={() => setOffset(Math.max(0, d.offset - d.limit))}>{t("previous")}</button>
      <span>{d.total ? `${d.offset + 1}–${Math.min(d.offset + d.rows.length, d.total)} / ${d.total}` : "0 / 0"}</span>
      <button className="btn" disabled={d.offset + d.limit >= d.total} onClick={() => setOffset(d.offset + d.limit)}>{t("next")}</button>
    </div>
  </>;
}

function OrderDialog({ id, shopId, close }: { id: number; shopId?: string; close: () => void }) {
  const lang = useLang(), t = (key: string) => orderText(lang, key);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current, prior = document.body.style.overflow;
    if (el && !el.open) el.showModal();
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prior; };
  }, []);
  const { data, loading, error, reload } = useApi<OrderDetail>(`/api/orders/${id}${shopId ? `?shop_id=${encodeURIComponent(shopId)}` : ""}`);
  return <dialog className="order-dialog" ref={ref} onClose={close} aria-labelledby="order-dialog-title">
    <div className="order-dialog-head"><h2 id="order-dialog-title">{t("open")}{data ? ` · ${data.external_order_id}` : ""}</h2><button className="btn" onClick={() => ref.current?.close()}>{t("close")}</button></div>
    {error ? <ErrorNote error={error} onRetry={reload} /> : loading || !data ? <Skeleton h={260} /> : <DetailBody d={data} />}
  </dialog>;
}

function DetailBody({ d }: { d: OrderDetail }) {
  const lang = useLang(), t = (key: string) => orderText(lang, key);
  const money = (s: string | null | undefined) => orderMoney(s, lang, d.currency);
  const [expanded, setExpanded] = useState<string[]>([]);
  const toggle = (key: string) => setExpanded(old => old.includes(key) ? old.filter(k => k !== key) : [...old, key]);
  return <div className="order-detail">
    {d.demo && <div className="banner warn">{t("demo")}</div>}
    <div className="order-results"><Evidence value={d.state} /><span>{dateTime(d.created_at, lang, d.timezone)} · {d.order_status}</span></div>
    <Items order={d} />
    {d.income_evidence && <div className="note"><b>{lang === "ru" ? "Финансовая выгрузка TikTok" : "TikTok income export"}</b><p>{d.income_evidence.filename} · {lang === "ru" ? "строка" : "row"} {d.income_evidence.row}</p><p>{lang === "ru" ? "Возврат после скидки" : "Refund after discount"}: {money(d.income_evidence.refund)} · {lang === "ru" ? "Начисление после удержаний" : "Settlement"}: {money(d.income_evidence.settlement)}</p><p>{lang === "ru" ? "Динамическая комиссия" : "Dynamic commission"}: {money(d.income_evidence.dynamic_commission)} · {lang === "ru" ? "Обработка заказа" : "Order processing"}: {money(d.income_evidence.processing)} · {lang === "ru" ? "Налог" : "Tax"}: {money(d.income_evidence.tax)}</p><span className="small muted">{lang === "ru" ? "Сверочный источник. Эти удержания уже входят в Total Fees и повторно не вычитаются. Нулевое начисление не подтверждает нулевые внутренние затраты." : "Reconciliation source. These deductions are already included in Total Fees, never subtracted twice. Zero settlement does not prove zero internal costs."}</span></div>}
    <p className="small muted">{t("version")}: {d.version ?? "—"} · {t("calculatedAt")}: {dateTime(d.calculated_at, lang, d.timezone)}<br />{t("source")}: {t(d.source ?? "unknown")}</p>
    {!!d.warnings.length && <div className="order-warnings"><b>{t("warnings")}</b><ul>{d.warnings.map(w => <li key={w}>{t(`warning_${w}`)}</li>)}</ul></div>}
    {!!d.lines.length && <>
      <p className="note">{t("basis")} <b>100% = {money(d.revenue_base)}</b></p>
      {d.lines[0]?.share === null && <p className="banner warn">{t("zeroBase")}</p>}
      <div className="order-breakdown-wrap"><table className="order-breakdown"><thead><tr><th>{t("article")}</th><th>{t("amount")}</th><th>{t("share")}</th></tr></thead><tbody>
        {d.lines.map(line => {
          const txns = d.transactions.filter(tx => tx.group === line.key), isOpen = expanded.includes(line.key), unconfirmed = line.evidence === "unavailable";
          return <Fragment key={line.key}>
            <tr className={line.subtotal ? `order-subtotal subtotal-${line.key}` : ""}>
              <td><div>{t(line.key)}</div><Evidence value={line.evidence} />{txns.length > 0 && <button className="order-expand" aria-expanded={isOpen} onClick={() => toggle(line.key)}>{isOpen ? "▾" : "▸"} {t("transactions")} ({txns.length})</button>}</td>
              <td className={`r ${line.amount?.startsWith("-") ? "dn" : ""}`}>{unconfirmed ? <><span>—</span></> : money(line.amount)}</td>
              <td className="r">{unconfirmed ? "—" : pct(line.share, lang, { frac: 2 })}</td>
            </tr>
            {isOpen && <tr className="order-operation"><td colSpan={3} className="tiny">{t("already")}</td></tr>}
            {isOpen && txns.map((tx, n) => <tr className="order-operation" key={`${tx.id}:${n}`}>
              <td>{t(tx.field) === tx.field ? t(tx.group) : t(tx.field)}<code>{tx.field}</code></td><td className="r">{money(tx.amount)}</td><td className="r">{pct(tx.share, lang, { frac: 2 })}</td>
            </tr>)}
          </Fragment>;
        })}
      </tbody></table></div>
      {d.transactions.some(tx => tx.group === "unknown") && <div className="order-warnings"><b>{t("unknownTransactions")}</b>
        {d.transactions.filter(tx => tx.group === "unknown").map((tx, n) => <p key={n}><code>{tx.field}</code> · {money(tx.raw_amount)}</p>)}
      </div>}
      <p className="small muted">{t("profitNote")} · {d.ad_method ?? "BLENDED"} / {d.ad_confidence ?? "LOW"}{d.ad_window_days ? ` · ${d.ad_window_days} ${lang === "ru" ? "дней" : "days"}` : ""}</p>
      <div className="order-checks">
        <div className="note"><b>{t("arithmetic")}</b><p className={d.calculation_check?.status === "mismatch" ? "dn" : ""}>{t(d.calculation_check?.status ?? "unavailable")}</p>
          {d.calculation_check?.status === "mismatch" && Object.entries(d.calculation_check.differences).map(([k, v]) => <div key={k}>{t(k)}: {money(v)}</div>)}
        </div>
        <div className="note"><b>{t("statement")}</b><p className={d.settlement_check.status === "mismatch" ? "dn" : ""}>{t(d.settlement_check.status)}</p>
          {d.settlement_check.actual !== null && <div>{t("external")}: {money(d.settlement_check.actual)}<br />{t("difference")}: {money(d.settlement_check.difference)}</div>}
        </div>
      </div>
      <p className="small muted">{t("checkNote")}</p>
      {!!d.settlements.length && <details className="order-sources"><summary>{t("records")} ({d.settlements.length})</summary>
        {d.settlements.map(s => <div key={s.statement_id}><code>{s.statement_id}</code> · {orderMoney(s.amount, lang, s.currency)}<br /><span className="tiny">{dateTime(s.statement_time, lang, d.timezone)} · {t("fetched")}: {dateTime(s.fetched_at, lang, d.timezone)}</span></div>)}
      </details>}
      {!!d.cost_versions?.length && <details className="order-sources"><summary>{t("costVersions")}</summary>{d.cost_versions.map((c, n) => <div key={n}><code>{c.sku_id}</code> · {c.evidence === "internal" ? c.effective_from : "—"} · {money(c.cogs_per_unit)} <Evidence value={c.evidence} /></div>)}</details>}
    </>}
  </div>;
}
