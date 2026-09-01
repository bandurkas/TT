// Shapes mirror apps/api/dashboard.py (+ src/domain/dashboard/*). Money/ratios = Decimal strings.
export type Dec = string;

export interface Meta {
  advertising?: Advertising;
  shop: { id: number; name: string; currency: string; timezone: string };
  period: { start: string; end: string };
  compare: { start: string; end: string };
  generated_at: string;
}

export type CardKind = "money" | "count" | "pct" | "ratio";
export type Status = "good" | "warn" | "bad" | "neutral";

export interface Card {
  key: string;
  kind: CardKind;
  value: Dec | null;
  prev: Dec | null;
  change_abs: Dec | null;
  change_pct: Dec | null;
  sparkline: Dec[];
  status: Status;
  note: string | null;
  provisional: boolean;
  meta: { units?: number; refunded?: number; ad_share?: Dec | null; floor?: Dec; break_even?: Dec | null; settled?: number; provisional?: number };
}

export interface Health {
  score: number;
  grade: "GOOD" | "FAIR" | "POOR";
  components: Record<string, number | null>;
}

export interface UnitEconomics {
  units: number;
  revenue_per_unit: Dec;
  fees_per_unit: Dec;
  cogs_per_unit: Dec;
  contribution_per_unit: Dec;
  ad_cost_per_unit: Dec;
  net_per_unit: Dec;
  ad_cost_is_estimate: boolean;
  revenue_basis?: string;
  calculation_difference?: Dec;
  contribution_difference?: Dec;
  contribution_rounding_per_unit?: Dec | null;
  rounding_per_unit?: Dec | null;
}

export interface Advertising {
  cost: string | null; known_cost: string; gmv_pay: string;
  covered_days: number; expected_days: number; missing_days: string[]; partial_days: string[];
  status: "reported" | "partial" | "missing";
  source: string; payment_basis?: string; taxes_and_credits?: string;
  reports: { filename: string; sha256: string; observed_at: string; timezone?: string; timezone_basis?: string; scope?: string; period_start?: string; period_end?: string }[];
  days: AdDay[]; manual_days: number; entry_note?: string;
}

export interface DataQuality {
  score: number;
  state: "OK" | "PARTIAL" | "POOR";
  reasons: string[];
  last_sync: string | null;
  freshness_minutes: number | null;
}

export interface Overview extends Meta {
  cards: Card[];
  health: Health;
  unit_economics: UnitEconomics | null;
  data_quality: DataQuality;
  advertising?: Advertising;
  totals: Record<string, Dec | number | null>;
  notes: string[];
}

export interface TrendPoint {
  date: string;
  gmv: Dec;
  net_seller_revenue: Dec;
  ad_cost: Dec | null;
  net_profit: Dec | null;
  cum_net_profit: Dec | null;
  orders: number;
  settled_orders: number;
  provisional_orders: number;
}

export interface TrendEvent {
  date: string;
  type: "ad_deduction" | "video_posted" | string;
  amount: Dec | null;
  label: string;
  video_id?: number | null;
  external_video_id?: string | null;
}

export interface GmvSource {
  date: string;
  gmv_total: Dec | null;
  gmv_video: Dec | null;
  gmv_product_card: Dec | null;
  gmv_live: Dec | null;
  gmv_max_pct: Dec | null;
}

export interface Trends extends Meta {
  series: TrendPoint[];
  events: TrendEvent[];
  gmv_sources: GmvSource[];
}

export type ProductStatus = "SCALE" | "HEALTHY" | "WATCH" | "INVESTIGATE" | "REDUCE" | "SMALL_SAMPLE";

export interface ProductRow {
  product_id: number;
  title: string;
  external_product_id: string | null;
  units: number;
  orders: number;
  gmv: Dec;
  net_seller_revenue: Dec;
  fees: Dec;
  affiliate: Dec;
  cogs: Dec;
  ad_cost: Dec | null;
  ad_cost_is_estimate: boolean;
  refunds: Dec;
  net_profit: Dec | null;
  net_margin: Dec | null;
  cvr: Dec | null;
  ctr: Dec | null;
  status: ProductStatus;
  status_reason: string;
}

export interface Products extends Meta {
  rows: ProductRow[];
  cvr_note: string;
  ad_cost_note: string;
}

export type VideoClass =
  | "WINNER" | "PROMISING" | "TRAFFIC_NO_SALES" | "LOW_ATTENTION" | "LOSER"
  | "FATIGUING" | "NEUTRAL" | "WATCH" | "INSUFFICIENT_DATA";

