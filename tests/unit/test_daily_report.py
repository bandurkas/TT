from decimal import Decimal as D

import pytest

from src.reports.daily import DailySummary, VideoHighlight, fmt_idr, fmt_pct, format_daily_report


def test_fmt_idr():
    assert fmt_idr(D(4800000)) == "Rp 4.8m"
    assert fmt_idr(D(3920000)) == "Rp 3.9m"  # 1 dp for m/b by design
    assert fmt_idr(D(820000)) == "Rp 820k"
    assert fmt_idr(D(1000000)) == "Rp 1.0m"
    assert fmt_idr(D(143499)) == "Rp 143k"
    assert fmt_idr(D(999)) == "Rp 999"
    assert fmt_idr(D(-615000)) == "-Rp 615k"
    assert fmt_idr(D(999999)) == "Rp 1.0m"
    assert fmt_idr(D(999500)) == "Rp 1.0m"
    assert fmt_idr(D(950000)) == "Rp 950k"
    assert fmt_idr(D(1200000000)) == "Rp 1.2b"
    assert fmt_idr(D(999950000)) == "Rp 1.0b"
    assert fmt_idr(D(-400)) == "-Rp 400"
    assert fmt_idr(1600000) == "Rp 1.6m"
    with pytest.raises(TypeError):
        fmt_idr(1.5)


def test_fmt_pct():
    assert fmt_pct(D(92)) == "92%"
    assert fmt_pct(D("18.5")) == "18.5%"
    assert fmt_pct(D("92.04")) == "92%"
    assert fmt_pct(D(0)) == "0%"


def test_format_daily_report_layout():
    s = DailySummary(
        date="2026-08-29", gmv=D(4800000), net_seller_revenue=D(3920000),
        ad_spend=D(820000), cogs=D(1600000), fees=D(610000), net_profit=D(890000),
        net_margin_pct=D("18.5"), reported_roas=D("5.85"), blended_roas=D("4.78"),
        settled_pct=D(92), provisional_pct=D(8),
        winners=[VideoHighlight("Video #184", 37, est_profit=D(615000),
                                note="CTR +41% vs 7-day median")],
        losers=[VideoHighlight("Video #162", 0, spend=D(143000))],
        recommendation="Reduce exposure to #162 and create 3 variants of #184.")
    text = format_daily_report(s)
    assert text.startswith("TikTok Shop — Daily Profit Report\n2026-08-29\n\nGMV: Rp 4.8m\n")
    for line in ["Net Seller Revenue: Rp 3.9m", "Ad Spend: Rp 820k", "COGS: Rp 1.6m",
                 "Affiliate/Platform/Other Fees: Rp 610k", "Estimated Net Profit: Rp 890k",
                 "Net Margin: 18.5%", "Reported ROAS: 5.85", "Adjusted/Blended ROAS: 4.78",
                 "🔥 Winner\nVideo #184\n37 orders\nEstimated profit: Rp 615k",
                 "⚠️ Losing Spend\nVideo #162\nSpend Rp 143k\n0 orders",
                 "Recommendation:\nReduce exposure", "Data status:\n92% settled / 8% provisional"]:
        assert line in text
    assert len(text) < 4096


def test_no_roas_shows_na():
    s = DailySummary("d", D(0), D(0), D(0), D(0), D(0), D(0), D(0), None, None, D(0), D(100))
    assert "Reported ROAS: n/a" in format_daily_report(s)
