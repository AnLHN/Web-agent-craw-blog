"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  addTavilyKey,
  createChatSession,
  deleteChatSession,
  deleteTavilyKey,
  fetchTavilyKeys,
  getChatSession,
  listChatSessions,
  searchWebStream,
} from "@/services/apiClient";
import { ChatSession, SearchData, SearchStreamStatusEvent, TavilyKeyInfo } from "@/types/api";
import { prettyDate } from "@/utils/date";

import { ArticleImportPanel } from "./ArticleImportPanel";
import { KeyManager } from "./KeyManager";
import { OpsDashboard } from "./OpsDashboard";
import { PromptManagerPanel } from "./PromptManagerPopup";
import { SearchResultPanel } from "./SearchResultPanel";

type WorkspaceMode = "web-search" | "article-import";
type TabKey = "tavily-keys" | "ops" | "prompts";

type NavItem = {
  key: TabKey;
  label: string;
  shortLabel: string;
};

function humanizeStatus(status: string): string {
  const map: Record<string, string> = {
    accepted: "Đã nhận truy vấn",
    context_rewrite_started: "Đang hiểu ngữ cảnh chat",
    context_rewrite_done: "Đã hiểu ngữ cảnh chat",
    cache_hit: "Lấy kết quả từ cache",
    query_analysis_started: "Đang phân tích truy vấn",
    query_analysis_done: "Đã phân tích truy vấn",
    query_planning_started: "Đang lập kế hoạch tìm kiếm",
    query_planning_done: "Đã lập kế hoạch tìm kiếm",
    retrieval_started: "Đang tìm nguồn web",
    retrieval_done: "Đã lấy nguồn web",
    evidence_merge_started: "Đang hợp nhất nguồn",
    evidence_merge_done: "Đã hợp nhất nguồn",
    fallback_single_query_started: "Đang thử lại với truy vấn gốc",
    fallback_single_query_done: "Đã thử lại với truy vấn gốc",
    quality_gate_extra_round_started: "Đang bổ sung vòng tìm kiếm",
    quality_gate_extra_round_done: "Đã bổ sung vòng tìm kiếm",
    quality_gate_passed: "Đã qua quality gate",
    llm_summary_started: "Đang tổng hợp tóm tắt bằng LLM",
    llm_summary_done: "Đã tổng hợp tóm tắt",
    no_sources_found: "Không tìm thấy nguồn phù hợp",
  };
  return map[status] || status.replaceAll("_", " ");
}

function isSearchData(value: unknown): value is SearchData {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<SearchData>;
  return (
    typeof candidate.query === "string" &&
    typeof candidate.provider_used === "string" &&
    typeof candidate.summary === "string" &&
    typeof candidate.confidence === "number" &&
    Array.isArray(candidate.sources) &&
    Array.isArray(candidate.attempts)
  );
}

function restoreLatestSearchResult(session: ChatSession): SearchData | null {
  const latestAssistantMessage = [...session.messages]
    .reverse()
    .find((message) => message.role === "assistant" && message.metadata?.search_result);

  const searchResult = latestAssistantMessage?.metadata?.search_result;
  return isSearchData(searchResult) ? searchResult : null;
}

