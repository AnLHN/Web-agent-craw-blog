import { ApiResponse, SearchData, TavilyKeysData } from "@/types/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
  "/api/v1";

async function parseJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T;
  return payload;
}

export async function searchWeb(query: string, topK = 5): Promise<ApiResponse<SearchData>> {
  const response = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
    cache: "no-store",
  });

  return parseJson<ApiResponse<SearchData>>(response);
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
    headers: { "Content-Type": "application/json" },
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
    cache: "no-store",
  });

  return parseJson<ApiResponse<TavilyKeysData>>(response);
}
