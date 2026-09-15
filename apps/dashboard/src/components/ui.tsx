"use client";
import { useEffect } from "react";
import { useT } from "@/lib/i18n";
import type { Dec, Status } from "@/lib/types";
import { num } from "@/lib/format";

// Opens a <dialog> ref on mount and locks body scroll for as long as it's up; shared so every
// modal in the app opens/closes the same way instead of re-implementing this per component.
export function useDialogAutoOpen(ref: React.RefObject<HTMLDialogElement | null>) {
  useEffect(() => {
    const el = ref.current, prior = document.body.style.overflow;
    if (el && !el.open) el.showModal();
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prior; };
  }, [ref]);
}

export const Pill = ({ tone, children }: { tone: "good" | "bad" | "warn" | "info" | "gray"; children: React.ReactNode }) => (
  <span className={`pill p-${tone}`}>{children}</span>
);

export const statusTone = (s: Status): "good" | "bad" | "warn" | "gray" =>
  s === "good" ? "good" : s === "bad" ? "bad" : s === "warn" ? "warn" : "gray";

export const Conf = ({ c }: { c: "HIGH" | "MEDIUM" | "LOW" | string }) => {
  const t = useT();
  return <span><span className="muted">{t("Confidence")}</span> <b>{t(c)}</b></span>;
};

export const Sparkline = ({ values, tone }: { values: Dec[]; tone: "good" | "bad" | "accent" }) => {
  const v = values.map((x) => num(x) ?? 0);
  if (v.length < 2) return <svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true" />;
  const min = Math.min(...v, 0), max = Math.max(...v, 0);
  const span = max - min || 1;
  const pts = v.map((y, i) => `${(i / (v.length - 1)) * 100} ${26 - ((y - min) / span) * 24}`);
  return (
    <svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
      <path d={`M${pts.join(" L")}`} fill="none" stroke={`var(--${tone})`} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

export const Skeleton = ({ h = 120 }: { h?: number }) => <div className="card skel" style={{ minHeight: h }} aria-busy="true" />;

export const ErrorNote = ({ error, onRetry }: { error: string; onRetry?: () => void }) => {
  const t = useT();
  return (
    <div className="banner warn" role="alert">
      <span><b>{t("Failed to load")}</b> · <span className="mono small">{error}</span></span>
      {onRetry && <button className="btn sm" onClick={onRetry}>{t("Retry")}</button>}
    </div>
  );
};

export const ZoneHeader = ({ id, eyebrow, title, hint }: { id: string; eyebrow: string; title: string; hint?: React.ReactNode }) => (
  <header id={id}>
    <span className="eyebrow">{eyebrow}</span>
    <h2>{title}</h2>
    {hint && <span className="hint">{hint}</span>}
  </header>
);

export const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
