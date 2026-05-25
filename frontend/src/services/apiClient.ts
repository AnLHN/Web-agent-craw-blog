import {
  AuditLogData,
  AdminSystemStatusData,
  AdminUsersData,
  ApiResponse,
  ArticleImportData,
  ArticleLlmHealthData,
  AuthData,
  CurrentUserData,
  ChatSessionData,
  ChatSessionListData,
  LlmHealthData,
  LlmRuntimeConfigData,
  LlmTestData,
  SearchData,
  SearchStreamEvent,
  TavilyKeyMetricsData,
  TavilyKeysData,
} from "@/types/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
  "/api/v1";
const OPS_ROLE = process.env.NEXT_PUBLIC_OPS_ROLE || "admin";
const OPS_ADMIN_TOKEN = process.env.NEXT_PUBLIC_OPS_ADMIN_TOKEN || "";

function opsHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "X-Role": OPS_ROLE };
  if (OPS_ADMIN_TOKEN) {
    headers["X-Admin-Token"] = OPS_ADMIN_TOKEN;
  }
  return headers;
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function parseJson<T>(response: Response): Promise<T> {
  const raw = await response.text();
  const trimmed = raw.trim();

  if (!trimmed) {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ${response.statusText}`.trim());
    }
    throw new Error("Backend returned an empty response.");
  }

  try {
    return JSON.parse(trimmed) as T;
  } catch {
    const snippet = trimmed.slice(0, 160);
    throw new Error(`Backend returned non-JSON response (HTTP ${response.status}): ${snippet}`);
  }
}

export async function registerUser(payload: {
  email: string;
  password: string;
  username?: string;
}): Promise<ApiResponse<AuthData>> {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AuthData>>(response);
}

export async function loginUser(payload: {
  email: string;
  password: string;
}): Promise<ApiResponse<AuthData>> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AuthData>>(response);
}

export async function fetchCurrentUser(token: string): Promise<ApiResponse<CurrentUserData>> {
  const response = await fetch(`${API_BASE}/auth/me`, {
    method: "GET",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<CurrentUserData>>(response);
}

export async function logoutUser(token: string): Promise<ApiResponse<{ status: string }>> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<{ status: string }>>(response);
}

export async function fetchAdminUsers(token: string): Promise<ApiResponse<AdminUsersData>> {
  const response = await fetch(`${API_BASE}/admin/users`, {
    method: "GET",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AdminUsersData>>(response);
}

export async function fetchAdminAuditEvents(token: string, limit = 50): Promise<ApiResponse<AuditLogData>> {
  const response = await fetch(`${API_BASE}/admin/audit-events?limit=${limit}`, {
    method: "GET",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AuditLogData>>(response);
}

export async function fetchAdminSystemStatus(token: string): Promise<ApiResponse<AdminSystemStatusData>> {
  const response = await fetch(`${API_BASE}/admin/system-status`, {
    method: "GET",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AdminSystemStatusData>>(response);
}

export async function updateAdminUserStatus(
  token: string,
  userId: string,
  status: "active" | "disabled",
): Promise<ApiResponse<AdminUsersData>> {
  const response = await fetch(`${API_BASE}/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ status }),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AdminUsersData>>(response);
}

