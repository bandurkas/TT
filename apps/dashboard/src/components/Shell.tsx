"use client";
import { useT, type Lang } from "@/lib/i18n";
import { dateTime, periodLabel } from "@/lib/format";
import type { Overview } from "@/lib/types";
import type { PeriodState, Preset } from "@/lib/period";
import DateRange from "./DateRange";
import { useEffect, useState } from "react";
import { orderText } from "@/lib/orders";
import { useLang } from "@/lib/i18n";

export function Rail({ shop, counts, setTab }: { shop?: string; counts: { recs: number; board: number }; setTab: (t: string) => void }) {
  const t = useT();
  const lang = useLang();
  const [active, setActive] = useState("z1");
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => {
    const ids = ["z1", "z2", "zorders", "z3", "z3b", "z4", "z4b", "z5", "z7"];
    const els = ids.map((i) => document.getElementById(i)).filter((e): e is HTMLElement => !!e);
    const io = new IntersectionObserver((es) => { const v = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]; if (v) setActive(v.target.id); }, { rootMargin: "-80px 0px -60% 0px" });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
  const cls = (id: string) => (active === id ? "on" : "");
  // Explorer's tab links used to only scroll to #z4 without ever switching the tab (they all
  // pointed at the same anchor) — this now matches Diagnosis/Attention's onOpenTab pattern.
  const go = (id: string, tab?: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    if (tab) setTab(tab);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMobileOpen(false);
  };
  return (
    <>
      <button type="button" className="rail-toggle" aria-label={t("Menu")} aria-expanded={mobileOpen} onClick={() => setMobileOpen((v) => !v)}>☰</button>
      {mobileOpen && <div className="rail-backdrop" onClick={() => setMobileOpen(false)} />}
      <aside className={`rail ${mobileOpen ? "open" : ""}`}>
        <div className="brand"><div className="mark">L</div><div><b>Profit Control</b><small>{shop ?? "—"} · TikTok Shop ID</small></div></div>
        <nav className="nav">
          <div className="lbl">{t("Views")}</div>
          <a className={cls("z1")} href="#z1" onClick={go("z1")}>{t("Executive")}</a>
          <a className={cls("z2")} href="#z2" onClick={go("z2")}>{t("What needs attention")} <span className="pill p-info">{counts.recs}</span></a>
          <a className={cls("zorders")} href="#zorders" onClick={go("zorders")}>{orderText(lang, "journal")}</a>
          <a className={cls("z3")} href="#z3" onClick={go("z3")}>{t("Sales trend")}</a>
          <a className={cls("z3b")} href="#z3b" onClick={go("z3b")}>{t("Best & worst performers")}</a>
          <a className={cls("z4")} href="#z4" onClick={go("z4", "campaigns")}>{t("Performance marketing")}</a>
          <a className={cls("z4b")} href="#z4b" onClick={go("z4b")}>{t("Creative / video")}</a>
          <a className={cls("z5")} href="#z5" onClick={go("z5")}>{t("Finance")}</a>
          <div className="lbl">{t("Explore")}</div>
          <a className={cls("z4")} href="#z4" onClick={go("z4", "campaigns")}>{t("Campaigns")}</a>
          <a className={cls("z4")} href="#z4" onClick={go("z4", "products")}>{t("Products")}</a>
          <a className={cls("z4")} href="#z4" onClick={go("z4", "videos")}>{t("Videos")}</a>
          <a className={cls("z4")} href="#z4" onClick={go("z4", "creators")}>{t("Creators")}</a>
          <div className="lbl">{t("Work")}</div>
          <a className={cls("z7")} href="#z7" onClick={go("z7")}>{t("Team board")} <span className="pill p-warn">{counts.board}</span></a>
        </nav>
      </aside>
    </>
  );
}

interface HeaderProps {
  lang: Lang; setLang: (l: Lang) => void; period: PeriodState;
  onPeriod: (p: { preset?: Preset; from?: string; to?: string }) => void;
  overview: Overview | null; onRefresh: () => void; refreshing: boolean;
}

export function Header({ lang, setLang, period, onPeriod, overview, onRefresh, refreshing }: HeaderProps) {
  const t = useT();
  const dq = overview?.data_quality;
  const dqCls = dq ? dq.state.toLowerCase() : "na";
  return (
    <div className="head">
      <span className="chip"><b>{overview?.shop.name ?? "—"}</b></span>
      <DateRange preset={period.preset} from={period.from ?? overview?.period.start} to={period.to ?? overview?.period.end}
        timezone={overview?.shop.timezone} onPick={onPeriod} />
      <span className="chip">{t("Compare")} <b>{overview ? periodLabel(overview.compare.start, overview.compare.end, lang) : "—"}</b></span>
      <span className="sp" />
      <span className="sync">
        <span>{t("Last sync")} {dateTime(dq?.last_sync, lang, overview?.shop.timezone)}</span>
        <span className={`dq ${dqCls}`} title={dq?.reasons.join("; ")}>{t("Data quality")} {dq ? `${dq.score}% · ${t(dq.state)}` : "—"}</span>
      </span>
      <button className="btn" onClick={onRefresh} disabled={refreshing}>{t("Refresh")}</button>
      <span className="lang">
        <button aria-pressed={lang === "en"} className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
        <button aria-pressed={lang === "ru"} className={lang === "ru" ? "on" : ""} onClick={() => setLang("ru")}>RU</button>
      </span>
    </div>
  );
}
