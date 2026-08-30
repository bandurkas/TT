"use client";
import { EnHint, useLang, useT } from "@/lib/i18n";
import { idr, int, num, pct } from "@/lib/format";
import type { Funnel as FunnelT } from "@/lib/types";
import { ErrorNote, Skeleton, ZoneHeader } from "./ui";

export default function Funnel({ fn, loading, error, reload }: { fn: FunnelT | null; loading: boolean; error: string | null; reload: () => void }) {
  const lang = useLang(), t = useT();
  const stages = fn?.stages ?? [];
  const first = stages[0]?.count ?? 0;
  const width = (c: number) => (first > 0 && c > 0 ? Math.max(3, (Math.log10(c + 1) / Math.log10(first + 1)) * 100) : 0);
  const stepTo = new Map((fn?.steps ?? []).map((s) => [s.to, s]));
  const d = fn?.diagnosis ?? null;
  const wf = fn?.waterfall;
  let run = 0, lo = 0, hi = 0;
  const bars = (wf?.steps ?? []).map((s) => {
    const a = num(s.amount) ?? 0;
    if (s.subtotal) { run = a; lo = Math.min(lo, 0, a); hi = Math.max(hi, 0, a); return { s, a, from: Math.min(0, a), to: Math.max(0, a) }; }
    const from = Math.min(run, run + a), to = Math.max(run, run + a);
    run += a; lo = Math.min(lo, from); hi = Math.max(hi, to);
    return { s, a, from, to };
  });
  const span = hi - lo || 1;
  return (
    <section className="zone">
      <ZoneHeader id="z5" eyebrow={t("5 · Funnel & root cause")} title={t("Where the drop is, and what it cost")} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !fn ? <Skeleton h={260} /> : fn && (
        <div className="two">
          <div className="card funnel">
            {stages.map((s, i) => {
              const st = stepTo.get(s.name);
              const bad = d && d.stage_to === s.name;
              return (
                <div className="step" key={s.name}>
                  <span className="l">{t(s.name)}<small>{s.note}</small></span>
                  <span className="bar"><b style={{ width: `${width(s.count)}%` }} /></span>
                  <span className="cv">{int(s.count, lang)}</span>
                  <span className={`cv ${bad ? "bad" : ""}`}>{i === 0 ? "" : pct(st?.rate ?? null, lang)}{st?.timing_only && <small>{t("timing only")}</small>}{st && !st.timing_only && st.delta_pct !== null && <small>{pct(st.delta_pct, lang, { sign: true })} {t("vs baseline")}</small>}</span>
                </div>
              );
            })}
            {d ? (
              <div className="diagbox"><b style={{ color: "var(--bad)" }}>{t("Largest deterioration")}: {t(d.stage_from)} → {t(d.stage_to)}</b> · {pct(d.current_rate, lang)} {t("vs baseline")} {pct(d.baseline_rate, lang)} ({pct(d.delta_pct, lang, { sign: true })}). {t("Est.")} {int(d.lost_orders, lang)} {t("lost orders")}, <b>{idr(d.lost_profit, lang)}</b> {t("contribution")}. {d.evidence.join("; ")} <span className="tiny">({t("estimate")})</span><EnHint lang={lang} /></div>
            ) : <div className="diagbox ok">{t("No funnel deterioration vs the previous comparable period.")}</div>}
            <div className="tiny" style={{ marginTop: 8 }}>{t("baseline = previous comparable period")} · {t("(log scale)")}</div>
          </div>
          <div className="card wf">
            <div className="k lbl" style={{ marginBottom: 8 }}>{t("Profit waterfall")} · {int(wf?.orders ?? 0, lang)} {t("orders")} · {int(wf?.provisional_orders ?? 0, lang)} {t("provisional")}</div>
            {bars.map(({ s, a, from, to }) => (
              <div className={`wrow ${s.key === "net_profit" ? "total" : ""}`} key={s.key}>
                <span className={`lab ${s.subtotal ? "tot" : ""}`}>{t(s.key)}<small>{s.measured ? t("measured") : t("est.")}</small></span>
                <span className="g"><b style={{ left: `${((from - lo) / span) * 100}%`, width: `${s.amount === null ? 0 : Math.max(0.5, ((to - from) / span) * 100)}%`, background: s.subtotal ? (a < 0 ? "var(--bad)" : s.key === "net_profit" ? "var(--good)" : "var(--accent)") : a < 0 ? (s.key === "cogs" ? "var(--warn)" : "var(--bad)") : "var(--good)" }} /></span>
                <span className={`val ${a < 0 ? "dn" : ""}`}>{s.subtotal ? <b>{idr(s.amount, lang)}</b> : idr(s.amount, lang)}</span>
              </div>
            ))}
            <div className="tiny" style={{ marginTop: 8 }}>{wf?.note}<EnHint lang={lang} /></div>
          </div>
        </div>
      )}
    </section>
  );
}
