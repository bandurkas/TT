"use client";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { LangContext, type Lang, t as tr } from "@/lib/i18n";
import { qs, useApi } from "@/lib/api";
import { usePeriod } from "@/lib/period";
import type { Campaigns, Creators, Finding, Funnel as FunnelT, Insights, Overview, Products, TaskIn, Tasks, Trends, VideoProducts as VPT, Videos } from "@/lib/types";
import { Header, Rail } from "@/components/Shell";
import Health from "@/components/Health";
import Diagnosis from "@/components/Diagnosis";
import Trend from "@/components/Trend";
import Explorer from "@/components/Explorer";
import VideoProducts from "@/components/VideoProducts";
import Funnel from "@/components/Funnel";
import Opps from "@/components/Opps";
import Board, { draftFromFinding } from "@/components/Board";
import { scrollTo } from "@/components/ui";

function Dashboard() {
  const { state, update } = usePeriod();
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => { try { const s = localStorage.getItem("tt-lang"); if (s === "ru" || s === "en") setLangState(s); } catch { /* no storage */ } }, []);
  const setLang = (l: Lang) => { setLangState(l); document.documentElement.lang = l; try { localStorage.setItem("tt-lang", l); } catch { /* ignore */ } };
  const [tick, setTick] = useState(0);
  const q = state.query;
  const ov = useApi<Overview>(`/api/dashboard/overview${q}`, tick);
  const ins = useApi<Insights>(`/api/dashboard/insights${q}`, tick);
  const trd = useApi<Trends>(`/api/dashboard/trends${q}`, tick);
  const prods = useApi<Products>(`/api/analytics/products${q}`, tick);
  const vids = useApi<Videos>(`/api/analytics/videos${q}`, tick);
  const camps = useApi<Campaigns>(`/api/analytics/campaigns${q}`, tick);
  const crs = useApi<Creators>(`/api/analytics/creators${q}`, tick);
  const vp = useApi<VPT>(`/api/analytics/video-products${q}`, tick);
  const fn = useApi<FunnelT>(`/api/dashboard/funnel${q}`, tick);
  const tasks = useApi<Tasks>(`/api/tasks${qs({ shop_id: state.shopId })}`, tick);
  const [draft, setDraft] = useState<TaskIn | null>(null);
  const onCreateTask = useCallback((f: Finding) => { setDraft(draftFromFinding(f, lang)); setTimeout(() => scrollTo("z7"), 50); }, [lang]);
  const onOpenTab = useCallback((tab: string) => { update({ tab }); scrollTo("z4"); }, [update]);
  const all = [ov, ins, trd, prods, vids, camps, crs, vp, fn, tasks];
  const refreshing = all.some((x) => x.loading);
  const apiDown = all.every((x) => x.error !== null && !x.loading);
  const counts = useMemo(() => ({ recs: (ins.data?.opportunities.length ?? 0) + (ins.data?.risks.length ?? 0), board: tasks.data?.columns.today.length ?? 0 }), [ins.data, tasks.data]);
  return (
    <LangContext.Provider value={lang}>
      <div className="app">
        <Rail shop={ov.data?.shop.name} counts={counts} />
        <div className="main">
          <Header lang={lang} setLang={setLang} period={state} onPeriod={(p) => update(p)} overview={ov.data} onRefresh={() => setTick((x) => x + 1)} refreshing={refreshing} />
          <div className="wrap">
            {apiDown && <div className="banner bad" role="alert"><b>{tr(lang, "API unreachable")}</b> <span className="mono small">{ov.error}</span><button className="btn sm" onClick={() => setTick((x) => x + 1)}>{tr(lang, "Retry")}</button></div>}
            <Health ov={ov.data} loading={ov.loading} error={apiDown ? null : ov.error} reload={ov.reload} />
            <Diagnosis ins={ins.data} loading={ins.loading} error={apiDown ? null : ins.error} reload={ins.reload} onCreateTask={onCreateTask} onOpenTab={onOpenTab} />
            <Trend tr={trd.data} ov={ov.data} loading={trd.loading} error={apiDown ? null : trd.error} reload={trd.reload} />
            <Explorer tab={state.tab} setTab={(tab) => update({ tab })} apiDown={apiDown} products={prods} videos={vids} campaigns={camps} creators={crs} />
            <VideoProducts vp={vp.data} loading={vp.loading} error={apiDown ? null : vp.error} reload={vp.reload} />
            <Funnel fn={fn.data} loading={fn.loading} error={apiDown ? null : fn.error} reload={fn.reload} />
            <Opps ins={ins.data} loading={ins.loading} error={apiDown ? null : ins.error} reload={ins.reload} onCreateTask={onCreateTask} />
            <Board tasks={tasks.data} loading={tasks.loading} error={apiDown ? null : tasks.error} reload={tasks.reload} draft={draft} clearDraft={() => setDraft(null)} shopId={state.shopId} />
          </div>
        </div>
      </div>
    </LangContext.Provider>
  );
}

export default function Page() {
  return <Suspense fallback={<div className="wrap muted">Loading…</div>}><Dashboard /></Suspense>;
}
