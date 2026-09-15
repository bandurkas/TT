"use client";
import { EnHint, useLang, useT } from "@/lib/i18n";
import { idr } from "@/lib/format";
import type { Finding, Insights } from "@/lib/types";
import { Conf, ErrorNote, Skeleton, ZoneHeader, scrollTo } from "./ui";

interface Props {
  ins: Insights | null; loading: boolean; error: string | null; reload: () => void;
  onCreateTask: (f: Finding) => void; onOpenTab: (tab: string) => void;
}

const sevCls = (s: Finding["severity"]) => (s === "CRITICAL" ? "dn" : s === "OPPORTUNITY" ? "up" : s === "WARNING" ? "" : "muted");

export function FindingActions({ f, onCreateTask, onOpenTab }: { f: Finding; onCreateTask: (f: Finding) => void; onOpenTab: (tab: string) => void }) {
  const t = useT();
  const l = f.links ?? {};
  const tab = l.tab ?? (l.product_id ? "products" : l.video_id ? "videos" : null);
  return (
    <div className="a">
      {tab && <button className="btn sm" onClick={() => onOpenTab(tab)}>{t(tab === "products" ? "Open products" : tab === "videos" ? "Open videos" : "Open campaigns")}</button>}
      {l.zone === "funnel" && <button className="btn sm" onClick={() => scrollTo("z5")}>{t("Open funnel")}</button>}
      <button className="btn sm pri" onClick={() => onCreateTask(f)}>{t("Create task")}</button>
    </div>
  );
}

function FindingRow({ f, i, onCreateTask, onOpenTab }: { f: Finding; i: number } & Pick<Props, "onCreateTask" | "onOpenTab">) {
  const lang = useLang(), t = useT();
  return (
    <div className="f" key={f.key}>
      <span className="no">{f.severity === "OPPORTUNITY" ? "✓" : i + 1}</span>
      <div>
        <div className={`t ${sevCls(f.severity)}`}><span className={`pill ${f.severity === "CRITICAL" ? "p-bad" : f.severity === "WARNING" ? "p-warn" : f.severity === "OPPORTUNITY" ? "p-good" : "p-gray"}`} style={{ marginRight: 8 }}>{t(f.severity)}</span>{f.title}</div>
        <div className="e">{f.detail}<EnHint lang={lang} /></div>
        <div className="m">
          <span>{t("Impact")} <b>{f.impact === null ? "—" : idr(f.impact, lang, { sign: true })}</b> <span className="tiny">({t(f.measured ? "measured" : "estimate")})</span></span>
          <Conf c={f.confidence} />
          <span>{t("Source")}: {f.source}</span>
        </div>
      </div>
      <FindingActions f={f} onCreateTask={onCreateTask} onOpenTab={onOpenTab} />
    </div>
  );
}

// Zones 2 & 6 used to show the same insights.findings() list twice: once in full (Diagnosis),
// once re-split by kind into two columns (Opps) — same data, same API call, two shapes on the
// same page. This is the one place for it, split by kind (not re-fetched, just re-grouped).
export default function Attention({ ins, loading, error, reload, onCreateTask, onOpenTab }: Props) {
  const lang = useLang(), t = useT();
  const items = ins?.findings ?? [];
  const lead = items[0];
  // Matches the backend's own risks/opportunities split (apps/api/dashboard.py) exactly: a risk
  // only belongs under "needs action" at CRITICAL/WARNING — an INFO-severity risk-kind finding
  // (e.g. a positive profit-vs-previous headline) is context, not something to act on.
  const risks = items.filter((f) => f.kind === "risk" && (f.severity === "CRITICAL" || f.severity === "WARNING"));
  const opportunities = items.filter((f) => f.kind === "opportunity");
  return (
    <section className="zone">
      <ZoneHeader id="z2" eyebrow={t("2 · Needs attention")} title={t("What needs attention")}
                 hint={<><b>{t("Deterministic rules · no LLM")}</b> · {t("confidence shown per finding")}</>} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !ins ? <Skeleton h={160} /> : ins && (
        <>
          <div className="card diag">
            {lead ? <div className="lead"><span className={sevCls(lead.severity)}>{lead.title}.</span> <span className="muted" style={{ fontWeight: 500, fontSize: 14 }}>{lead.detail}</span></div>
              : <div className="muted">{t("No findings for this period.")}</div>}
          </div>
          <div className="two">
            <div>
              <div className="k lbl" style={{ margin: "10px 0 6px" }}>{t("Needs action")}</div>
              <div className="card diag">
                {risks.length === 0 && <div className="muted" style={{ padding: 12 }}>{t("None detected.")}</div>}
                {risks.map((f, i) => <FindingRow key={f.key} f={f} i={i} onCreateTask={onCreateTask} onOpenTab={onOpenTab} />)}
              </div>
            </div>
            <div>
              <div className="k lbl" style={{ margin: "10px 0 6px" }}>{t("Opportunities")}</div>
              <div className="card diag">
                {opportunities.length === 0 && <div className="muted" style={{ padding: 12 }}>{t("None detected.")}</div>}
                {opportunities.map((f, i) => <FindingRow key={f.key} f={f} i={i} onCreateTask={onCreateTask} onOpenTab={onOpenTab} />)}
              </div>
            </div>
          </div>
          <div className="tiny" style={{ marginTop: 10 }}>{ins.note}<EnHint lang={lang} /></div>
        </>
      )}
    </section>
  );
}
