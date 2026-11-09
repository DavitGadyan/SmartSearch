export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
/** Console requests go through the same-origin proxy (app/api/admin), which holds the API key server-side. */
const ADMIN_PROXY = "/api/admin";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

export function qs(params: Params = {}): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init: RequestInit = {}, admin = false): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  if (init.body) headers["Content-Type"] = "application/json";
  const res = await fetch(admin ? `${ADMIN_PROXY}${path}` : `${API_URL}/api/v1${path}`, { ...init, headers });
  if (!res.ok) {
    if (admin && res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/admin/login")) {
      location.assign(`/admin/login?next=${encodeURIComponent(location.pathname + location.search)}`);
    }
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>(`${path}${qs(params)}`),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  admin: {
    get: <T>(path: string, params?: Params) => request<T>(`${path}${qs(params)}`, {}, true),
    post: <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) }, true),
    patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }, true),
  },
};

// ---------- types (mirror backend schemas) ----------
export type Product = {
  id: number;
  name: string;
  product_class: string | null;
  brand: string | null;
  price: number;
  rating: number | null;
  review_count: number;
  in_stock: boolean;
  is_new: boolean;
  attributes: Record<string, string | number | boolean>;
  image_url: string | null;
  position?: number | null;
  score?: number | null;
  explanation?: Explanation | null;
};

export type Explanation = {
  strategy: string;
  note?: string;
  retrieved_by?: string[];
  bm25_rank?: number | null;
  semantic_rank?: number | null;
  ltr_score?: number | null;
  personal_boost?: number | null;
  explored?: boolean;
  factors?: { feature: string; label: string; value: number; contribution: number }[];
  reason?: string;
  relevance?: { expected_grade: number; p_irrelevant: number; p_exact: number; source: string };
};

export type ProductDetail = Product & { description: string | null; category_hierarchy: string | null; similar: Product[] };

export type Facet = { name: string; values: { value: string; count: number }[] };

export type SearchResponse = {
  request_id: string;
  query: string;
  parsed: {
    text: string;
    price_min: number | null;
    price_max: number | null;
    top_class: string | null;
    top_class_sim: number;
    intent?: { class: string | null; p: number; source: string } | null;
    bandit?: { action: string; propensity: number; group: string; segment: string; device: string } | null;
  };
  total: number;
  page: number;
  page_size: number;
  items: Product[];
  facets: Facet[];
  strategy: string;
  variant: string | null;
  experiment_key: string | null;
  ranking_model_version: string;
  retrieval: Record<string, number>;
  latency_ms: number;
  explored_product_id: number | null;
};

export type Suggestion = { text: string; kind: "query" | "category" | "product" };

export type DemoUser = {
  id: string;
  persona: string;
  segment: string;
  traits: { style?: Record<string, number>; brands?: Record<string, number>; classes?: Record<string, number>; log_price_offset?: number };
  interactions: number;
};

export type Experiment = {
  key: string;
  name: string;
  hypothesis: string | null;
  status: "draft" | "running" | "completed" | "archived";
  surface: string;
  variants: { key: string; name?: string; description?: string; strategy?: string; explore?: boolean; ui?: UiConfig | null; effect?: Record<string, number> | null; weight: number }[];
  traffic_allocation: number;
  primary_metric: string;
  secondary_metrics: string[];
  guardrail_metrics: string[];
  config: Record<string, unknown> & { summary?: string; simulated_traffic?: SimulatedTraffic };
  start_at: string | null;
  end_at: string | null;
  created_at: string;
  assigned_users: number;
};

export type TestResult = {
  metric: string;
  method: string;
  control: number;
  treatment: number;
  abs_diff: number;
  rel_lift: number | null;
  ci_low: number;
  ci_high: number;
  p_value: number;
  statistic: number | null;
  n_control: number;
  n_treatment: number;
  alpha: number;
  significant: boolean;
  p_value_bh?: number;
  significant_bh?: boolean;
  breached?: boolean;
  extra?: Record<string, unknown>;
};

export type ExperimentAnalysis = {
  experiment: Experiment;
  status: "ok" | "no_data";
  days_running: number | null;
  srm: { chi2: number; p_value: number; srm_detected: boolean; observed: Record<string, number>; expected: Record<string, number> };
  variants: Record<string, number | string>[];
  comparisons: {
    control: string;
    treatment: string;
    n_control: number;
    n_treatment: number;
    primary_metric: string;
    metrics: Record<string, TestResult>;
    guardrails: Record<string, TestResult>;
    revenue: { bootstrap: TestResult; cuped: TestResult & { theta: number; variance_reduction: number } };
    power: {
      baseline_rate?: number;
      mde_rel_planned?: number;
      required_n_per_arm?: number;
      current_n_per_arm?: number;
      progress?: number;
      mde_rel_at_current_n?: number;
      achieved_power_for_observed_effect?: number;
      days_to_required_n?: number | null;
    };
    sequential: { lambda?: number; always_valid_p?: number; tau?: number };
    decision: { recommendation: string; label: string; guardrails_breached: string[]; narrative: string };
  }[];
  daily: { variant: string; days: string[]; cum_users: number[]; cum_rpv: number[]; cum_purchases_per_user: number[]; daily_ctr: number[]; daily_revenue: number[] }[];
  metric_labels: Record<string, string>;
  generated_at: string;
};

// ---------- console ----------
export type Overview = {
  window: { start: string; end: string; days: number };
  kpis: Record<string, number>;
  previous: Record<string, number>;
  deltas: Record<string, number | null>;
  daily: Record<string, number | string>[];
};