export function SearchWorkspace() {
  const featureSessionHistory =
    (process.env.NEXT_PUBLIC_FEATURE_SESSION_HISTORY || "true").toLowerCase() !== "false";
  const featureOpsDashboard =
    (process.env.NEXT_PUBLIC_FEATURE_OPS_DASHBOARD || "true").toLowerCase() !== "false";
  const featureLlmRuntimeConfig =
    (process.env.NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG || "true").toLowerCase() !== "false";
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("web-search");
  const [activeTab, setActiveTab] = useState<TabKey>("tavily-keys");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);

  const [result, setResult] = useState<SearchData | null>(null);
  const [lastSubmittedQuery, setLastSubmittedQuery] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [streamStatuses, setStreamStatuses] = useState<SearchStreamStatusEvent[]>([]);
  const [streamedAnswer, setStreamedAnswer] = useState("");
  const [streamedAnswerTarget, setStreamedAnswerTarget] = useState("");

  const [keys, setKeys] = useState<TavilyKeyInfo[]>([]);
  const [isLoadingKeys, setIsLoadingKeys] = useState(false);
  const [keysError, setKeysError] = useState<string | null>(null);

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const currentSessionLabel = useMemo(() => {
    if (!currentSession) {
      return "No session";
    }
    return `${currentSession.title} (${currentSession.message_count} msgs)`;
  }, [currentSession]);

  const currentProcessingStatus = useMemo(() => {
    if (!isSearching) {
      return "";
    }
    const latest = streamStatuses[streamStatuses.length - 1];
    if (!latest?.status) {
      return "Đang xử lý...";
    }
    return humanizeStatus(latest.status);
  }, [isSearching, streamStatuses]);

  function resetChatDraftAndResult() {
    setQuery("");
    setResult(null);
    setLastSubmittedQuery("");
    setSearchError(null);
    setIsSearching(false);
    setStreamStatuses([]);
    setStreamedAnswer("");
    setStreamedAnswerTarget("");
  }

  useEffect(() => {
    if (streamedAnswer.length >= streamedAnswerTarget.length) {
      return;
    }
    const timer = window.setTimeout(() => {
      const next = streamedAnswerTarget.slice(0, streamedAnswer.length + 3);
      setStreamedAnswer(next);
    }, 12);
    return () => window.clearTimeout(timer);
  }, [streamedAnswer, streamedAnswerTarget]);

  async function loadKeys() {
    setIsLoadingKeys(true);
    try {
      const response = await fetchTavilyKeys();
      if (!response.success || !response.data) {
        setKeysError(response.error?.message || "Khong the lay danh sach key.");
        return;
      }
      setKeysError(null);
      setKeys(response.data.keys);
    } catch {
      setKeysError("Khong ket noi duoc backend.");
    } finally {
      setIsLoadingKeys(false);
    }
  }

  async function loadSessionHistory() {
    setIsLoadingSessions(true);
    try {
      const response = await listChatSessions();
      if (!response.success || !response.data) {
        setSessionError(response.error?.message || "Khong the tai lich su session.");
        return;
      }
      setSessions(response.data.sessions);
      setSessionError(null);

      if (!currentSessionId && response.data.sessions.length > 0) {
        const first = response.data.sessions[0];
        setCurrentSessionId(first.id);
        await loadSessionDetail(first.id);
      }

      if (!currentSessionId && response.data.sessions.length === 0) {
        await handleCreateSession();
      }
    } catch {
      setSessionError("Khong ket noi duoc backend session API.");
    } finally {
      setIsLoadingSessions(false);
    }
  }

  async function loadSessionDetail(sessionId: string) {
    try {
      const response = await getChatSession(sessionId);
      if (!response.success || !response.data) {
        setSessionError(response.error?.message || "Khong the tai session.");
        return;
      }
      const session = response.data.session;
      const restoredResult = restoreLatestSearchResult(session);

      setCurrentSession(session);
      setResult(restoredResult);
      setLastSubmittedQuery(restoredResult?.query || "");
      setSearchError(null);
      setStreamStatuses([]);
      setStreamedAnswer("");
      setSessionError(null);
    } catch {
      setSessionError("Khong ket noi duoc backend khi tai session.");
    }
  }

  async function handleCreateSession() {
    try {
      const title = `Session ${new Date().toLocaleString()}`;
      const response = await createChatSession(title);
      if (!response.success || !response.data) {
        setSessionError(response.error?.message || "Khong tao duoc session moi.");
        return;
      }
      const session = response.data.session;
      resetChatDraftAndResult();
      setCurrentSessionId(session.id);
      setCurrentSession(session);
      await loadSessionHistory();
    } catch {
      setSessionError("Khong ket noi duoc backend khi tao session.");
    }
  }

  async function ensureActiveSessionForSearch(): Promise<string | null> {
    if (!featureSessionHistory) {
      return null;
    }
    if (currentSessionId) {
      return currentSessionId;
    }

    const title = `Session ${new Date().toLocaleString()}`;
    const response = await createChatSession(title);
    if (!response.success || !response.data) {
      setSessionError(response.error?.message || "Khong tao duoc session moi.");
      return null;
    }

    const session = response.data.session;
    setCurrentSessionId(session.id);
    setCurrentSession(session);
    await loadSessionHistory();
    return session.id;
  }

  async function handleDeleteSession(sessionId: string) {
    try {
      const response = await deleteChatSession(sessionId);
      if (!response.success || !response.data) {
        setSessionError(response.error?.message || "Khong xoa duoc session.");
        return;
      }
      const updatedSessions = response.data.sessions;
      setSessions(updatedSessions);
      setSessionError(null);

      if (currentSessionId === sessionId) {
        if (updatedSessions.length > 0) {
          setCurrentSessionId(updatedSessions[0].id);
          await loadSessionDetail(updatedSessions[0].id);
        } else {
          setCurrentSessionId(null);
          setCurrentSession(null);
          resetChatDraftAndResult();
        }
      }
    } catch {
      setSessionError("Khong ket noi duoc backend khi xoa session.");
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      if (featureSessionHistory) {
        void Promise.all([loadKeys(), loadSessionHistory()]);
      } else {
        void loadKeys();
      }
    }, 0);

    return () => {
      window.clearTimeout(timerId);
    };
    // Initial boot load only; tab changes should not refetch all workspace data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }

    setSearchError(null);
    setIsSearching(true);
    setResult(null);
    setStreamStatuses([]);
    setStreamedAnswer("");
    setStreamedAnswerTarget("");

    try {
      const submittedQuery = query.trim();
      setQuery("");
      setLastSubmittedQuery(submittedQuery);
      const sessionIdForSearch = await ensureActiveSessionForSearch();
      await searchWebStream(
        submittedQuery,
        topK,
        sessionIdForSearch,
        (event) => {
          if (event.type === "status") {
            setStreamStatuses((prev) => [...prev.slice(-7), event]);
            return;
          }
          if (event.type === "token") {
            setStreamedAnswerTarget((prev) => `${prev}${event.text}`);
            return;
          }
          if (event.type === "done") {
            setResult(event.result);
            return;
          }
          if (event.type === "error") {
            setResult(null);
            setSearchError(event.message);
          }
        },
      );
      if (featureSessionHistory && sessionIdForSearch) {
        await loadSessionDetail(sessionIdForSearch);
        await loadSessionHistory();
      }
    } catch {
      setResult(null);
      setSearchError("Khong ket noi duoc backend API.");
    } finally {
      setIsSearching(false);
    }
  }

  async function handleAddKey(apiKey: string, label: string) {
    setKeysError(null);
    setIsLoadingKeys(true);
    try {
      const response = await addTavilyKey(apiKey, label);
      if (!response.success || !response.data) {
        setKeysError(response.error?.message || "Khong the them key.");
        return;
      }
      setKeys(response.data.keys);
    } catch {
      setKeysError("Khong ket noi duoc backend khi them key.");
    } finally {
      setIsLoadingKeys(false);
    }
  }

  async function handleDeleteKey(keyId: string) {
    setKeysError(null);
    setIsLoadingKeys(true);
    try {
      const response = await deleteTavilyKey(keyId);
      if (!response.success || !response.data) {
        setKeysError(response.error?.message || "Khong the xoa key.");
        return;
      }
      setKeys(response.data.keys);
    } catch {
      setKeysError("Khong ket noi duoc backend khi xoa key.");
    } finally {
      setIsLoadingKeys(false);
    }
  }

  const navItems: NavItem[] = [
    { key: "tavily-keys", label: "Tavily Keys", shortLabel: "Keys" },
    ...(featureOpsDashboard ? [{ key: "ops" as const, label: "Ops Dashboard", shortLabel: "Ops" }] : []),
    ...(featureLlmRuntimeConfig
      ? [{ key: "prompts" as const, label: "Prompt Manager", shortLabel: "Prompts" }]
      : []),
  ];

  function renderSessionSidebar() {
    if (!featureSessionHistory) {
      return null;
    }

    return (
      <aside className="flex h-screen min-h-0 flex-col border-r border-blue-950/30 bg-[#102a56] text-blue-50">
        <div className="space-y-3 border-b border-white/10 p-3">
          <div className="grid grid-cols-2 gap-1 rounded-2xl border border-white/10 bg-blue-950/25 p-1">
            <button
              type="button"
              onClick={() => setWorkspaceMode("web-search")}
              className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
                workspaceMode === "web-search"
                  ? "bg-white text-blue-950 shadow-sm"
                  : "text-blue-100 hover:bg-white/10"
              }`}
            >
              Web Search
            </button>
            <button
              type="button"
              onClick={() => setWorkspaceMode("article-import")}
              className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
                workspaceMode === "article-import"
                  ? "bg-orange-300 text-blue-950 shadow-sm"
                  : "text-blue-100 hover:bg-white/10"
              }`}
            >
              Viết blog
            </button>
          </div>

          {workspaceMode === "web-search" ? (
            <button
              type="button"
              onClick={() => {
                void handleCreateSession();
              }}
              className="w-full rounded-xl border border-white/15 bg-white/8 px-3 py-2 text-left text-sm font-medium text-white shadow-sm hover:bg-white/14"
            >
              Chat mới
            </button>
          ) : null}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
          {workspaceMode === "web-search" ? (
            <>
              <p className="px-2 text-[11px] font-semibold uppercase text-blue-200/70">Lịch sử chat</p>
              {sessionError ? <p className="mt-2 px-2 text-xs text-orange-200">{sessionError}</p> : null}
              {isLoadingSessions ? <p className="mt-2 px-2 text-xs text-blue-100/60">Loading...</p> : null}
              <div className="mt-2 space-y-1">
                {sessions.map((session) => {
                  const isActive = currentSessionId === session.id;
                  return (
                    <div
                      key={session.id}
                      className={`group rounded-xl transition ${
                        isActive ? "bg-white text-blue-950 shadow-sm" : "hover:bg-white/10"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          resetChatDraftAndResult();
                          setCurrentSessionId(session.id);
                          void loadSessionDetail(session.id);
                        }}
                        className="w-full px-2 py-2 text-left"
                      >
                        <p className="line-clamp-1 text-sm font-medium">{session.title}</p>
                        <p className={`mt-0.5 text-[11px] ${isActive ? "text-blue-700" : "text-blue-100/55"}`}>
                          {prettyDate(session.last_message_at)} | {session.message_count} msgs
                        </p>
                      </button>
                      <div className="hidden gap-1 px-2 pb-2 group-hover:flex">
                        <button
                          type="button"
                          onClick={() => void handleDeleteSession(session.id)}
                          className={`rounded-lg border px-2 py-1 text-[11px] ${
                            isActive
                              ? "border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100"
                              : "border-orange-300/30 text-orange-100 hover:bg-orange-900/30"
                          }`}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
                {!isLoadingSessions && sessions.length === 0 ? (
                  <p className="px-2 py-2 text-xs text-blue-100/55">Chưa có lịch sử chat.</p>
                ) : null}
              </div>
            </>
          ) : (
            <div className="rounded-2xl border border-white/10 bg-white/8 px-3 py-3">
              <p className="text-sm font-semibold text-white">Article Import</p>
              <p className="mt-1 text-xs leading-5 text-blue-100/65">
                Nhập URL nguồn, tách block, tải ảnh, tạo draft và đẩy sang WordPress.
              </p>
            </div>
          )}
        </div>

        <div className="border-t border-white/10 p-3">
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="w-full rounded-xl bg-orange-300 px-3 py-2 text-left text-sm font-semibold text-blue-950 shadow-sm hover:bg-orange-200"
          >
            Cài đặt
          </button>
        </div>
      </aside>
    );
  }

  function renderSettingsContent() {
    if (activeTab === "ops" && featureOpsDashboard) {
      return <OpsDashboard onKeysChanged={loadKeys} />;
    }

    if (activeTab === "prompts" && featureLlmRuntimeConfig) {
      return <PromptManagerPanel />;
    }

    return (
      <KeyManager
        keys={keys}
        isLoading={isLoadingKeys}
        errorMessage={keysError}
        onAdd={handleAddKey}
        onDelete={handleDeleteKey}
      />
    );
  }

  function renderSettingsModal() {
    if (!settingsOpen) {
      return null;
    }

    return (
      <div className="fixed inset-0 z-50 bg-blue-950/45 p-3 backdrop-blur-sm md:p-6">
        <div className="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-blue-100 bg-[#f8fbff] shadow-2xl">
          <div className="flex items-center justify-between border-b border-blue-100 bg-white px-5 py-4">
            <div>
              <p className="text-xs font-semibold uppercase text-orange-600">Cài đặt</p>
              <h2 className="text-lg font-semibold text-stone-900">Quản lý hệ thống</h2>
            </div>
            <button
              type="button"
              onClick={() => setSettingsOpen(false)}
              className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 hover:bg-blue-50"
            >
              Đóng
            </button>
          </div>

          <div className="grid min-h-0 flex-1 md:grid-cols-[220px_1fr]">
            <nav className="flex gap-2 overflow-x-auto border-b border-blue-100 bg-white p-3 md:block md:space-y-1 md:overflow-visible md:border-b-0 md:border-r">
              {navItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveTab(item.key)}
                  className={`shrink-0 rounded-xl px-3 py-2 text-left text-sm font-medium transition md:w-full ${
                    activeTab === item.key
                      ? "bg-blue-700 text-white shadow-sm"
                      : "border border-blue-100 bg-white text-stone-700 hover:bg-orange-50 md:border-0"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>

            <div className="min-h-0 overflow-y-auto p-4 md:p-5">
              {renderSettingsContent()}
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderChatWorkspace() {
    return (
      <div className="flex h-screen min-h-0 flex-col bg-[#f5f9ff]">
        <header className="flex items-center justify-between border-b border-blue-100 bg-white/90 px-4 py-3 backdrop-blur">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-stone-900">Web Search Chat</h1>
            <p className="truncate text-xs text-blue-700/70">{currentSessionLabel}</p>
          </div>
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 shadow-sm hover:bg-orange-50"
          >
            Cài đặt
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-5 md:px-8">
          <div className="mx-auto max-w-3xl space-y-4">
            <SearchResultPanel
              isLoading={isSearching}
              errorMessage={searchError}
              result={result}
              latestUserQuery={lastSubmittedQuery}
              streamedAnswer={streamedAnswer}
              processingStatus={currentProcessingStatus}
              sessionMessages={currentSession?.messages || []}
            />
          </div>
        </div>

        <div className="border-t border-blue-100 bg-white/90 px-3 py-3 backdrop-blur md:px-8">
          <form onSubmit={handleSearch} className="mx-auto grid max-w-3xl gap-2 rounded-3xl border border-blue-200 bg-white p-2 shadow-lg shadow-blue-900/5 md:grid-cols-[1fr_120px_auto]">
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Nhập câu hỏi cần tìm trên web..."
              className="rounded-2xl border-0 px-3 py-2 text-sm focus:outline-none"
            />
            <label
              className="grid rounded-2xl border border-blue-100 bg-blue-50/60 px-3 py-1.5 focus-within:border-orange-400"
              title="Số kết quả web tối đa sẽ lấy làm nguồn cho câu trả lời."
            >
              <span className="text-[10px] font-semibold uppercase leading-none text-blue-600">Nguồn</span>
              <input
                type="number"
                min={1}
                max={10}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value) || 5)}
                aria-label="Số nguồn web"
                className="w-full bg-transparent text-sm text-blue-950 focus:outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={isSearching}
              className="rounded-2xl bg-orange-500 px-5 py-2 text-sm font-semibold text-white transition hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSearching ? "Đang tìm..." : "Tìm web"}
            </button>
          </form>
          {featureSessionHistory && currentSessionId ? (
            <p className="mx-auto mt-2 max-w-3xl break-all text-xs text-stone-400">Mã phiên: {currentSessionId}</p>
          ) : null}
        </div>
      </div>
    );
  }

  function renderArticleImportWorkspace() {
    return (
      <div className="flex h-screen min-h-0 flex-col bg-[#f5f9ff]">
        <header className="flex items-center justify-between border-b border-blue-100 bg-white/90 px-4 py-3 backdrop-blur">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-stone-900">Article Import</h1>
            <p className="truncate text-xs text-blue-700/70">Cào dữ liệu và dựng bài WordPress</p>
          </div>
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 shadow-sm hover:bg-orange-50"
          >
            Cài đặt
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-5 md:px-8">
          <div className="mx-auto w-full max-w-6xl min-w-0">
            <ArticleImportPanel />
          </div>
        </div>
      </div>
    );
  }

  return (
    <main className={`grid min-h-screen ${featureSessionHistory ? "md:grid-cols-[280px_1fr]" : ""}`}>
      {renderSessionSidebar()}
      <section className="min-w-0 overflow-x-hidden">
        <div className={workspaceMode === "web-search" ? "block" : "hidden"}>{renderChatWorkspace()}</div>
        <div className={workspaceMode === "article-import" ? "block" : "hidden"}>
          {renderArticleImportWorkspace()}
        </div>
      </section>
      {renderSettingsModal()}
    </main>
  );
}

