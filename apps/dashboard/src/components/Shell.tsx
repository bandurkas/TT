"use client";
import { useT, type Lang } from "@/lib/i18n";
import { dateTime, periodLabel } from "@/lib/format";
import type { Overview } from "@/lib/types";
import type { PeriodState, Preset } from "@/lib/period";
import { useState } from "react";

export function Rail({ shop, counts }: { shop?: string; counts: { recs: number; board: number } }) {
  const t = useT();
  const go = (id: string) => (e: React.MouseEvent) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); };
  return (
    <aside className="rail">
      <div className="brand"><div className="mark">L</div><div><b>Profit Control</b><small>{shop ?? "—"} · TikTok Shop ID</small></div></div>
      <nav className="nav">
        <div className="lbl">{t("Views")}</div>
        <a className="on" href="#z1" onClick={go("z1")}>{t("Executive")}</a>
        <a href="#z4" onClick={go("z4")}>{t("Performance marketing")}</a>
        <a href="#z4b" onClick={go("z4b")}>{t("Creative / video")}</a>
        <a href="#z4" onClick={go("z4")}>{t("Product / commerce")}</a>
        <a href="#z5" onClick={go("z5")}>{t("Finance")}</a>
        <div className="lbl">{t("Explore")}</div>
        <a href="#z4" onClick={go("z4")}>{t("Campaigns")}</a>
        <a href="#z4" onClick={go("z4")}>{t("Products")}</a>
        <a href="#z4" onClick={go("z4")}>{t("Videos")}</a>
        <a href="#z4" onClick={go("z4")}>{t("Creators")}</a>
        <div className="lbl">{t("Work")}</div>
        <a href="#z6" onClick={go("z6")}>{t("Recommendations")} <span className="pill p-info">{counts.recs}</span></a>
        <a href="#z7" onClick={go("z7")}>{t("Team board")} <span className="pill p-warn">{counts.board}</span></a>
      </nav>
    </aside>
  );
}

interface HeaderProps {
  lang: Lang; setLang: (l: Lang) => void; period: PeriodState;
  onPeriod: (p: { preset?: string; from?: string; to?: string }) => void;
  overview: Overview | null; onRefresh: () => void; refreshing: boolean;
}

export function Header({ lang, setLang, period, onPeriod, overview, onRefresh, refreshing }: HeaderProps) {
  const t = useT();
  const [from, setFrom] = useState(period.from ?? "");
  const [to, setTo] = useState(period.to ?? "");
  const dq = overview?.data_quality;
  const dqCls = dq ? dq.state.toLowerCase() : "na";
  return (
    <div className="head">
      <span className="chip"><b>{overview?.shop.name ?? "—"}</b></span>
      <span className="chip">{t("Period")}
        <select aria-label={t("Period")} value={period.preset} onChange={(e) => onPeriod({ preset: e.target.value as Preset, from: undefined, to: undefined })}>
          <option value="month">{t("This month")}</option>
          <option value="30d">{t("Last 30 days")}</option>
          <option value="custom">{t("Custom")}</option>
        </select>
        {period.preset === "custom" ? (
          <>
            <input type="date" aria-label="from" value={from} onChange={(e) => setFrom(e.target.value)} />–
            <input type="date" aria-label="to" value={to} onChange={(e) => setTo(e.target.value)} />
            <button className="btn xs" disabled={!from || !to} onClick={() => onPeriod({ preset: "custom", from, to })}>{t("Apply")}</button>
          </>
        ) : overview ? <b>{periodLabel(overview.period.start, overview.period.end, lang)}</b> : null}
      </span>
      <span className="chip">{t("Compare")} <b>{overview ? periodLabel(overview.compare.start, overview.compare.end, lang) : "—"}</b></span>
      <span className="sp" />
      <span className="sync">
        <span>{t("Last sync")} {dateTime(dq?.last_sync, lang, overview?.shop.timezone)}</span>
        <span className={`dq ${dqCls}`} title={dq?.reasons.join("; ")}>{t("Data quality")} {dq ? `${dq.score}% · ${t(dq.state)}` : "—"}</span>
      </span>
      <button className="btn" onClick={onRefresh} disabled={refreshing}>{t("Refresh")}</button>
      <span className="lang">
        <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
        <button className={lang === "ru" ? "on" : ""} onClick={() => setLang("ru")}>RU</button>
      </span>
    </div>
  );
}
