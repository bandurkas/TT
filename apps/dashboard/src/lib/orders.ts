import type { Meta } from "./types";
import type { Lang } from "./i18n";

export type OrderState = "final" | "preliminary" | "not_calculated";
export interface OrderAmounts {
  revenue_base: string; fees: string | null; costs: string | null; refunds: string; other_effect: string; ad_cost: string | null; net_profit: string | null;
  profit_share: string | null; shares: Record<string, string | null>;
}
export interface OrderRow {
  income_evidence?: { filename: string; row: number; refund: string; settlement: string; dynamic_commission: string; processing: string; tax: string } | null;
  id: number; external_order_id: string; created_at: string | null; order_status: string;
  currency: string; state: OrderState; profit_status: string | null; version: number | null;
  calculated_at: string | null;
  unconfirmed_fields: string[];
  items: { title: string | null; sku_id: string | null; sku_title: string | null; quantity: number }[];
  amounts: OrderAmounts | null;
}
export interface OrderPage extends Meta {
  rows: OrderRow[]; total: number; offset: number; limit: number; demo?: boolean; mixed_currencies: boolean;
  summary: (OrderAmounts & { currency: string | null; calculated_orders: number; missing_orders: number; uncertain_orders: number; basis?: string; unallocated_ad_cost?: string }) | null;
}
export interface FinanceLine { key: string; amount: string | null; share: string | null; subtotal: boolean; evidence: string }
export interface OrderDetail extends OrderRow {
  timezone: string; demo?: boolean; revenue_base?: string; source?: string;
  ad_method?: string; ad_confidence?: string; ad_window_days?: number;
  lines: FinanceLine[];
  transactions: { id: string; field: string; kind: string; group: string; amount: string; raw_amount: string; share: string | null; statement_id: string | null }[];
  warnings: string[];
  calculation_check: { status: string; differences: Record<string, string> } | null;
  settlement_check: { status: string; difference: string | null; actual: string | null };
  settlements: { statement_id: string; amount: string | null; currency: string; statement_time: string | null; fetched_at: string | null }[];
  cost_versions?: { sku_id: string; effective_from: string; cogs_per_unit: string; evidence: string }[];
}

/** Format the stored decimal string without float conversion, abbreviation or hidden rounding. */
export function orderMoney(value: string | null | undefined, lang: Lang, currency = "IDR"): string {
  if (value == null || !/^-?\d+(\.\d+)?$/.test(value)) return "—";
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const tail = fraction.replace(/0+$/, "");
  const negative = value.startsWith("-") && /[1-9]/.test(value);
  return `${negative ? "−" : ""}${currency === "IDR" ? "Rp" : currency} ${BigInt(whole).toLocaleString(lang === "ru" ? "ru-RU" : "en-US")}${tail ? (lang === "ru" ? "," : ".") + tail : ""}`;
}

