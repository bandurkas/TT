"use client";
import { EnHint, useLang, useT } from "@/lib/i18n";
import { idr } from "@/lib/format";
import type { Finding, Insights } from "@/lib/types";
import { ErrorNote, Skeleton, ZoneHeader } from "./ui";

function List({ items, tone, onCreateTask }: { items: Finding[]; tone: "up" | "dn"; onCreateTask: (f: Finding) => void }) {
  const lang = useLang(), t = useT();
  return (
    <div className="card"><div className="list">
      {items.length === 0 && <div className="item"><span className="no">–</span><div className="muted">{t("None detected.")}</div><span /></div>}
      {items.map((f, i) => (
        <div className="item" key={f.key}>
          <span className="no">{i + 1}</span>
          <div>
            <div className="t">{f.title}</div>
            <div className="s">{f.detail}<EnHint lang={lang} /> · {t("Confidence")} {t(f.confidence)} · <button className="btn xs" onClick={() => onCreateTask(f)}>{t("Create task")}</button></div>
          </div>
          <div className={`amt ${tone}`}>{f.impact === null ? "—" : idr(f.impact, lang, { sign: true })}<small>{t(f.measured ? "measured" : "estimate")}</small></div>
        </div>
      ))}
    </div></div>
  );
}

export default function Opps({ ins, loading, error, reload, onCreateTask }: { ins: Insights | null; loading: boolean; error: string | null; reload: () => void; onCreateTask: (f: Finding) => void }) {
  const t = useT();
  return (
    <section className="zone">
      <ZoneHeader id="z6" eyebrow={t("6 · Opportunities & leakage")} title={t("Ranked by money, not percentages")} hint={t("Deterministic rules · no LLM")} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {loading && !ins ? <Skeleton h={160} /> : ins && (
        <div className="two">
          <div><div className="k lbl" style={{ marginBottom: 6 }}>{t("Opportunities")}</div><List items={ins.opportunities} tone="up" onCreateTask={onCreateTask} /></div>
          <div><div className="k lbl" style={{ marginBottom: 6 }}>{t("Leakage / risks")}</div><List items={ins.risks} tone="dn" onCreateTask={onCreateTask} /></div>
        </div>
      )}
    </section>
  );
}