// ---------- assistant ----------
export type AgentDecisions = {
  route?: { route: string; p: number; source: string };
  relevance?: { product_id: number; expected_grade: number; p_irrelevant: number; source: string }[];
};
export type AgentAction = {
  type: "add_to_cart" | "order_placed";
  product_id?: number | null;
  quantity?: number | null;
  product?: Product | null;
  order_id?: string | null;
  checkout_session_id?: string | null;
  total?: number | null;
};
export type ToolTrace = { tool: string; input: Record<string, unknown>; summary: string };
export type ChatResponse = {
  message: string;
  products: Product[];
  preferences: Record<string, unknown>;
  trace: ToolTrace[];
  provider: "claude" | "rule_based";
  model: string | null;
  latency_ms: number;
  decisions?: AgentDecisions;
  actions?: AgentAction[];
};

// ---------- Agentic Commerce Protocol (the storefront is a client of its own merchant endpoints) ----------
export type AcpLineItem = { id: string; item: { id: string; quantity: number }; base_amount: number; discount: number; subtotal: number; tax: number; total: number };
export type AcpFulfillmentOption = { type: "shipping"; id: string; title: string; subtitle?: string | null; carrier?: string | null; earliest_delivery_time?: string; latest_delivery_time?: string; subtotal: number; tax: number; total: number };
export type AcpAddress = { name: string; line_one: string; line_two?: string | null; city: string; state: string; country: string; postal_code: string };
export type AcpSession = {
  id: string;
  status: "not_ready_for_payment" | "ready_for_payment" | "completed" | "canceled" | "in_progress";
  currency: string;
  line_items: AcpLineItem[];
  fulfillment_address: AcpAddress | null;
  fulfillment_options: AcpFulfillmentOption[];
  fulfillment_option_id: string | null;
  totals: { type: string; display_text: string; amount: number }[];
  messages: { type: "info" | "error"; code?: string; param?: string; content?: string }[];
  order?: { id: string; checkout_session_id: string; permalink_url: string } | null;
};

const ACP_KEY = process.env.NEXT_PUBLIC_ACP_API_KEY ?? "dev-acp-key";
async function acpRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}/acp${path}`, {
    ...init,
    headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${ACP_KEY}`, "API-Version": "2025-09-29", ...(init.headers as Record<string, string>) },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const e = await res.json();
      msg = e.message ?? msg;
    } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json();
}
export const acp = {
  create: (items: { id: string; quantity: number }[], address?: AcpAddress) => acpRequest<AcpSession>("/checkout_sessions", { method: "POST", body: JSON.stringify({ items, fulfillment_address: address }) }),
  update: (id: string, body: { items?: { id: string; quantity: number }[]; fulfillment_address?: AcpAddress; fulfillment_option_id?: string }) => acpRequest<AcpSession>(`/checkout_sessions/${id}`, { method: "POST", body: JSON.stringify(body) }),
  delegatePayment: (sessionId: string, maxAmount: number, name: string) =>
    acpRequest<{ id: string }>("/agentic_commerce/delegate_payment", {
      method: "POST",
      body: JSON.stringify({
        payment_method: { type: "card", card_number_type: "fpan", number: "4242424242424242", exp_month: "12", exp_year: "2030", name, metadata: {} },
        allowance: { reason: "one_time", max_amount: maxAmount, currency: "usd", checkout_session_id: sessionId, merchant_id: "smartsearch-demo", expires_at: new Date(Date.now() + 15 * 60_000).toISOString() },
        risk_signals: [],
        metadata: { source: "storefront" },
      }),
    }),
  complete: (id: string, token: string) => acpRequest<AcpSession>(`/checkout_sessions/${id}/complete`, { method: "POST", body: JSON.stringify({ payment_data: { token, provider: "smartsearch_mock" } }) }),
};

// ---------- UI experiments ----------
export type UiConfig = {
  cta_label: string;
  cta_style: "dark" | "glass" | "accent";
  cta_icon: boolean;
  show_ratings: boolean;
  card_badges: boolean;
  hero_title: string;
  hero_subtitle: string;
  banner: string | null;
};
export const DEFAULT_UI: UiConfig = {
  cta_label: "Add to cart",
  cta_style: "dark",
  cta_icon: false,
  show_ratings: true,
  card_badges: true,
  hero_title: "Search that learns what sells.",
  hero_subtitle: "Hybrid retrieval, a learned ranker and real A/B tests on a real catalog.",
  banner: null,
};
export type UiExposure = { experiment_key?: string; variant?: string; ui?: Partial<UiConfig> | null };
export type SimulatedTraffic = { status: "running" | "done" | "error"; users: number; days: number; seed?: number; assumed_effect?: Record<string, Record<string, number>>; counters?: Record<string, number>; error?: string };
export type Proposal = { name: string; hypothesis: string; summary: string; control: UiConfig; treatment: UiConfig; assumed_effect: Record<string, number>; changes: string[] };
export type SamplePlan = { baseline_conversion: number; mde_rel: number; alpha: number; power: number; users_per_arm: number; total_users: number; days_at_current_traffic: number | null };
export type DraftResults = { metric: string; control: number; treatment: number; rel_lift: number | null; ci: [number, number]; p_value: number; n_control: number; n_treatment: number; decision: string; hypothesis: string; srm_ok: boolean };
export type ExperimentDraft = { message: string; proposal: Proposal | null; experiment_key: string | null; plan: SamplePlan | null; results: DraftResults | null; trace: ToolTrace[]; provider: "claude" | "rule_based"; latency_ms: number };
