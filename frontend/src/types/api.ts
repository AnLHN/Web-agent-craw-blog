export type ProviderAttempt = {
  provider: string;
  status: string;
  reason: string;
  latency_ms: number;
  result_count: number;
  sub_query?: string | null;
};

export type SourceItem = {
  title: string;
  url: string;
  snippet: string;
  domain: string;
  score: number;
  published_date?: string | null;
};

export type SearchData = {
  query: string;
  provider_used: string;
  summary: string;
  confidence: number;
  sources: SourceItem[];
  attempts: ProviderAttempt[];
  query_analysis?: {
    original_query: string;
    normalized_query: string;
    intent: string;
    expanded_sub_queries: string[];
    planned_sub_queries: string[];
    complexity: string;
    retrieval_budget: number;
    evidence_kept_count: number;
    evidence_dropped_count: number;
    evidence_dropped_reason_summary: string;
    query_expansion_count: number;
    subquery_cache_hit_rate: number;
    retrieval_coverage: number;
    analysis_reasoning_short: string;
  } | null;
};

export type SearchStreamStatusEvent = {
  type: "status";
  status: string;
  [key: string]: unknown;
};

export type SearchStreamTokenEvent = {
  type: "token";
  text: string;
};

export type SearchStreamDoneEvent = {
  type: "done";
  result: SearchData;
  meta?: ApiResponse<SearchData>["meta"];
};

export type SearchStreamErrorEvent = {
  type: "error";
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
};

export type SearchStreamEvent =
  | SearchStreamStatusEvent
  | SearchStreamTokenEvent
  | SearchStreamDoneEvent
  | SearchStreamErrorEvent;

export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
};

export type ApiResponse<T> = {
  success: boolean;
  data: T | null;
  error: ApiError | null;
  meta: {
    timestamp: string;
    request_id?: string | null;
  };
};

export type TavilyKeyInfo = {
  id: string;
  label: string;
  masked_key: string;
  status: string;
  success_rate_5m: number;
  last_used_at?: string | null;
  cooldown_until?: string | null;
};

export type TavilyKeysData = {
  keys: TavilyKeyInfo[];
};

export type TavilyKeyMetricsData = {
  total_keys: number;
  active_keys: number;
  cooling_down_keys: number;
  unhealthy_keys: number;
  exhausted_keys: number;
  total_success_count: number;
  total_failure_count: number;
  average_success_rate: number;
  keys: TavilyKeyInfo[];
};

export type ChatMessage = {
  id: string;
  role: string;
  content: string;
  created_at: string;
  metadata?: Record<string, unknown> | null;
};

export type ChatSession = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_message_at: string;
  message_count: number;
  messages: ChatMessage[];
  metadata?: Record<string, unknown> | null;
};

export type ChatSessionData = {
  session: ChatSession;
};

export type ChatSessionListData = {
  sessions: ChatSession[];
  total: number;
};

export type LlmRuntimeConfig = {
  base_url: string;
  model: string;
  temperature: number;
  max_tokens?: number | null;
  summary_max_tokens?: number;
  summary_max_chars?: number;
  summary_system_prompt?: string;
  updated_at: string;
};

export type LlmRuntimeConfigData = {
  config: LlmRuntimeConfig;
};

export type LlmHealthData = {
  ok: boolean;
  message: string;
  latency_ms: number;
  base_url: string;
  checked_at: string;
};

export type LlmTestData = {
  status: string;
  finish_reason: string;
  latency_ms: number;
  response_preview: string;
};

export type AuditLogItem = {
  timestamp: string;
  actor_role: string;
  action: string;
  path: string;
  method: string;
  status: string;
  details?: Record<string, unknown> | null;
};

export type AuditLogData = {
  events: AuditLogItem[];
  total: number;
};