export async function addAdminUserRole(
  token: string,
  userId: string,
  role: "admin" | "user",
): Promise<ApiResponse<AdminUsersData>> {
  const response = await fetch(`${API_BASE}/admin/users/${userId}/roles/${role}`, {
    method: "PUT",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AdminUsersData>>(response);
}

export async function removeAdminUserRole(
  token: string,
  userId: string,
  role: "admin" | "user",
): Promise<ApiResponse<AdminUsersData>> {
  const response = await fetch(`${API_BASE}/admin/users/${userId}/roles/${role}`, {
    method: "DELETE",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AdminUsersData>>(response);
}

export async function searchWeb(
  query: string,
  topK = 5,
  sessionId: string | null = null,
): Promise<ApiResponse<SearchData>> {
  const body: Record<string, unknown> = { query, top_k: topK };
  if (sessionId) {
    body.session_id = sessionId;
  }
  const response = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  return parseJson<ApiResponse<SearchData>>(response);
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: JSON.parse(dataLines.join("\n")) as unknown };
}

function toSearchStreamEvent(event: string, data: unknown): SearchStreamEvent | null {
  if (!data || typeof data !== "object") {
    return null;
  }
  const payload = data as Record<string, unknown>;
  if (event === "status") {
    return { type: "status", ...payload, status: String(payload.status || "unknown") };
  }
  if (event === "token") {
    return { type: "token", text: String(payload.text || "") };
  }
  if (event === "done") {
    return { type: "done", result: payload.result as SearchData, meta: payload.meta as ApiResponse<SearchData>["meta"] };
  }
  if (event === "error") {
    return {
      type: "error",
      code: String(payload.code || "STREAM_ERROR"),
      message: String(payload.message || "Search stream failed"),
      details: (payload.details as Record<string, unknown> | null | undefined) ?? null,
    };
  }
  return null;
}

export async function searchWebStream(
  query: string,
  topK = 5,
  sessionId: string | null = null,
  onEvent: (event: SearchStreamEvent) => void,
): Promise<void> {
  const body: Record<string, unknown> = { query, top_k: topK };
  if (sessionId) {
    body.session_id = sessionId;
  }

  const response = await fetch(`${API_BASE}/search/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!response.ok || !response.body) {
    onEvent({
      type: "error",
      code: "STREAM_HTTP_ERROR",
      message: `Search stream failed with HTTP ${response.status}`,
      details: null,
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed) {
        continue;
      }
      const streamEvent = toSearchStreamEvent(parsed.event, parsed.data);
      if (streamEvent) {
        onEvent(streamEvent);
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer);
    if (parsed) {
      const streamEvent = toSearchStreamEvent(parsed.event, parsed.data);
      if (streamEvent) {
        onEvent(streamEvent);
      }
    }
  }
}

export async function createChatSession(
  title?: string,
): Promise<ApiResponse<ChatSessionData>> {
  const response = await fetch(`${API_BASE}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
    cache: "no-store",
  });
  return parseJson<ApiResponse<ChatSessionData>>(response);
}

export async function listChatSessions(
  q?: string,
): Promise<ApiResponse<ChatSessionListData>> {
  const query = q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  const response = await fetch(`${API_BASE}/chat/sessions${query}`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<ApiResponse<ChatSessionListData>>(response);
}

export async function getChatSession(
  sessionId: string,
): Promise<ApiResponse<ChatSessionData>> {
  const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<ApiResponse<ChatSessionData>>(response);
}

export async function deleteChatSession(
  sessionId: string,
): Promise<ApiResponse<ChatSessionListData>> {
  const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  return parseJson<ApiResponse<ChatSessionListData>>(response);
}

export async function clearChatSessions(): Promise<ApiResponse<ChatSessionListData>> {
  const response = await fetch(`${API_BASE}/chat/sessions`, {
    method: "DELETE",
    cache: "no-store",
  });
  return parseJson<ApiResponse<ChatSessionListData>>(response);
}

export async function fetchTavilyKeys(): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily`, {
    method: "GET",
    cache: "no-store",
  });

  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function addTavilyKey(
  token: string,
  apiKey: string,
  label: string,
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ api_key: apiKey, label }),
    cache: "no-store",
  });

  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function deleteTavilyKey(
  token: string,
  keyId: string,
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/${keyId}`, {
    method: "DELETE",
    headers: authHeaders(token),
    cache: "no-store",
  });

  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function updateTavilyKey(
  token: string,
  keyId: string,
  payload: { label?: string; status?: string },
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/${keyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function resetTavilyKeyCooldown(
  token: string,
  keyId: string,
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/${keyId}/cooldown/reset`, {
    method: "POST",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function fetchTavilyKeyMetrics(): Promise<ApiResponse<TavilyKeyMetricsData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/metrics`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<ApiResponse<TavilyKeyMetricsData>>(response);
}

export async function fetchLlmConfig(): Promise<ApiResponse<LlmRuntimeConfigData>> {
  const response = await fetch(`${API_BASE}/llm/config`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<ApiResponse<LlmRuntimeConfigData>>(response);
}

export async function patchLlmConfig(
  token: string,
  payload: {
    base_url?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number | null;
    summary_max_tokens?: number;
    summary_max_chars?: number;
    summary_system_prompt?: string;
  },
): Promise<ApiResponse<LlmRuntimeConfigData>> {
  const response = await fetch(`${API_BASE}/llm/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return parseJson<ApiResponse<LlmRuntimeConfigData>>(response);
}

export async function fetchLlmHealth(): Promise<ApiResponse<LlmHealthData>> {
  const response = await fetch(`${API_BASE}/llm/health`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<ApiResponse<LlmHealthData>>(response);
}

export async function runLlmTest(token: string, prompt: string): Promise<ApiResponse<LlmTestData>> {
  const response = await fetch(`${API_BASE}/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ prompt }),
    cache: "no-store",
  });
  return parseJson<ApiResponse<LlmTestData>>(response);
}

export async function fetchAuditLogs(limit = 50): Promise<ApiResponse<AuditLogData>> {
  const response = await fetch(`${API_BASE}/ops/audit/logs?limit=${limit}`, {
    method: "GET",
    headers: opsHeaders(),
    cache: "no-store",
  });
  return parseJson<ApiResponse<AuditLogData>>(response);
}

export async function importArticle(token: string, payload: {
  url: string;
  mode?: "draft" | "preview";
  target_language?: string;
  glossary_key?: string;
  wordpress_target_url?: string;
  async_mode?: boolean;
}): Promise<ApiResponse<ArticleImportData>> {
  const response = await fetch(`${API_BASE}/articles/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return parseJson<ApiResponse<ArticleImportData>>(response);
}

export async function fetchArticleImport(runId: string): Promise<ApiResponse<ArticleImportData>> {
  const response = await fetch(`${API_BASE}/articles/import/${runId}`, {
    method: "GET",
    cache: "no-store",
  });
  return parseJson<ApiResponse<ArticleImportData>>(response);
}

export async function dryRunWordPressImport(token: string, runId: string): Promise<ApiResponse<ArticleImportData>> {
  const response = await fetch(`${API_BASE}/articles/import/${runId}/wordpress/dry-run`, {
    method: "POST",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<ArticleImportData>>(response);
}

export async function translateArticleImport(token: string, runId: string): Promise<ApiResponse<ArticleImportData>> {
  const response = await fetch(`${API_BASE}/articles/import/${runId}/translate`, {
    method: "POST",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<ArticleImportData>>(response);
}

export async function pasteWordPressImport(token: string, runId: string): Promise<ApiResponse<ArticleImportData>> {
  const response = await fetch(`${API_BASE}/articles/import/${runId}/wordpress/paste`, {
    method: "POST",
    headers: authHeaders(token),
    cache: "no-store",
  });
  return parseJson<ApiResponse<ArticleImportData>>(response);
}

export async function checkArticleLlmHealth(): Promise<ApiResponse<ArticleLlmHealthData>> {
  const response = await fetch(`${API_BASE}/articles/import/llm/health`, {
    method: "POST",
    cache: "no-store",
  });
  return parseJson<ApiResponse<ArticleLlmHealthData>>(response);
}
