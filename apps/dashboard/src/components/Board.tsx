"use client";
import { useEffect, useState } from "react";
import { useLang, useT } from "@/lib/i18n";
import { dayMon, idr } from "@/lib/format";
import { createTask, patchTask } from "@/lib/api";
import { PRIORITIES, TASK_STATUSES, TEAMS, type Finding, type Task, type TaskIn, type TaskStatus, type Tasks, type Team } from "@/lib/types";
import { ErrorNote, Pill, Skeleton, ZoneHeader } from "./ui";

const COL_LABEL: Record<TaskStatus, string> = { today: "Today", in_progress: "In progress", review: "Review", done: "Done · measured" };
const TEAM_LABEL: Record<Team, string> = { performance: "Performance", video: "Video", design: "Design", product: "Product", finance: "Finance", management: "Management" };

const guessTeam = (key: string): Team =>
  key.startsWith("ads_") ? "performance" : key.startsWith("video_") || key === "funnel_deterioration" ? "video"
  : key.startsWith("product_loss") || key === "refund_rate_high" ? "product" : key === "margin_below_floor" ? "finance" : "management";

export const draftFromFinding = (f: Finding, lang: "en" | "ru"): TaskIn => ({
  title: f.title.slice(0, 255),
  detail: f.detail,
  team: guessTeam(f.key),
  priority: f.severity === "CRITICAL" ? "P1" : f.severity === "WARNING" ? "P2" : "P3",
  status: "today",
  impact_note: f.impact === null ? null : `${idr(f.impact, lang, { sign: true })} (${f.measured ? "measured" : "estimate"}, ${f.confidence})`,
  source: "insight",
  evidence: { insight: f.key, ...f.links },
});

const EMPTY: TaskIn = { title: "", detail: "", team: "performance", priority: "P2", status: "today", owner: "", deadline: "", impact_note: "", source: "manual", evidence: {} };

function TaskCard({ task, onMove, busy }: { task: Task; onMove: (t: Task, s: TaskStatus) => void; busy: boolean }) {
  const lang = useLang(), t = useT();
  const i = TASK_STATUSES.indexOf(task.status);
  const prev = i > 0 ? TASK_STATUSES[i - 1] : null, next = i < TASK_STATUSES.length - 1 ? TASK_STATUSES[i + 1] : null;
  const ev = Object.entries(task.evidence ?? {});
  return (
    <div className="task">
      <div className="h">
        {task.status === "done" ? <Pill tone="good">{t("Done")}</Pill> : <span className={`p ${task.priority.toLowerCase()}`}>{task.priority}</span>}
        <span className="team">{t(TEAM_LABEL[task.team] ?? task.team)}</span>
        {task.source === "insight" && <span className="tiny">· {t("Evidence")}: {ev.map(([k, v]) => `${k}=${String(v)}`).join(", ") || "insight"}</span>}
      </div>
      <div className="tt">{task.title}</div>
      {task.detail && <div className="why">{task.detail}</div>}
      {task.result_note && <div className="why"><b>{t("Result")}:</b> {task.result_note}</div>}
      <div className="ft">
        <span>{t("Owner")}: {task.owner || "—"}</span>
        {task.status === "done" ? <span>{t("Done")} {dayMon(task.done_at, lang)}</span> : task.deadline ? <span>{t("Deadline")}: {dayMon(task.deadline, lang)}</span> : task.impact_note ? <span>{t("Impact")} {task.impact_note}</span> : null}
        <span className="mv">
          {prev && <button className="btn xs" disabled={busy} aria-label={`${t("Move to previous column")}: ${t(COL_LABEL[prev])}`} title={`${t("Move to")} ${t(COL_LABEL[prev])}`} onClick={() => onMove(task, prev)}>◀</button>}
          {next && <button className="btn xs" disabled={busy} aria-label={`${t("Move to next column")}: ${t(COL_LABEL[next])}`} title={`${t("Move to")} ${t(COL_LABEL[next])}`} onClick={() => onMove(task, next)}>▶</button>}
        </span>
      </div>
    </div>
  );
}