const LABELS: Record<string, [string, string]> = {
  warning_advertising_missing: ["Нет отчёта Cost за день заказа. Реклама и прибыль не подтверждены.", "No Cost report for this order day. Advertising and profit are unavailable."],
  warning_advertising_partial: ["Рекламный отчёт за день неполный; прибыль ещё изменится.", "Advertising report for this day is partial; profit may change."],
  journal: ["Журнал заказов", "Order journal"], title: ["Из чего складывается прибыль заказа", "Where each order's profit comes from"],
  basis: ["100% — выручка после скидки продавца, до возвратов и комиссий. Проценты показывают долю от этой суммы, а не тариф TikTok.", "100% is revenue after seller discounts, before refunds and fees. Percentages are shares of this amount, not TikTok fee rates."],
  basisShort: ["% от выручки после скидки", "% of revenue after discount"],
  search: ["Номер заказа или товар", "Order number or product"], find: ["Найти", "Search"], state: ["Данные TikTok", "TikTok data"],
  all: ["Все статусы", "All statuses"], final: ["TikTok: финальные", "TikTok: final"], preliminary: ["TikTok: предварительные", "TikTok: preliminary"], not_calculated: ["Не рассчитан", "Not calculated"],
  loss: ["Только убыточные", "Losses only"], reset: ["Сбросить", "Reset"], order: ["Заказ / товар", "Order / product"],
  revenue: ["Выручка после скидки", "Revenue after discount"], fees: ["Удержания TikTok", "TikTok deductions"], costs: ["Товар и расходы", "Product & costs"],
  ads: ["Реклама · оценка", "Ads · estimate"], profit: ["Прибыль · оценка", "Profit · estimate"],
  open: ["Разбор заказа", "Order breakdown"], close: ["Закрыть", "Close"], loading: ["Загрузка заказов…", "Loading orders…"],
  empty: ["Заказов по этим условиям нет.", "No orders match these filters."], previous: ["Назад", "Previous"], next: ["Дальше", "Next"],
  found: ["Найдено заказов", "Orders found"], totals: ["Итоги по всем найденным заказам, не только на этой странице", "Totals for all matching orders, not just this page"],
  included: ["Рассчитано", "Calculated"], missing: ["Без расчёта (не включены в суммы)", "Uncalculated (excluded from totals)"],
  uncertain: ["Предварительные комиссии или неполная себестоимость", "Preliminary fees or incomplete product costs"],
  other_effect: ["Возвраты, компенсации, корректировки", "Refunds, subsidies, adjustments"],
  mixed: ["В выборке разные валюты. Общий денежный итог не суммируется.", "Multiple currencies in selection. Monetary totals are not combined."],
  demo: ["Демонстрационные данные — не реальные заказы магазина.", "Demo data — not real shop orders."],
  version: ["Версия расчёта", "Calculation version"], calculatedAt: ["Рассчитано", "Calculated at"], source: ["Источник", "Source"],
  settled: ["Финальный отчёт TikTok", "Final TikTok statement"], unsettled_record: ["Предварительный отчёт TikTok", "Preliminary TikTok statement"], ratio_estimate: ["Оценка по предыдущим заказам", "Estimate from past orders"], unknown: ["Источник не подтверждён", "Source unconfirmed"],
  amount: ["Сумма", "Amount"], article: ["Статья", "Item"], share: ["Доля, %", "Share, %"],
  sale_proceeds: ["Продажа до скидки продавца", "Sale before seller discount"], seller_discounts: ["Скидка продавца", "Seller discount"], revenue_base: ["Выручка после скидки · база 100%", "Revenue after discount · 100% base"],
  refunds: ["Возвраты покупателям", "Customer refunds"], platform_fees: ["Комиссии и услуги платформы", "Platform commissions & services"],
  affiliate_commission: ["Комиссии авторам / аффилиатам", "Creator / affiliate commissions"], seller_shipping: ["Логистика за счёт продавца", "Seller-funded logistics"], taxes: ["Налоговые удержания", "Tax withholdings"],
  subsidies: ["Компенсации платформы, включённые в расчёт", "Platform subsidies included in calculation"], adjustments: ["Корректировки", "Adjustments"],
  net_seller_revenue: ["Остаток после удержаний TikTok", "Revenue after TikTok deductions"], cogs: ["Закупочная стоимость товара", "Product purchase cost"],
  packaging: ["Упаковка", "Packaging"], inbound_logistics: ["Доставка до склада", "Inbound logistics"], other_variable: ["Прочие переменные расходы", "Other variable costs"],
  contribution_profit: ["Прибыль до рекламы", "Profit before advertising"], allocated_ad_cost: ["Реклама, распределённая на заказ", "Advertising allocated to order"], estimated_net_profit: ["Расчётная прибыль заказа", "Estimated order profit"],
  internal: ["Внесённые затраты", "Entered costs"], estimate: ["Оценка", "Estimate"], calculated: ["Вычислено", "Calculated"], unavailable: ["Нет подтверждения", "Unconfirmed"],
  assumed: ["В расчёте принято", "Assumed in calculation"], transactions: ["Состав суммы", "Amount breakdown"],
  already: ["Операции ниже уже учтены в строке выше. Повторно их не вычитаем.", "The operations below are already included above. They are not deducted again."],
  fee_residual: ["Динамическая комиссия + обработка заказа (общая сумма без отдельной разбивки)", "Dynamic commission + order processing (combined; separate breakdown unavailable)"],
  arithmetic: ["Проверка арифметики", "Arithmetic check"], statement: ["Сверка остатка с отчётами TikTok", "Revenue reconciliation with TikTok statements"],
  matched: ["Сходится", "Matches"], mismatch: ["Есть расхождение", "Mismatch"], pending: ["Ждём финальных данных", "Awaiting final data"],
  difference: ["Расхождение", "Difference"], external: ["Сумма по отчётам", "Statement total"],
  checkNote: ["Совпадение итогов не подтверждает каждую комиссию отдельно и не означает поступление денег в банк. Себестоимость и реклама не входят в эту сверку.", "Matching totals do not verify every fee separately or prove a bank payout. Product costs and advertising are excluded from this reconciliation."],
  records: ["Отчёты, связанные с версией расчёта", "Statements linked to this calculation version"], fetched: ["Загружен", "Fetched"],
  costVersions: ["Источники себестоимости: SKU, дата действия, цена за штуку", "Cost sources: SKU, effective date, unit cost"],
  zeroBase: ["Выручка после скидки не положительная: процентное соотношение не рассчитывается.", "Revenue after discount is not positive: percentage shares are unavailable."],
  warnings: ["Ограничения расчёта", "Calculation limitations"],
  warning_not_calculated: ["Для заказа ещё нет расчёта. Отсутствие данных не означает нулевые расходы или прибыль.", "This order has no calculation yet. Missing data does not mean zero costs or profit."],
  warning_cogs_missing: ["Не хватает себестоимости хотя бы одного SKU. Часть затрат могла быть принята равной нулю; прибыль может быть завышена.", "Cost is missing for at least one SKU. Some costs may be assumed zero and profit overstated."],
  warning_cogs_default_used: ["Для части товаров применена общая себестоимость магазина вместо индивидуальной цены SKU.", "Some products use the shop's default cost rather than a SKU-specific cost."],
  warning_mismatch: ["При исходном расчёте обнаружено расхождение с финансовыми данными. Совпадение итоговой суммы не снимает это предупреждение.", "The original calculation found a finance data mismatch. A matching total does not clear this warning."],
  warning_fees_unknown_zero_assumption: ["Нет базы для оценки комиссий: движок принял их равными нулю. Это не подтверждённые нулевые комиссии.", "No basis for estimating fees: the engine assumed zero. These are not confirmed zero fees."],
  warning_advertising_allocated: ["Реклама распределена по выручке между заказами магазина (BLENDED, низкая уверенность). Это не точная стоимость привлечения этого заказа.", "Advertising is allocated across shop orders by revenue (BLENDED, low confidence). This is not this order's exact acquisition cost."],
  warning_unknown_transactions: ["Есть нераспознанные операции. Их исходные суммы показаны отдельно; движок не учитывает их отдельной строкой. Они могут уже входить в общую комиссию — повторно прибавлять их нельзя.", "There are unrecognized operations. Original amounts are shown separately; the engine does not include them as separate entries. They may already be covered by the combined fee and must not be added again."],
  unknownTransactions: ["Нераспознанные операции: исходные суммы, без отдельного влияния на итог", "Unrecognized operations: original amounts, no separate impact on total"],
  profitNote: ["Статус «финальные» относится к данным TikTok. Прибыль остаётся оценкой из-за распределённой рекламы; учитываются только внесённые расходы.", "“Final” refers to TikTok data. Profit remains estimated because advertising is allocated; only entered costs are included."],
  noItems: ["Состав заказа не загружен", "Order items not loaded"],
};

