export type ProviderAttempt = {
  provider: string;
  status: string;
  reason: string;
  latency_ms: number;
  result_count: number;
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
};

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
