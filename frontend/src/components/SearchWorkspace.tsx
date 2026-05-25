"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  addAdminUserRole,
  addTavilyKey,
  createChatSession,
  deleteChatSession,
  fetchAdminAuditEvents,
  fetchAdminUsers,
  fetchCurrentUser,
  deleteTavilyKey,
  fetchTavilyKeys,
  getChatSession,
  listChatSessions,
  loginUser,
  logoutUser,
  registerUser,
  removeAdminUserRole,
  searchWebStream,
  updateAdminUserStatus,
} from "@/services/apiClient";
import { AuditLogItem, AuthUser, ChatSession, SearchData, SearchStreamStatusEvent, TavilyKeyInfo } from "@/types/api";
import { prettyDate } from "@/utils/date";

import { ArticleImportPanel } from "./ArticleImportPanel";
import { KeyManager } from "./KeyManager";
import { OpsDashboard } from "./OpsDashboard";
import { PromptManagerPanel } from "./PromptManagerPopup";
import { SearchResultPanel } from "./SearchResultPanel";

type WorkspaceMode = "web-search" | "article-import";
type AdminTabKey = "users" | "audit" | "tavily-keys" | "ops" | "prompts" | "auth";
type AuthMode = "login" | "register";

const AUTH_TOKEN_KEY = "web_agent_auth_token";