interface Props { tasks: Tasks | null; loading: boolean; error: string | null; reload: () => void; draft: TaskIn | null; clearDraft: () => void; shopId?: string }

export default function Board({ tasks, loading, error, reload, draft, clearDraft, shopId }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<TaskIn>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  useEffect(() => { if (draft) { setForm({ ...EMPTY, ...draft }); setOpen(true); } }, [draft]);
  const set = <K extends keyof TaskIn>(k: K, v: TaskIn[K]) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setErr(null);
    try {
      const body: TaskIn = { ...form, detail: form.detail || null, owner: form.owner || null, deadline: form.deadline || null, impact_note: form.impact_note || null };
      await createTask(body, shopId);
      setForm(EMPTY); setOpen(false); clearDraft(); reload();
    } catch (x) { setErr(x instanceof Error ? x.message : String(x)); }
    setSaving(false);
  };
  const move = async (task: Task, s: TaskStatus) => {
    setBusy(task.id);
    try { await patchTask(task.id, { status: s }); reload(); } catch (x) { setErr(x instanceof Error ? x.message : String(x)); }
    setBusy(null);
  };
  const cols = tasks?.columns;
  return (
    <section className="zone">
      <ZoneHeader id="z7" eyebrow={t("7 · Team action board")} title={t("Accept · edit · assign · measure after 72 h")} hint={<button className="btn sm pri" onClick={() => { setOpen((o) => !o); if (open) clearDraft(); }}>{open ? t("Cancel") : t("New task")}</button>} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {err && !open && <div className="banner bad" role="alert">{err}</div>}
      {open && (
        <form className="card form" onSubmit={submit}>
          <label className="wide">{t("Title")}<input required minLength={3} maxLength={255} value={form.title} onChange={(e) => set("title", e.target.value)} /></label>
          <label className="wide">{t("Detail")}<textarea rows={2} value={form.detail ?? ""} onChange={(e) => set("detail", e.target.value)} /></label>
          <label>{t("Team")}<select value={form.team} onChange={(e) => set("team", e.target.value as Team)}>{TEAMS.map((x) => <option key={x} value={x}>{t(TEAM_LABEL[x])}</option>)}</select></label>
          <label>{t("Priority")}<select value={form.priority} onChange={(e) => set("priority", e.target.value as TaskIn["priority"])}>{PRIORITIES.map((x) => <option key={x}>{x}</option>)}</select></label>
          <label>{t("Owner")}<input value={form.owner ?? ""} onChange={(e) => set("owner", e.target.value)} /></label>
          <label>{t("Deadline")}<input type="date" value={form.deadline ?? ""} onChange={(e) => set("deadline", e.target.value)} /></label>
          <label className="wide">{t("Impact")}<input value={form.impact_note ?? ""} onChange={(e) => set("impact_note", e.target.value)} /></label>
          {form.source === "insight" && <div className="wide tiny">{t("Evidence")}: {JSON.stringify(form.evidence)}</div>}
          <div className="actions"><span className="err">{err}</span><button type="button" className="btn" onClick={() => { setOpen(false); clearDraft(); }}>{t("Cancel")}</button><button className="btn pri" disabled={saving}>{saving ? t("Saving…") : t("Save")}</button></div>
        </form>
      )}
      {loading && !tasks ? <Skeleton h={160} /> : cols && (
        <div className="board">
          {TASK_STATUSES.map((s) => (
            <div className="col" key={s}>
              <h3>{t(COL_LABEL[s])} <span>{cols[s]?.length ?? 0}</span></h3>
              {(cols[s] ?? []).length === 0 && <div className="tiny">{t("No tasks.")}</div>}
              {(cols[s] ?? []).map((task) => <TaskCard key={task.id} task={task} onMove={move} busy={busy === task.id} />)}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
