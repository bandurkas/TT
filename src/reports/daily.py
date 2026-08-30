"""Daily Telegram report formatter (SPEC §15.1). Money in IDR as Decimal, never float."""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal


def fmt_idr(amount: Decimal | int) -> str:
    a = Decimal(amount)
    sign = "-" if a < 0 else ""
    a = abs(a)
    if a >= 1_000_000:
        s = str((a / 1_000_000).quantize(Decimal("0.01"), ROUND_HALF_UP))
        s = s.removesuffix("0")
        return f"{sign}Rp {s}m"
    if a >= 1_000:
        return f"{sign}Rp {(a / 1_000).quantize(Decimal(1), ROUND_HALF_UP)}k"
    return f"{sign}Rp {a.quantize(Decimal(1), ROUND_HALF_UP)}"


def fmt_pct(v: Decimal) -> str:
    return f"{v.quantize(Decimal('0.1'), ROUND_HALF_UP)}%"


def fmt_ratio(v: Decimal | None) -> str:
    return "n/a" if v is None else str(v.quantize(Decimal("0.01"), ROUND_HALF_UP))


@dataclass(frozen=True)
class VideoHighlight:
    video_ref: str
    orders: int
    est_profit: Decimal | None = None
    spend: Decimal | None = None
    note: str | None = None


@dataclass(frozen=True)
class DailySummary:
    date: str
    gmv: Decimal
    net_seller_revenue: Decimal
    ad_spend: Decimal
    cogs: Decimal
    fees: Decimal
    net_profit: Decimal
    net_margin_pct: Decimal
    reported_roas: Decimal | None
    blended_roas: Decimal | None
    settled_pct: Decimal
    provisional_pct: Decimal
    winners: list[VideoHighlight] = field(default_factory=list)
    losers: list[VideoHighlight] = field(default_factory=list)
    recommendation: str | None = None
    title: str = "TikTok Shop — Daily Profit Report"


def format_daily_report(s: DailySummary) -> str:
    lines = [s.title, s.date, "",
             f"GMV: {fmt_idr(s.gmv)}",
             f"Net Seller Revenue: {fmt_idr(s.net_seller_revenue)}",
             f"Ad Spend: {fmt_idr(s.ad_spend)}",
             f"COGS: {fmt_idr(s.cogs)}",
             f"Affiliate/Platform/Other Fees: {fmt_idr(s.fees)}", "",
             f"Estimated Net Profit: {fmt_idr(s.net_profit)}",
             f"Net Margin: {fmt_pct(s.net_margin_pct)}", "",
             f"Reported ROAS: {fmt_ratio(s.reported_roas)}",
             f"Adjusted/Blended ROAS: {fmt_ratio(s.blended_roas)}"]
    for w in s.winners:
        lines += ["", "🔥 Winner", w.video_ref, f"{w.orders} orders"]
        if w.est_profit is not None:
            lines.append(f"Estimated profit: {fmt_idr(w.est_profit)}")
        if w.note:
            lines.append(w.note)
    for lo in s.losers:
        lines += ["", "⚠️ Losing Spend", lo.video_ref]
        if lo.spend is not None:
            lines.append(f"Spend {fmt_idr(lo.spend)}")
        lines.append(f"{lo.orders} orders")
        if lo.note:
            lines.append(lo.note)
    if s.recommendation:
        lines += ["", "Recommendation:", s.recommendation]
    lines += ["", "Data status:",
              f"{fmt_pct(s.settled_pct)} settled / {fmt_pct(s.provisional_pct)} provisional"]
    return "\n".join(lines)
