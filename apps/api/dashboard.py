"""Dashboard API (SPEC §54). Read-only analytics over pre-aggregated tables + tasks CRUD.
All money = Decimal serialised as strings; ad cost always labelled BLENDED/estimate."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.analytics.creative_scoring import ScoringConfig
from src.db.models import Task
from src.db.session import SessionLocal
from src.domain.dashboard import compute as C
from src.domain.dashboard import insights as I
from src.domain.dashboard import loaders as L
from src.domain.dashboard import order_loaders as OL
from src.domain.reports import advertising_summary

router = APIRouter(prefix="/api")
TASK_STATUSES = ("today", "in_progress", "review", "done")
TEAMS = ("performance", "video", "design", "product", "finance", "management")
PRIORITIES = ("P1", "P2", "P3")
DEFAULT_FLOOR = Decimal("0.10")
DEFAULT_MIN_ORDERS = 5


def get_session():
    with SessionLocal() as s:
        yield s


class Ctx:
    def __init__(self, session: Any, shop_id: int | None, start: date | None, end: date | None,
                 cmp_start: date | None, cmp_end: date | None):
        self.session = session
        self.shop, self.cfg = L.shop_and_config(session, shop_id)
        self.tz = self.shop.timezone or "Asia/Jakarta"
        self.today = L.today_local(self.shop)
        self.period, self.compare = C.default_periods(self.today, start, end, cmp_start, cmp_end)
        self.floor = Decimal(str(self.cfg.minimum_net_margin)) if self.cfg else DEFAULT_FLOOR
        self.min_orders = int(self.cfg.minimum_sample_orders) if self.cfg else DEFAULT_MIN_ORDERS
        self._memo: dict[tuple, Any] = {}

    def memo(self, key: tuple, fn):
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    def profits(self, period: C.Period):
        return self.memo(("profits", period.start, period.end),
                         lambda: L.current_profits(self.session, self.shop.id, period.start, period.end, self.tz))

    def daily(self, period: C.Period):
        return self.memo(("daily", period.start, period.end),
                         lambda: L.shop_daily(self.session, self.shop.id, period.start, period.end))

    def funnel_days(self, period: C.Period):
        return self.memo(("funnel", period.start, period.end),
                         lambda: L.shop_funnel_by_day(self.session, self.shop.id, period.start, period.end))

    def totals(self, period: C.Period) -> C.Totals:
        def build():
            t = C.sum_daily(self.daily(period), period, self.funnel_days(period), self.profits(period)[1])
            ad = self.advertising(period)
            t.ad_cost_known = ad["cost"] is not None
            t.ad_cost_partial = bool(ad["partial_days"])
            t.ad_cost = ad["known_cost"]
            t.net_profit = t.contribution - t.ad_cost
            return t
        return self.memo(("totals", period.start, period.end), build)

    def advertising(self, period):
        return self.memo(("advertising", period.start, period.end), lambda: advertising_summary(
            self.session, self.shop.id, period.start, period.end, self.tz))

    def meta(self) -> dict[str, Any]:
        return {"shop": {"id": self.shop.id, "name": self.shop.name, "currency": self.shop.currency,
                         "timezone": self.tz},
                "period": {"start": self.period.start, "end": self.period.end},
                "compare": {"start": self.compare.start, "end": self.compare.end},
                "generated_at": datetime.now(UTC)}


def ctx_dep(shop_id: int | None = None, start: date | None = Query(None, alias="from"),
            end: date | None = Query(None, alias="to"), cmp_from: date | None = None,
            cmp_to: date | None = None, session: Any = Depends(get_session)) -> Ctx:
    if (cmp_from is None) != (cmp_to is None):
        raise HTTPException(422, "cmp_from and cmp_to must be given together")
    if cmp_from and cmp_to and cmp_from > cmp_to:
        cmp_from, cmp_to = cmp_to, cmp_from
    try:
        return Ctx(session, shop_id, start, end, cmp_from, cmp_to)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


def shop_dep(shop_id: int | None = None, session: Any = Depends(get_session)):
    try:
        return L.shop_and_config(session, shop_id)[0], session
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


def _n(d: dict[str, Any]) -> dict[str, Any]:
    return C.normalize(d)


def _overview(c: Ctx) -> dict[str, Any]:
    cur, prev = c.totals(c.period), c.totals(c.compare)
    rows = c.daily(c.period)
    sync_at, fresh = L.last_sync(c.session, c.shop.id)
    missing, unmapped = L.cogs_gaps(c.session, c.shop.id, c.period.start, c.period.end, c.tz)
    dq = C.data_quality(fresh, cur, missing, unmapped)
    zone1 = C.business_health(cur, prev, rows, c.period, c.floor, dq)
    return {**c.meta(), **zone1, "advertising": c.advertising(c.period), "data_quality": {"score": dq.score, "state": dq.state.value,
                                                   "reasons": list(dq.reasons), "last_sync": sync_at,
                                                   "freshness_minutes": fresh},
            "totals": {k: (None if (k == "ad_cost" and not cur.ad_cost_known) or (k == "net_profit" and not cur.profit_known) else getattr(cur, k)) for k in C.DAILY_FIELDS} | {"refunded_orders": cur.refunded_orders},
            "notes": ["Ad spend = reported daily Cost; GMV Pay is a separate payment. Order attribution is same-day BLENDED (LOW).",
                      "Provisional orders: fees estimated from trailing settled ratio; not final.",
                      "Reported ROAS / per-campaign cost: NOT AVAILABLE until the TikTok Ads app is approved."]}


@router.get("/dashboard/overview")
def overview(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    return _n(_overview(c))


@router.get("/dashboard/trends")
def trends(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    rows = c.daily(c.period)
    series = C.trend_series(rows, c.period)
    events = [{"date": d["date"], "type": "ad_deduction", "amount": d["amount"],
               "label": f"GMV Pay payment {d['amount']} (not Cost)"}
              for d in L.ad_deductions(c.session, c.shop.id, c.period.start, c.period.end, c.tz)]
    _, meta = _video_rows(c)
    for v in meta.values():
        pday = C._pub_date(v, c.tz)
        if pday and c.period.start <= pday <= c.period.end:
            events.append({"date": pday, "type": "video_posted", "amount": None, "video_id": v.id,
                           "external_video_id": v.external_video_id,
                           "label": f"new video {v.external_video_id}"})
    events.sort(key=lambda e: e["date"])
    sm = L.shop_metrics(c.session, c.shop.id, c.period.start, c.period.end)
    for e in events:
        e.setdefault("video_id", None)
        e.setdefault("external_video_id", None)
    return _n({**c.meta(), "series": series, "events": events,
            "gmv_sources": [{"date": m.metric_date, "gmv_total": m.gmv_total, "gmv_video": m.gmv_video,
                             "gmv_product_card": m.gmv_product_card, "gmv_live": m.gmv_live,
                             "gmv_max_pct": m.gross_revenue_gmv_max_pct} for m in sm]})


@router.get("/analytics/products")
def products(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    pd = L.product_daily(c.session, c.shop.id, c.period.start, c.period.end)
    pf = L.product_funnel(c.session, c.shop.id, c.period.start, c.period.end)
    rows = C.product_rows(pd, L.products(c.session, c.shop.id), c.period, pf, c.floor, c.min_orders)
    return _n({**c.meta(), "rows": rows, "cvr_note": C.NOT_AVAILABLE + ": product clicks not in Shop API",
               "ad_cost_note": "BLENDED estimate: reported daily Cost split by same-day revenue; GMV Pay excluded"})


def _video_rows(c: Ctx):
    return c.memo(("video_rows", c.period.start, c.period.end),
                  lambda: L.videos_with_metrics(c.session, c.shop.id, c.period.start, c.period.end))


def _videos(c: Ctx) -> list[dict[str, Any]]:
    daily, meta = _video_rows(c)
    cfg = ScoringConfig(minimum_net_margin=c.floor, minimum_sample_orders=c.min_orders,
                        minimum_sample_impressions=int(c.cfg.minimum_sample_impressions) if c.cfg else 1000,
                        minimum_sample_clicks=int(c.cfg.minimum_sample_clicks) if c.cfg else 30)
    return c.memo(("videos", c.period.start, c.period.end),
                  lambda: C.video_cards(daily, meta, c.period, c.today, cfg, c.tz))


@router.get("/analytics/videos")
def videos(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    return _n({**c.meta(), "cards": _videos(c),
               "clicks_note": "derived: views × click_through_rate", 
               "ad_spend_note": C.NOT_AVAILABLE + ": per-video ad cost needs Ads API"})


@router.get("/analytics/video-products")
def video_products(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    """Videos -> product cards: per video × product measured impressions/clicks/GMV + shop-level split
    (video vs product-card GMV) + lagged dependency of product-card GMV on video views."""
    pd = L.product_daily(c.session, c.shop.id, c.period.start, c.period.end)
    pf = L.product_funnel(c.session, c.shop.id, c.period.start, c.period.end)
    pmeta = L.products(c.session, c.shop.id)
    prows = C.product_rows(pd, pmeta, c.period, pf, c.floor, c.min_orders)
    daily, vmeta = _video_rows(c)
    cards = _videos(c)
    views = {vid: sum(int(r.views or 0) for r in rows) for vid, rows in daily.items()}
    vclass = {cd["video_id"]: cd["classification"] for cd in cards}
    vpm = L.video_product_metrics(c.session, c.shop.id, c.period.start, c.period.end)
    products, videos = C.video_product_map(vpm, prows, pmeta, vmeta, views, vclass, c.period)
    sm = L.shop_metrics(c.session, c.shop.id, c.period.start, c.period.end)
    views_by_day: dict[date, int] = {}
    for rows in daily.values():
        for r in rows:
            views_by_day[r.metric_date] = views_by_day.get(r.metric_date, 0) + int(r.views or 0)
    days = [{"date": m.metric_date, "gmv_video": C._d(m.gmv_video), "gmv_product_card": C._d(m.gmv_product_card),
             "gmv_live": C._d(m.gmv_live), "video_views": views_by_day.get(m.metric_date, 0)} for m in sm]
    gv = sum((d["gmv_video"] for d in days), Decimal(0))
    gpc = sum((d["gmv_product_card"] for d in days), Decimal(0))
    gl = sum((d["gmv_live"] for d in days), Decimal(0))
    tot = gv + gpc + gl
    loaded_start = c.period.start - timedelta(days=2 * C.LIFT_WINDOW)
    pd_hist = L.product_daily(c.session, c.shop.id, loaded_start, c.period.end)
    history = C.video_history(vpm, pd_hist, daily, vmeta, pmeta, c.period, c.min_orders,
                              data_end=min(c.period.end, c.today - timedelta(days=1)),
                              loaded_start=loaded_start, tz=c.tz)
    return _n({**c.meta(), "history": history,
               "shop_split": {"gmv_video": gv, "gmv_product_card": gpc, "gmv_live": gl, "gmv_total": tot,
                              "video_share": C.ratio(gv, tot) if tot else None, "days": days},
               "dependency": C.lag_dependency(days), "products": products, "videos": videos,
               "notes": ["per video × product impressions/clicks/GMV are measured by TikTok video analytics",
                         ("product-card GMV without a video is organic/search/GMV Max product-card traffic; "
                         "its impressions are NOT AVAILABLE"),
                         "shop split from shop_metrics (gmv_video / gmv_product_card / gmv_live)"]})


@router.get("/analytics/campaigns")
def campaigns(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    ded = L.ad_deductions(c.session, c.shop.id, c.period.start, c.period.end, c.tz)
    ad = c.advertising(c.period)
    return _n({**c.meta(), "available": False, "reason": "Shop overview export has no campaign IDs",
               "advertising": ad, "shop_level_ad_cost": ad["cost"], "deductions": ded, "rows": []})


@router.get("/analytics/creators")
def creators(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    rows = c.profits(c.period)[0]
    agg = L.affiliate_totals(rows)
    return _n({**c.meta(), "rows": [{"creator": "Affiliate (aggregated)", **agg}],
               "note": "Per-creator attribution NOT AVAILABLE from Shop API orders; affiliate commission is measured."})


def _funnel(c: Ctx) -> dict[str, Any]:
    cur = L.funnel_counts(c.session, c.shop.id, c.period, c.tz)
    base = L.funnel_counts(c.session, c.shop.id, c.compare, c.tz)
    t = c.totals(c.period)
    avg_profit = (t.contribution / t.orders).quantize(Decimal(1)) if t.orders and t.profit_inputs_known else None
    return c.memo(("funnel_view",), lambda: C.funnel_view(cur, base, avg_profit))


@router.get("/dashboard/funnel")
def funnel(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    rows = c.profits(c.period)[0]
    return _n({**c.meta(), **_funnel(c), "waterfall": C.waterfall(rows, c.advertising(c.period))})


@router.get("/dashboard/insights")
def insights(c: Ctx = Depends(ctx_dep)) -> dict[str, Any]:
    cur, prev = c.totals(c.period), c.totals(c.compare)
    pd = L.product_daily(c.session, c.shop.id, c.period.start, c.period.end)
    pf = L.product_funnel(c.session, c.shop.id, c.period.start, c.period.end)
    prods = C.product_rows(pd, L.products(c.session, c.shop.id), c.period, pf, c.floor, c.min_orders)
    items = I.findings(cur, prev, c.floor, prods, _videos(c), _funnel(c), c.min_orders)
    return _n({**c.meta(), "findings": items,
               "opportunities": [f for f in items if f["kind"] == "opportunity"],
               "risks": [f for f in items if f["kind"] == "risk" and f["severity"] in ("CRITICAL", "WARNING")],
               "note": "Deterministic rules; impact = estimate unless measured=true. LLM narrative: not enabled."})


# --- tasks (existing `tasks` table: why/expected_impact/source_entity/evaluation JSONB) ---------
@router.get("/orders")
def order_journal(c: Ctx = Depends(ctx_dep), search: str = Query("", max_length=100),
                  state: Literal["all", "final", "preliminary", "not_calculated"] = "all",
                  loss_only: bool = False, offset: int = Query(0, ge=0),
                  limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    return _n({**c.meta(), **OL.page(c.session, c.shop.id, c.period.start, c.period.end, c.tz,
                                    search.strip(), state, loss_only, offset, limit)})


@router.get("/orders/{order_id}")
def order_details(order_id: int, dep: Any = Depends(shop_dep)) -> dict[str, Any]:
    shop, session = dep
    try:
        return _n({"shop_id": shop.id, "timezone": shop.timezone,
                   **OL.detail(session, shop.id, order_id)})
    except LookupError as e:
        raise HTTPException(404, "order not found") from e


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    detail: str | None = None
    team: Literal[TEAMS]  # type: ignore[valid-type]
    priority: Literal[PRIORITIES] = "P2"  # type: ignore[valid-type]
    status: Literal[TASK_STATUSES] = "today"  # type: ignore[valid-type]
    owner: str | None = None
    deadline: date | None = None
    impact_note: str | None = None
    source: str | None = "manual"
    evidence: dict[str, Any] = Field(default_factory=dict)


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=255)
    detail: str | None = None
    team: Literal[TEAMS] | None = None  # type: ignore[valid-type]
    priority: Literal[PRIORITIES] | None = None  # type: ignore[valid-type]
    status: Literal[TASK_STATUSES] | None = None  # type: ignore[valid-type]
    owner: str | None = None
    deadline: date | None = None
    impact_note: str | None = None
    result_note: str | None = None


def _dl(d: date | None) -> datetime | None:
    return datetime(d.year, d.month, d.day, tzinfo=UTC) if d else None


def task_out(t: Task) -> dict[str, Any]:
    ev = t.evaluation or {}
    return {"id": t.id, "shop_id": t.shop_id, "title": t.title, "detail": t.why, "team": t.team,
            "priority": t.priority, "status": t.status, "owner": t.owner,
            "deadline": t.deadline.date() if t.deadline else None,
            "impact_note": (t.expected_impact or {}).get("note"),
            "source": (t.source_entity or {}).get("source"),
            "evidence": {k: v for k, v in (t.source_entity or {}).items() if k != "source"},
            "result_note": ev.get("note"), "done_at": ev.get("done_at"),
            "created_at": t.created_at, "updated_at": t.updated_at}


@router.get("/tasks")
def list_tasks(status: str | None = None, dep: Any = Depends(shop_dep)) -> dict[str, Any]:
    shop, session = dep
    if status and status not in TASK_STATUSES:
        raise HTTPException(422, f"status must be one of {TASK_STATUSES}")
    q = select(Task).where(Task.shop_id == shop.id)
    if status:
        q = q.where(Task.status == status)
    rows = [task_out(t) for t in session.scalars(q.order_by(Task.priority, Task.created_at.desc()))]
    return {"shop_id": shop.id, "tasks": rows,
            "columns": {s: [t for t in rows if t["status"] == s] for s in TASK_STATUSES}}


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, dep: Any = Depends(shop_dep)) -> dict[str, Any]:
    shop, session = dep
    t = Task(shop_id=shop.id, title=body.title, why=body.detail, team=body.team, priority=body.priority,
             status=body.status, owner=body.owner, deadline=_dl(body.deadline),
             expected_impact={"note": body.impact_note} if body.impact_note else None,
             source_entity={**body.evidence, "source": body.source or "manual"})
    session.add(t)
    session.commit()
    session.refresh(t)
    return task_out(t)


@router.patch("/tasks/{task_id}")
def patch_task(task_id: int, body: TaskPatch, session: Any = Depends(get_session)) -> dict[str, Any]:
    t = session.get(Task, task_id)
    if t is None:
        raise HTTPException(404, "task not found")
    data = body.model_dump(exclude_unset=True)
    for k in ("title", "team", "priority", "status", "owner"):
        if k in data:
            setattr(t, k, data[k])
    if "detail" in data:
        t.why = data["detail"]
    if "deadline" in data:
        t.deadline = _dl(data["deadline"])
    if "impact_note" in data:
        t.expected_impact = {**(t.expected_impact or {}), "note": data["impact_note"]}
    ev = dict(t.evaluation or {})
    if "result_note" in data:
        ev["note"] = data["result_note"]
    if data.get("status") == "done" and not ev.get("done_at"):
        ev["done_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    elif "status" in data and data["status"] != "done":
        ev.pop("done_at", None)
    t.evaluation = ev or None
    session.commit()
    session.refresh(t)
    return task_out(t)
