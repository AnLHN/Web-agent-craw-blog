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

export type AuthUser = {
  id: string;
  email: string;
  username?: string | null;
  full_name?: string | null;
  status: string;
  roles: string[];
  permissions: string[];
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
};

export type AuthData = {
  user: AuthUser;
  access_token: string;
  token_type: string;
};

export type CurrentUserData = {
  user: AuthUser;
};

export type AdminUsersData = {
  users: AuthUser[];
  total: number;
};

export type ArticleBlockType =
  | "heading"
  | "paragraph"
  | "image"
  | "code"
  | "table"
  | "quote"
  | "embed"
  | "unknown";

export type ArticleAsset = {
  id: string;
  source_url: string;
  local_path?: string | null;
  mime_type?: string | null;
  width?: number | null;
  height?: number | null;
  alt_text?: string | null;
  caption?: string | null;
  checksum?: string | null;
  download_status: "pending" | "downloaded" | "skipped" | "failed";
  metadata: Record<string, unknown>;
};

export type ArticleBlock = {
  id: string;
  order_index: number;
  block_type: ArticleBlockType;
  source_text?: string | null;
  translated_text?: string | null;
  language_hint?: string | null;
  asset_id?: string | null;
  metadata: Record<string, unknown>;
};

export type ArticleDraftPreview = {
  title?: string | null;
  slug?: string | null;
  excerpt?: string | null;
  content_format: string;
  content?: string | null;
  tags: string[];
  categories: string[];
  source_attribution?: {
    url: string;
    title?: string | null;
    domain: string;
  } | null;
};

export type ArticleImportRun = {
  id: string;
  status: string;
  mode: string;
  target_language: string;
  source: {
    url: string;
    domain: string;
    title?: string | null;
    author?: string | null;
    published_at?: string | null;
  };
  storage: {
    run_dir: string;
    raw_snapshot_path: string;
    extracted_json_path: string;
    draft_json_path: string;
    assets_dir: string;
  };
  blocks: ArticleBlock[];
  assets: ArticleAsset[];
  draft?: ArticleDraftPreview | null;
  prompt_usage: Array<{
    prompt_key: string;
    version?: string | null;
    model?: string | null;
    provider?: string | null;
  }>;
  wordpress_post_id?: string | null;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
  metadata: Record<string, unknown>;
};

export type ArticleImportData = {
  run: ArticleImportRun;
};

export type ArticleLlmHealthData = {
  ok: boolean;
  configured: boolean;
  status: string;
  message: string;
  latency_ms: number;
  base_url: string;
  model: string;
  has_api_key: boolean;
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

export type AdminSystemStatusData = {
  status: string;
  environment: string;
  auth_store_backend: string;
  auth_service_type: string;
  session_store_backend: string;
  session_store_type: string;
  database_configured: boolean;
  rbac_enabled: boolean;
  llm_enabled: boolean;
  llm_configured: boolean;
  tavily_key_count: number;
  article_import_storage_path: string;
  article_import_run_count: number;
  article_import_status_counts: Record<string, number>;
  readiness_checks: Record<string, string>;
};