export interface VideoCard {
  video_id: number;
  external_video_id: string | null;
  caption: string | null;
  published_at: string | null;
  duration_seconds: number | null;
  age_days: number;
  views: number;
  impressions: number;
  clicks: number;
  orders: number;
  gmv: Dec;
  ctr: Dec | null;
  cvr: Dec | null;
  gpm: Dec | null;
  ad_spend: null;
  net_profit: null;
  ad_spend_note: string;
  clicks_note?: string;
  classification: VideoClass;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reasons: string[];
}

export interface Videos extends Meta {
  cards: VideoCard[];
  clicks_note: string;
  ad_spend_note: string;
}

export interface Deduction {
  date: string;
  amount: Dec;
  [k: string]: unknown;
}

export interface Campaigns extends Meta {
  available: boolean;
  reason: string;
  shop_level_ad_cost: Dec | null;
  deductions: Deduction[];
  rows: unknown[];
}

export interface CreatorRow {
  creator: string;
  orders?: number;
  gmv?: Dec;
  affiliate_commission?: Dec;
  profit_after_commission?: Dec;
  [k: string]: unknown;
}

export interface Creators extends Meta {
  rows: CreatorRow[];
  note: string;
}

export interface FunnelStage { name: string; count: number; note: string | null }
export interface FunnelStep {
  from: string; to: string; count: number; rate: Dec | null; baseline_rate: Dec | null;
  delta_pct: Dec | null; timing_only: boolean;
}
export interface FunnelDiagnosis {
  stage_from: string; stage_to: string; current_rate: Dec; baseline_rate: Dec; delta_pct: Dec;
  lost_orders: Dec; lost_profit: Dec | null; evidence: string[]; estimated: true;
}
export interface WaterfallStep { key: string; amount: Dec | null; measured: boolean; subtotal?: boolean }
export interface Funnel extends Meta {
  stages: FunnelStage[];
  steps: FunnelStep[];
  diagnosis: FunnelDiagnosis | null;
  baseline_note: string;
  waterfall: { orders: number; provisional_orders: number; steps: WaterfallStep[]; note: string };
}

export type Severity = "CRITICAL" | "WARNING" | "OPPORTUNITY" | "INFO";
export interface Finding {
  key: string;
  kind: "risk" | "opportunity";
  severity: Severity;
  title: string;
  detail: string;
  impact: Dec | null;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  source: string;
  measured: boolean;
  links: { tab?: string; product_id?: number; video_id?: number; zone?: string };
}
export interface Insights extends Meta {
  findings: Finding[];
  opportunities: Finding[];
  risks: Finding[];
  note: string;
}

export type Team = "performance" | "video" | "design" | "product" | "finance" | "management";
export type Priority = "P1" | "P2" | "P3";
export type TaskStatus = "today" | "in_progress" | "review" | "done";
export const TEAMS: Team[] = ["performance", "video", "design", "product", "finance", "management"];
export const PRIORITIES: Priority[] = ["P1", "P2", "P3"];
export const TASK_STATUSES: TaskStatus[] = ["today", "in_progress", "review", "done"];

