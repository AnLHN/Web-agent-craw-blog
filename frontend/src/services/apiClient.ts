import {
  AuditLogData,
  ApiResponse,
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

async function parseJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T;
  return payload;
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
  apiKey: string,
  label: string,
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...opsHeaders() },
    body: JSON.stringify({ api_key: apiKey, label }),
    cache: "no-store",
  });

  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function deleteTavilyKey(
  keyId: string,
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/${keyId}`, {
    method: "DELETE",
    headers: opsHeaders(),
    cache: "no-store",
  });

  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function updateTavilyKey(
  keyId: string,
  payload: { label?: string; status?: string },
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/${keyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...opsHeaders() },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return parseJson<ApiResponse<TavilyKeysData>>(response);
}

export async function resetTavilyKeyCooldown(
  keyId: string,
): Promise<ApiResponse<TavilyKeysData>> {
  const response = await fetch(`${API_BASE}/keys/tavily/${keyId}/cooldown/reset`, {
    method: "POST",
    headers: opsHeaders(),
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
  payload: {
    base_url?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number | null;
    summary_max_chars?: number;
    summary_system_prompt?: string;
  },
): Promise<ApiResponse<LlmRuntimeConfigData>> {
  const response = await fetch(`${API_BASE}/llm/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...opsHeaders() },
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

export async function runLlmTest(prompt: string): Promise<ApiResponse<LlmTestData>> {
  const response = await fetch(`${API_BASE}/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...opsHeaders() },
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