const FIELDS: Record<string, [string, string]> = {
  gross_sales_amount: LABELS.sale_proceeds, seller_discount_amount: LABELS.seller_discounts,
  gross_sales_refund_amount: LABELS.refunds, seller_discount_refund_amount: ["Возврат скидки продавца", "Seller discount reversal"],
  platform_commission_amount: ["Комиссия платформы", "Platform commission"], referral_fee_amount: ["Реферальная комиссия", "Referral fee"], transaction_fee_amount: ["Обработка платежа", "Transaction fee"],
  affiliate_commission_amount: LABELS.affiliate_commission, affiliate_ads_commission_amount: ["Аффилиатная рекламная комиссия", "Affiliate ads commission"], affiliate_partner_commission_amount: ["Партнёрская комиссия", "Affiliate partner commission"],
  shipping_cost_amount: LABELS.seller_shipping, shipping_insurance_fee_amount: ["Страхование доставки", "Shipping insurance"], signature_confirmation_fee_amount: ["Подтверждение вручения", "Signature confirmation"], return_shipping_fee_amount: ["Обратная доставка", "Return shipping"],
  fbm_shipping_cost_amount: ["Доставка FBM", "FBM shipping"], fbt_shipping_cost_amount: ["Доставка FBT", "FBT shipping"], fbt_fulfillment_fee_amount: ["Фулфилмент FBT", "FBT fulfillment"], fbt_fulfillment_fee_reimbursement_amount: ["Возмещение фулфилмента FBT", "FBT fulfillment reimbursement"],
  refund_administration_fee_amount: ["Обработка возврата", "Refund administration"], retail_delivery_fee_amount: ["Сбор за розничную доставку", "Retail delivery fee"], sales_tax_amount: ["Налог с продаж", "Sales tax"], isr_income_tax_amount: ["Подоходное удержание ISR", "ISR income tax"], iva_vat_amount: ["НДС / IVA", "VAT / IVA"], pit_amount: ["Подоходное удержание PIT", "PIT withholding"], adjustment_amount: LABELS.adjustments,
};
export const orderText = (lang: Lang, key: string): string => (LABELS[key] ?? FIELDS[key])?.[lang === "ru" ? 0 : 1] ?? key;