type AdminNavItem = {
  key: AdminTabKey;
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
  const [adminOpen, setAdminOpen] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authToken, setAuthToken] = useState<string | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.localStorage.getItem(AUTH_TOKEN_KEY);
  });
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authUsername, setAuthUsername] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("web-search");
  const [activeAdminTab, setActiveAdminTab] = useState<AdminTabKey>("users");
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

  const [adminUsers, setAdminUsers] = useState<AuthUser[]>([]);
  const [isLoadingAdminUsers, setIsLoadingAdminUsers] = useState(false);
  const [adminUsersError, setAdminUsersError] = useState<string | null>(null);
  const [adminAuditEvents, setAdminAuditEvents] = useState<AuditLogItem[]>([]);
  const [isLoadingAdminAudit, setIsLoadingAdminAudit] = useState(false);
  const [adminAuditError, setAdminAuditError] = useState<string | null>(null);

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

  const isAdmin = Boolean(currentUser?.roles.includes("admin"));
  const canManageKeys = Boolean(isAdmin || currentUser?.permissions.includes("keys:tavily_manage"));
  const canViewOpsDashboard = Boolean(isAdmin || currentUser?.permissions.includes("ops:audit_read"));
  const canManagePrompts = Boolean(isAdmin || currentUser?.permissions.includes("llm:config_manage"));
  const canViewAuthState = Boolean(isAdmin || currentUser?.permissions.includes("admin:users_read"));
  const canViewAdminPanel = canManageKeys || canViewOpsDashboard || canManagePrompts || canViewAuthState;

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

  async function loadAdminUsers() {
    if (!authToken) {
      return;
    }
    setIsLoadingAdminUsers(true);
    try {
      const response = await fetchAdminUsers(authToken);
      if (!response.success || !response.data) {
        setAdminUsersError(response.error?.message || "Khong the tai danh sach user.");
        return;
      }
      setAdminUsers(response.data.users);
      setAdminUsersError(null);
    } catch {
      setAdminUsersError("Khong ket noi duoc backend admin API.");
    } finally {
      setIsLoadingAdminUsers(false);
    }
  }

  async function loadAdminAuditEvents() {
    if (!authToken) {
      return;
    }
    setIsLoadingAdminAudit(true);
    try {
      const response = await fetchAdminAuditEvents(authToken, 80);
      if (!response.success || !response.data) {
        setAdminAuditError(response.error?.message || "Khong the tai audit events.");
        return;
      }
      setAdminAuditEvents(response.data.events);
      setAdminAuditError(null);
    } catch {
      setAdminAuditError("Khong ket noi duoc backend audit API.");
    } finally {
      setIsLoadingAdminAudit(false);
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
    if (!authToken) {
      return;
    }
    void (async () => {
      try {
        const response = await fetchCurrentUser(authToken);
        if (!response.success || !response.data) {
          window.localStorage.removeItem(AUTH_TOKEN_KEY);
          setAuthToken(null);
          setCurrentUser(null);
          return;
        }
        setCurrentUser(response.data.user);
      } catch {
        window.localStorage.removeItem(AUTH_TOKEN_KEY);
        setAuthToken(null);
        setCurrentUser(null);
      }
    })();
  }, [authToken]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    const timerId = window.setTimeout(() => {
      const bootTasks: Promise<void>[] = [];
      if (canManageKeys) {
        bootTasks.push(loadKeys());
      }
      if (canViewAuthState) {
        bootTasks.push(loadAdminUsers());
      }
      if (canViewOpsDashboard) {
        bootTasks.push(loadAdminAuditEvents());
      }
      if (featureSessionHistory) {
        bootTasks.push(loadSessionHistory());
      }
      void Promise.all(bootTasks);
    }, 0);

    return () => {
      window.clearTimeout(timerId);
    };
    // Initial boot load after auth only; tab changes should not refetch all workspace data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.id]);

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthLoading(true);
    setAuthError(null);
    try {
      const response = authMode === "login"
        ? await loginUser({ email: authEmail, password: authPassword })
        : await registerUser({
            email: authEmail,
            password: authPassword,
            username: authUsername.trim() || undefined,
          });
      if (!response.success || !response.data) {
        setAuthError(response.error?.message || "Authentication failed.");
        return;
      }
      window.localStorage.setItem(AUTH_TOKEN_KEY, response.data.access_token);
      setAuthToken(response.data.access_token);
      setCurrentUser(response.data.user);
      setAuthPassword("");
      setAuthError(null);
    } catch {
      setAuthError("Khong ket noi duoc backend auth API.");
    } finally {
      setIsAuthLoading(false);
    }
  }

  async function handleLogout() {
    const token = authToken;
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    setAuthToken(null);
    setCurrentUser(null);
    setSessions([]);
    setCurrentSession(null);
    setCurrentSessionId(null);
    resetChatDraftAndResult();
    if (token) {
      try {
        await logoutUser(token);
      } catch {
        // Local logout already completed.
      }
    }
  }

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
      if (!authToken) {
        setKeysError("Vui long dang nhap lai.");
        return;
      }
      const response = await addTavilyKey(authToken, apiKey, label);
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
      if (!authToken) {
        setKeysError("Vui long dang nhap lai.");
        return;
      }
      const response = await deleteTavilyKey(authToken, keyId);
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

  async function handleUpdateUserStatus(userId: string, status: "active" | "disabled") {
    if (!authToken) {
      return;
    }
    const response = await updateAdminUserStatus(authToken, userId, status);
    if (!response.success || !response.data) {
      setAdminUsersError(response.error?.message || "Khong cap nhat duoc user.");
      return;
    }
    setAdminUsers(response.data.users);
    setAdminUsersError(null);
    await loadAdminAuditEvents();
  }

  async function handleToggleAdminRole(user: AuthUser) {
    if (!authToken) {
      return;
    }
    const hasAdmin = user.roles.includes("admin");
    const response = hasAdmin
      ? await removeAdminUserRole(authToken, user.id, "admin")
      : await addAdminUserRole(authToken, user.id, "admin");
    if (!response.success || !response.data) {
      setAdminUsersError(response.error?.message || "Khong cap nhat duoc role.");
      return;
    }
    setAdminUsers(response.data.users);
    setAdminUsersError(null);
    await loadAdminAuditEvents();
  }

  const adminNavItems: AdminNavItem[] = [
    ...(canViewAuthState ? [{ key: "users" as const, label: "Users", shortLabel: "Users" }] : []),
    ...(canViewOpsDashboard ? [{ key: "audit" as const, label: "Audit", shortLabel: "Audit" }] : []),
    ...(canManageKeys ? [{ key: "tavily-keys" as const, label: "Tavily Keys", shortLabel: "Keys" }] : []),
    ...(featureOpsDashboard && canViewOpsDashboard
      ? [{ key: "ops" as const, label: "Ops Dashboard", shortLabel: "Ops" }]
      : []),
    ...(featureLlmRuntimeConfig && canManagePrompts
      ? [{ key: "prompts" as const, label: "Prompt Manager", shortLabel: "Prompts" }]
      : []),
    ...(canViewAuthState ? [{ key: "auth" as const, label: "Auth State", shortLabel: "Auth" }] : []),
  ];
  const visibleAdminTab = adminNavItems.some((item) => item.key === activeAdminTab)
    ? activeAdminTab
    : adminNavItems[0]?.key;

  function renderAuthGate() {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f5f9ff] px-4 py-8">
        <div className="w-full max-w-md rounded-3xl border border-blue-100 bg-white p-6 shadow-xl shadow-blue-950/10">
          <p className="text-xs font-semibold uppercase text-orange-600">Web Agent Craw Blog</p>
          <h1 className="mt-2 text-2xl font-bold text-stone-950">
            {authMode === "login" ? "Đăng nhập" : "Đăng ký tài khoản"}
          </h1>
          <p className="mt-2 text-sm text-stone-600">
            {authMode === "login"
              ? "Đăng nhập để dùng search, article import và trang quản trị."
              : "Tài khoản đầu tiên sẽ tự nhận quyền admin."}
          </p>

          <form onSubmit={handleAuthSubmit} className="mt-6 space-y-3">
            <label className="grid gap-1 text-sm font-medium text-stone-700">
              Email
              <input
                type="email"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
                className="rounded-xl border border-blue-100 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none"
                required
              />
            </label>
            {authMode === "register" ? (
              <>
                <label className="grid gap-1 text-sm font-medium text-stone-700">
                  Username
                  <input
                    type="text"
                    value={authUsername}
                    onChange={(event) => setAuthUsername(event.target.value)}
                    className="rounded-xl border border-blue-100 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none"
                  />
                </label>
              </>
            ) : null}
            <label className="grid gap-1 text-sm font-medium text-stone-700">
              Password
              <input
                type="password"
                value={authPassword}
                onChange={(event) => setAuthPassword(event.target.value)}
                className="rounded-xl border border-blue-100 px-3 py-2 text-sm focus:border-orange-400 focus:outline-none"
                minLength={authMode === "register" ? 8 : 1}
                required
              />
            </label>
            {authError ? <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{authError}</p> : null}
            <button
              type="submit"
              disabled={isAuthLoading}
              className="w-full rounded-xl bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:opacity-60"
            >
              {isAuthLoading ? "Đang xử lý..." : authMode === "login" ? "Đăng nhập" : "Đăng ký"}
            </button>
          </form>

          <button
            type="button"
            onClick={() => {
              setAuthMode(authMode === "login" ? "register" : "login");
              setAuthError(null);
            }}
            className="mt-4 text-sm font-medium text-blue-700 hover:text-blue-900"
          >
            {authMode === "login" ? "Chưa có tài khoản? Đăng ký" : "Đã có tài khoản? Đăng nhập"}
          </button>
        </div>
      </main>
    );
  }

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

        <div className="space-y-2 border-t border-white/10 p-3">
          {currentUser ? (
            <div className="rounded-xl border border-white/10 bg-white/8 px-3 py-2">
              <p className="truncate text-xs font-semibold text-white">{currentUser.email}</p>
              <p className="mt-0.5 text-[11px] text-blue-100/60">Role: {currentUser.roles.join(", ") || "user"}</p>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="w-full rounded-xl bg-orange-300 px-3 py-2 text-left text-sm font-semibold text-blue-950 shadow-sm hover:bg-orange-200"
          >
            Cài đặt
          </button>
          {canViewAdminPanel ? (
            <button
              type="button"
              onClick={() => setAdminOpen(true)}
              className="w-full rounded-xl border border-orange-200/50 bg-white/8 px-3 py-2 text-left text-sm font-semibold text-white hover:bg-white/10"
            >
              Quản trị
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void handleLogout()}
            className="w-full rounded-xl border border-white/15 px-3 py-2 text-left text-sm font-semibold text-white hover:bg-white/10"
          >
            Đăng xuất
          </button>
        </div>
      </aside>
    );
  }

  function renderAdminUsersPanel() {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-orange-600">Admin</p>
            <h3 className="text-xl font-semibold text-stone-950">Users</h3>
            <p className="mt-1 text-sm text-stone-600">Danh sách tài khoản trong hệ thống.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadAdminUsers()}
            className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 hover:bg-blue-50"
          >
            Refresh
          </button>
        </div>

        {adminUsersError ? <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{adminUsersError}</p> : null}

        <div className="overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-sm">
          <div className="grid grid-cols-[1.4fr_1fr_0.8fr_1fr_1.2fr] gap-3 border-b border-blue-100 bg-blue-50/60 px-4 py-3 text-xs font-semibold uppercase text-blue-700">
            <span>Email</span>
            <span>Roles</span>
            <span>Status</span>
            <span>Last login</span>
            <span>Actions</span>
          </div>
          {isLoadingAdminUsers ? <p className="px-4 py-4 text-sm text-stone-500">Loading...</p> : null}
          {!isLoadingAdminUsers && adminUsers.length === 0 ? (
            <p className="px-4 py-4 text-sm text-stone-500">Chưa có user.</p>
          ) : null}
          {adminUsers.map((user) => (
            <div
              key={user.id}
              className="grid grid-cols-[1.4fr_1fr_0.8fr_1fr_1.2fr] gap-3 border-b border-blue-50 px-4 py-3 text-sm last:border-b-0"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-stone-900">{user.email}</p>
                <p className="truncate text-xs text-stone-500">{user.username || user.full_name || user.id}</p>
              </div>
              <p className="text-stone-700">{user.roles.join(", ") || "user"}</p>
              <p className="text-stone-700">{user.status}</p>
              <p className="text-stone-700">{user.last_login_at ? prettyDate(user.last_login_at) : "-"}</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleUpdateUserStatus(user.id, user.status === "active" ? "disabled" : "active")}
                  className="rounded-lg border border-blue-200 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
                >
                  {user.status === "active" ? "Disable" : "Enable"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleToggleAdminRole(user)}
                  className="rounded-lg border border-orange-200 px-2 py-1 text-xs font-medium text-orange-700 hover:bg-orange-50"
                >
                  {user.roles.includes("admin") ? "Remove admin" : "Make admin"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderAuditPanel() {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-orange-600">Admin</p>
            <h3 className="text-xl font-semibold text-stone-950">Audit</h3>
            <p className="mt-1 text-sm text-stone-600">Các thao tác quản trị và vận hành gần đây.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadAdminAuditEvents()}
            className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 hover:bg-blue-50"
          >
            Refresh
          </button>
        </div>

        {adminAuditError ? <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{adminAuditError}</p> : null}

        <div className="overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-sm">
          <div className="grid grid-cols-[1fr_1fr_1fr_1.5fr] gap-3 border-b border-blue-100 bg-blue-50/60 px-4 py-3 text-xs font-semibold uppercase text-blue-700">
            <span>Time</span>
            <span>Actor</span>
            <span>Action</span>
            <span>Target</span>
          </div>
          {isLoadingAdminAudit ? <p className="px-4 py-4 text-sm text-stone-500">Loading...</p> : null}
          {!isLoadingAdminAudit && adminAuditEvents.length === 0 ? (
            <p className="px-4 py-4 text-sm text-stone-500">Chưa có audit event.</p>
          ) : null}
          {adminAuditEvents.map((event, index) => (
            <div
              key={`${event.timestamp}-${event.action}-${index}`}
              className="grid grid-cols-[1fr_1fr_1fr_1.5fr] gap-3 border-b border-blue-50 px-4 py-3 text-sm last:border-b-0"
            >
              <p className="text-stone-700">{prettyDate(event.timestamp)}</p>
              <p className="text-stone-700">{event.actor_role}</p>
              <p className="font-medium text-stone-900">{event.action}</p>
              <p className="truncate text-stone-700">
                {event.method} {event.path} · {event.status}
              </p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderAdminPanel() {
    if (!currentUser) {
      return null;
    }

    return (
      <div className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase text-orange-600">Admin</p>
          <h3 className="text-xl font-semibold text-stone-950">Auth state</h3>
          <p className="mt-1 text-sm text-stone-600">Thông tin tài khoản và quyền hiện tại.</p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold uppercase text-blue-600">User</p>
            <dl className="mt-3 space-y-2 text-sm">
              <div>
                <dt className="text-stone-500">Email</dt>
                <dd className="font-medium text-stone-900">{currentUser.email}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Username</dt>
                <dd className="font-medium text-stone-900">{currentUser.username || "-"}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Status</dt>
                <dd className="font-medium text-stone-900">{currentUser.status}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Last login</dt>
                <dd className="font-medium text-stone-900">
                  {currentUser.last_login_at ? prettyDate(currentUser.last_login_at) : "-"}
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold uppercase text-blue-600">Access</p>
            <div className="mt-3 space-y-3">
              <div>
                <p className="text-sm font-medium text-stone-700">Roles</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {currentUser.roles.map((role) => (
                    <span key={role} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
                      {role}
                    </span>
                  ))}
                  {currentUser.roles.length === 0 ? <span className="text-sm text-stone-500">No roles</span> : null}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-stone-700">Permissions</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {currentUser.permissions.map((permission) => (
                    <span
                      key={permission}
                      className="rounded-full border border-orange-100 bg-orange-50 px-3 py-1 text-xs font-semibold text-orange-700"
                    >
                      {permission}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderAdminContent() {
    if (visibleAdminTab === "users" && canViewAuthState) {
      return renderAdminUsersPanel();
    }

    if (visibleAdminTab === "audit" && canViewOpsDashboard) {
      return renderAuditPanel();
    }

    if (visibleAdminTab === "ops" && featureOpsDashboard && canViewOpsDashboard) {
      return <OpsDashboard authToken={authToken || ""} onKeysChanged={loadKeys} />;
    }

    if (visibleAdminTab === "prompts" && featureLlmRuntimeConfig && canManagePrompts) {
      return <PromptManagerPanel authToken={authToken || ""} />;
    }

    if (visibleAdminTab === "auth" && canViewAuthState) {
      return renderAdminPanel();
    }

    if (canManageKeys) {
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

    return <p className="text-sm text-stone-600">Bạn không có quyền quản trị.</p>;
  }

  function renderSettingsModal() {
    if (!settingsOpen) {
      return null;
    }

    return (
      <div className="fixed inset-0 z-50 bg-blue-950/45 p-3 backdrop-blur-sm md:p-6">
        <div className="mx-auto flex max-h-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-blue-100 bg-[#f8fbff] shadow-2xl">
          <div className="flex items-center justify-between border-b border-blue-100 bg-white px-5 py-4">
            <div>
              <p className="text-xs font-semibold uppercase text-orange-600">Cài đặt</p>
              <h2 className="text-lg font-semibold text-stone-900">Tài khoản và cấu hình nhanh</h2>
            </div>
            <button
              type="button"
              onClick={() => setSettingsOpen(false)}
              className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 hover:bg-blue-50"
            >
              Đóng
            </button>
          </div>

          <div className="space-y-4 overflow-y-auto p-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase text-blue-600">Tài khoản</p>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-stone-500">Username</dt>
                    <dd className="font-medium text-stone-900">{currentUser?.username || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Email</dt>
                    <dd className="font-medium text-stone-900">{currentUser?.email}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Role</dt>
                    <dd className="font-medium text-stone-900">{currentUser?.roles.join(", ") || "user"}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  onClick={() => void handleLogout()}
                  className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100"
                >
                  Đăng xuất
                </button>
              </div>

              <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase text-blue-600">Tìm kiếm</p>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-stone-500">Số nguồn mặc định</dt>
                    <dd className="font-medium text-stone-900">{topK}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Session history</dt>
                    <dd className="font-medium text-stone-900">{featureSessionHistory ? "Bật" : "Tắt"}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">API base</dt>
                    <dd className="break-all font-medium text-stone-900">{process.env.NEXT_PUBLIC_API_BASE || "/api/v1"}</dd>
                  </div>
                </dl>
              </div>

              <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase text-blue-600">Article Import</p>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-stone-500">Ngôn ngữ dịch</dt>
                    <dd className="font-medium text-stone-900">Tiếng Việt</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Tốc độ dịch</dt>
                    <dd className="font-medium text-stone-900">Cân bằng tối ưu</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Glossary mặc định</dt>
                    <dd className="font-medium text-stone-900">ai-default</dd>
                  </div>
                </dl>
                <p className="mt-3 text-xs text-stone-500">Backend dịch theo batch vừa phải để nhanh hơn nhưng vẫn hạn chế timeout/rate-limit.</p>
              </div>

              <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase text-blue-600">9Router và WordPress</p>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-stone-500">9Router dashboard</dt>
                    <dd className="break-all font-medium text-stone-900">{process.env.NEXT_PUBLIC_9ROUTER_DASHBOARD_URL || "http://localhost:20128/dashboard"}</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">Article model</dt>
                    <dd className="font-medium text-stone-900">cx/gpt-5.5</dd>
                  </div>
                  <div>
                    <dt className="text-stone-500">WordPress target</dt>
                    <dd className="break-all font-medium text-stone-900">Thiết lập trong Article Import</dd>
                  </div>
                </dl>
              </div>
            </div>

            {canManageKeys ? (
              <KeyManager
                keys={keys}
                isLoading={isLoadingKeys}
                errorMessage={keysError}
                onAdd={handleAddKey}
                onDelete={handleDeleteKey}
              />
            ) : (
              <div className="rounded-2xl border border-blue-100 bg-white p-4 text-sm text-stone-600 shadow-sm">
                Tavily keys do admin cấu hình. Nếu search không có Tavily key, backend sẽ dùng fallback SearXNG khi khả dụng.
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  function renderAdminModal() {
    if (!adminOpen || !canViewAdminPanel) {
      return null;
    }

    return (
      <div className="fixed inset-0 z-50 bg-blue-950/45 p-3 backdrop-blur-sm md:p-6">
        <div className="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-blue-100 bg-[#f8fbff] shadow-2xl">
          <div className="flex items-center justify-between border-b border-blue-100 bg-white px-5 py-4">
            <div>
              <p className="text-xs font-semibold uppercase text-orange-600">Quản trị</p>
              <h2 className="text-lg font-semibold text-stone-900">Quản lý hệ thống</h2>
            </div>
            <button
              type="button"
              onClick={() => setAdminOpen(false)}
              className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 hover:bg-blue-50"
            >
              Đóng
            </button>
          </div>

          <div className="grid min-h-0 flex-1 md:grid-cols-[220px_1fr]">
            <nav className="flex gap-2 overflow-x-auto border-b border-blue-100 bg-white p-3 md:block md:space-y-1 md:overflow-visible md:border-b-0 md:border-r">
              {adminNavItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveAdminTab(item.key)}
                  className={`shrink-0 rounded-xl px-3 py-2 text-left text-sm font-medium transition md:w-full ${
                    visibleAdminTab === item.key
                      ? "bg-blue-700 text-white shadow-sm"
                      : "border border-blue-100 bg-white text-stone-700 hover:bg-orange-50 md:border-0"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>

            <div className="min-h-0 overflow-y-auto p-4 md:p-5">
              {renderAdminContent()}
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
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 shadow-sm hover:bg-orange-50"
            >
              Cài đặt
            </button>
            {canViewAdminPanel ? (
              <button
                type="button"
                onClick={() => setAdminOpen(true)}
                className="rounded-xl bg-blue-700 px-3 py-2 text-xs font-medium text-white shadow-sm hover:bg-blue-600"
              >
                Quản trị
              </button>
            ) : null}
          </div>
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
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="rounded-xl border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-800 shadow-sm hover:bg-orange-50"
            >
              Cài đặt
            </button>
            {canViewAdminPanel ? (
              <button
                type="button"
                onClick={() => setAdminOpen(true)}
                className="rounded-xl bg-blue-700 px-3 py-2 text-xs font-medium text-white shadow-sm hover:bg-blue-600"
              >
                Quản trị
              </button>
            ) : null}
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-5 md:px-8">
          <div className="mx-auto w-full max-w-6xl min-w-0">
            <ArticleImportPanel authToken={authToken || ""} />
          </div>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return renderAuthGate();
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
      {renderAdminModal()}
    </main>
  );
}