export interface Task {
  id: number;
  shop_id: number;
  title: string;
  detail: string | null;
  team: Team;
  priority: Priority;
  status: TaskStatus;
  owner: string | null;
  deadline: string | null;
  impact_note: string | null;
  source: string | null;
  evidence: Record<string, unknown>;
  result_note: string | null;
  done_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface TaskIn {
  title: string; detail?: string | null; team: Team; priority?: Priority; status?: TaskStatus;
  owner?: string | null; deadline?: string | null; impact_note?: string | null; source?: string;
  evidence?: Record<string, unknown>;
}
export interface TaskPatch {
  title?: string; detail?: string | null; team?: Team; priority?: Priority; status?: TaskStatus;
  owner?: string | null; deadline?: string | null; impact_note?: string | null; result_note?: string | null;
}
export interface Tasks {
  shop_id: number;
  tasks: Task[];
  columns: Record<TaskStatus, Task[]>;
}

// GET /api/analytics/video-products — videos → product cards dependency
export interface VPDay { date: string; gmv_video: Dec; gmv_product_card: Dec; gmv_live: Dec; video_views: number }
export interface VPLag { lag_days: number; correlation: Dec | null; n: number }
export interface VPVideoRef {
  video_id: number; external_video_id: string | null; caption: string | null;
  impressions: number; clicks: number; units_sold: number; gmv: Dec; customers: number; ctr: Dec | null;
}
export interface VPProduct {
  product_id: number; title: string; external_product_id: string | null; gmv: Dec; orders: number; net_profit: Dec | null;
  status: ProductStatus | "NO_SALES"; video_gmv: Dec; video_units: number; video_share: Dec | null;
  video_impressions: number; video_clicks: number; videos: VPVideoRef[];
}
export interface VPProductRef { product_id: number; title: string; impressions: number; clicks: number; units_sold: number; gmv: Dec; customers: number; ctr: Dec | null }
export interface VPVideo { video_id: number; external_video_id: string | null; caption: string | null; views: number; classification: VideoClass | null; products: VPProductRef[] }
export interface VideoProducts extends Meta {
  shop_split: { gmv_video: Dec; gmv_product_card: Dec; gmv_live: Dec; gmv_total: Dec; video_share: Dec | null; days: VPDay[] };
  dependency: { lags: VPLag[]; best_lag: number | null; note: string };
  products: VPProduct[];
  videos: VPVideo[];
  history?: VPHistory;
  notes: string[];
}

// history block of /api/analytics/video-products (compute.video_history)
export interface VPHistDay { date: string; gmv: Dec; orders: number; net_profit: Dec | null; video_gmv: Dec; non_video_gmv: Dec; video_clicks: number; video_impressions: number; video_units: number }
export interface VPHistEvent { date: string; video_id: number; external_video_id: string | null; type: "published" }
export type LiftVerdict = "positive" | "neutral" | "negative" | "insufficient" | "pending" | "out_of_range";
export interface VPLift {
  video_id: number; external_video_id: string | null; published: string;
  before: { orders: number; gmv: Dec; orders_per_day: Dec };
  after: { orders: number; gmv: Dec; orders_per_day: Dec; video_gmv: Dec };
  lift_pct: Dec | null; verdict: LiftVerdict; note: string;
}
export interface VPHistProduct { product_id: number; title: string; days: VPHistDay[]; events: VPHistEvent[]; lifts: VPLift[] }
export interface VPHistVideoDay { date: string; views: number; impressions: number; clicks: number; orders: number; gmv: Dec }
export type VideoPhase = "rising" | "steady" | "fading" | "insufficient";
export interface VPHistVideo {
  video_id: number; external_video_id: string | null; caption: string | null; published_at: string | null;
  days: VPHistVideoDay[]; peak_day: string; peak_views: number; recent_vs_peak: Dec | null; phase: VideoPhase;
}
export interface VPHistory { products: VPHistProduct[]; videos: VPHistVideo[]; notes: string[] }

// GET /api/advertising (also embedded as overview.advertising) — src/domain/reports.advertising_summary
export interface AdDay {
  date: string; cost: Dec; partial: boolean; sku_orders: number; gross_revenue: Dec;
  source: "shop_overview" | "manual_entry" | string; observed_at: string | null; note: string | null;
}
export interface ManualAdIn { date: string; cost: string; sku_orders: number; gross_revenue: string; final: boolean; note?: string | null }
export interface ManualAdOut { report_id: number; partial?: boolean; unchanged?: boolean; recomputed?: { orders: number; inserted: number }; day: AdDay | null }

// GET /api/costs — src/domain/costs.cost_overview
export interface CostLot {
  id: number; scope: "all" | "product" | "sku"; product_id: number | null; sku_id: number | null; received_on: string;
  unit_cost: Dec; quantity: number | null; currency: string; note: string | null; active: boolean; consumed?: number; remaining?: number | null;
}
export interface CostSku {
  sku_id: number; external_sku_id: string | null; product_id: number; product_title: string; sku_title: string | null;
  current_cost: Dec | null; source: "lot" | "seed" | "default" | "none"; lot_id: number | null; effective_from: string | null;
  history: { effective_from: string; effective_to: string | null; cogs_per_unit: Dec; notes: string | null }[];
}
export interface Costs extends Meta { default_cogs_per_unit: Dec | null; lots: CostLot[]; skus: CostSku[]; note: string }
export interface LotIn { scope: "all" | "product" | "sku"; product_id?: number | null; sku_id?: number | null; received_on: string; unit_cost: string; quantity?: number | null; note?: string | null }
export interface LotPatch { received_on?: string; unit_cost?: string; quantity?: number; note?: string | null; active?: boolean }
export interface CostWriteOut { lot_id?: number; default_cogs_per_unit?: Dec | null; versions: number; skus_with_lots: number; recomputed: { orders: number; inserted: number } }
