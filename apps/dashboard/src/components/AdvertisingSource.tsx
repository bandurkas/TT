"use client";
import type { Advertising } from "@/lib/types";
import { useLang } from "@/lib/i18n";
import { orderMoney } from "@/lib/orders";

export default function AdvertisingSource({ data, currency = "IDR" }: { data?: Advertising; currency?: string }) {
  const lang = useLang(), ru = lang === "ru";
  if (!data) return null;
  const money = (v: string | null) => orderMoney(v, lang, currency);
  return <div className="note ad-source">
    <b>{ru ? "Реклама: расход и оплата разделены" : "Advertising: cost and payments are separate"}</b>
    <div className="ad-source-values">
      <span>{ru ? "Расход по отчёту · Cost" : "Reported Cost"}: <strong>{money(data.cost)}</strong></span>
      <span>{ru ? "Оплачено из выручки · GMV Pay" : "Paid from shop revenue · GMV Pay"}: <strong>{money(data.gmv_pay)}</strong></span>
      <span>{ru ? "Дней с данными" : "Days covered"}: {data.covered_days}/{data.expected_days}</span>
    </div>
    <p>{ru ? "GMV Pay — движение денег, повторно из прибыли не вычитается. Общий Cost учитывает и дни без заказов; распределение по заказам одного дня — оценка, а не точная атрибуция." : "GMV Pay is a payment, never a second expense. Total Cost includes days without orders; same-day order allocation is an estimate, not exact attribution."}</p>
    {!!data.missing_days.length && <p className="dn">{ru ? "Нет полного отчёта за выбранный период. Расход и прибыль не подтверждены. Известный расход:" : "The report does not cover this period. Cost and profit are unavailable. Known cost:"} {money(data.known_cost)}</p>}
    {!!data.partial_days.length && <p className="dn">{ru ? "Неполный день в выгрузке — цифры ещё изменятся:" : "Partial day in the export — figures may change:"} {data.partial_days.join(", ")}</p>}
    <p className="small muted">{ru ? "Прибыль расчётная: предварительные комиссии, внесённая себестоимость. Рекламные кредиты и налоги требуют отдельной сверки с биллингом; они не предполагаются равными нулю." : "Profit is an estimate: preliminary fees and entered costs. Ad credits and taxes require a separate billing reconciliation; they are not assumed to be zero."}</p>
    <details><summary>{ru ? "Источник и контроль импорта" : "Source and import audit"}</summary>{data.reports.map(r => <p className="small" key={r.sha256}>{r.filename}<br />{r.observed_at} · {r.timezone}<br /><span className="source-hash">SHA-256: {r.sha256}</span></p>)}</details>
  </div>;
}
