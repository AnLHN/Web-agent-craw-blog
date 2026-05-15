"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  addTavilyKey,
  createChatSession,
  clearChatSessions,
  deleteChatSession,
  deleteTavilyKey,
  fetchTavilyKeys,
  getChatSession,
  listChatSessions,
  replayChatSession,
  searchWeb,
} from "@/services/apiClient";
import { ChatSession, SearchData, TavilyKeyInfo } from "@/types/api";
import { prettyDate } from "@/utils/date";

import { KeyManager } from "./KeyManager";
import { OpsDashboard } from "./OpsDashboard";
import { PromptManagerPopup } from "./PromptManagerPopup";
import { SearchResultPanel } from "./SearchResultPanel";

export function SearchWorkspace() {
  const featureSessionHistory =
    (process.env.NEXT_PUBLIC_FEATURE_SESSION_HISTORY || "true").toLowerCase() !== "false";
  const featureOpsDashboard =
    (process.env.NEXT_PUBLIC_FEATURE_OPS_DASHBOARD || "true").toLowerCase() !== "false";
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);

  const [result, setResult] = useState<SearchData | null>(null);
  const [lastSubmittedQuery, setLastSubmittedQuery] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

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
      setCurrentSession(response.data.session);
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

  async function handleReplaySession(sessionId: string) {
    try {
      const response = await replayChatSession(sessionId);
      if (!response.success || !response.data) {
        setSessionError(response.error?.message || "Khong replay duoc session.");
        return;
      }
      const replayed = response.data.session;
      setCurrentSessionId(replayed.id);
      setCurrentSession(replayed);
      await loadSessionHistory();
    } catch {
      setSessionError("Khong ket noi duoc backend khi replay session.");
    }
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
          setResult(null);
          setLastSubmittedQuery("");
        }
      }
    } catch {
      setSessionError("Khong ket noi duoc backend khi xoa session.");
    }
  }

  async function handleClearSessions() {
    try {
      const response = await clearChatSessions();
      if (!response.success || !response.data) {
        setSessionError(response.error?.message || "Khong xoa duoc lich su session.");
        return;
      }
      setSessions([]);
      setCurrentSessionId(null);
      setCurrentSession(null);
      setResult(null);
      setLastSubmittedQuery("");
      setSessionError(null);
    } catch {
      setSessionError("Khong ket noi duoc backend khi xoa lich su.");
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
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }

    setSearchError(null);
    setIsSearching(true);

    try {
      const submittedQuery = query.trim();
      setLastSubmittedQuery(submittedQuery);
      const sessionIdForSearch = await ensureActiveSessionForSearch();
      const response = await searchWeb(
        submittedQuery,
        topK,
        sessionIdForSearch,
      );
      if (!response.success || !response.data) {
        setResult(null);
        setSearchError(response.error?.message || "Search that bai.");
        return;
      }
      setResult(response.data);
      if (featureSessionHistory && currentSessionId) {
        await loadSessionDetail(currentSessionId);
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

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 md:px-8">
      <PromptManagerPopup />
      <header className="rounded-3xl border border-stone-300 bg-[radial-gradient(circle_at_top_left,_#fde68a_0%,_#fff7ed_40%,_#fafaf9_100%)] p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">
          Tavily-first Search Pipeline
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-stone-900 md:text-4xl">
          Web Search Aggregator
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-stone-700 md:text-base">
          Moi truy van deu uu tien Tavily truoc. Chi khi Tavily khong co key, het
          quota, hoac ket qua khong dat nguong thi moi fallback sang SearXNG.
        </p>
      </header>

      <div className="mt-6 grid gap-6">
        <KeyManager
          keys={keys}
          isLoading={isLoadingKeys}
          errorMessage={keysError}
          onAdd={handleAddKey}
          onDelete={handleDeleteKey}
        />

        <div className={`grid gap-6 ${featureSessionHistory ? "lg:grid-cols-[300px_1fr]" : ""}`}>
          {featureSessionHistory ? <aside className="space-y-4">
            <section className="rounded-2xl border border-stone-300 bg-white/90 p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">
                  Current Session
                </h2>
                <button
                  type="button"
                  onClick={() => void handleCreateSession()}
                  className="rounded-lg border border-stone-300 bg-white px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-100"
                >
                  New
                </button>
              </div>
              <p className="mt-2 text-sm text-stone-800">{currentSessionLabel}</p>
              {sessionError ? (
                <p className="mt-2 text-xs text-red-700">{sessionError}</p>
              ) : null}
            </section>

            <section className="rounded-2xl border border-stone-300 bg-white/90 p-4 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">
                  Session History
                </h2>
                <button
                  type="button"
                  onClick={() => void handleClearSessions()}
                  className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
                >
                  Clear all
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {isLoadingSessions ? (
                  <p className="text-xs text-stone-500">Loading sessions...</p>
                ) : null}
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                      currentSessionId === session.id
                        ? "border-amber-400 bg-amber-50"
                        : "border-stone-200 bg-white hover:bg-stone-50"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setCurrentSessionId(session.id);
                        void loadSessionDetail(session.id);
                      }}
                      className="w-full text-left"
                    >
                      <p className="line-clamp-1 text-sm font-medium text-stone-800">
                        {session.title}
                      </p>
                      <p className="text-xs text-stone-500">
                        {prettyDate(session.last_message_at)} | {session.message_count} msgs
                      </p>
                    </button>
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          void handleReplaySession(session.id);
                        }}
                        className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
                      >
                        Replay
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void navigator.clipboard.writeText(session.title);
                        }}
                        className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
                      >
                        Copy title
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleDeleteSession(session.id);
                        }}
                        className="rounded-md border border-red-300 px-2 py-1 text-[11px] text-red-700 hover:bg-red-50"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
                {!isLoadingSessions && sessions.length === 0 ? (
                  <p className="text-xs text-stone-500">No session history yet.</p>
                ) : null}
              </div>
            </section>

            <section className="rounded-2xl border border-stone-300 bg-white/90 p-4 shadow-sm">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">
                Session Thread
              </h2>
              <div className="mt-3 max-h-72 space-y-2 overflow-auto pr-1">
                {(currentSession?.messages || []).map((message) => (
                  <div key={message.id} className="rounded-lg border border-stone-200 bg-stone-50 p-2">
                    <p className="text-[11px] uppercase tracking-wide text-stone-500">
                      {message.role} | {prettyDate(message.created_at)}
                    </p>
                    <p className="mt-1 line-clamp-4 text-xs text-stone-800">{message.content}</p>
                  </div>
                ))}
                {currentSession && currentSession.messages.length === 0 ? (
                  <p className="text-xs text-stone-500">Session nay chua co message.</p>
                ) : null}
              </div>
            </section>
          </aside> : null}

          <div className="space-y-6">
            <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm">
              <form onSubmit={handleSearch} className="grid gap-3 md:grid-cols-[1fr_100px_auto]">
                <input
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Nhap truy van..."
                  className="rounded-xl border border-stone-300 px-4 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value) || 5)}
                  className="rounded-xl border border-stone-300 px-4 py-2 text-sm focus:border-amber-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={isSearching}
                  className="rounded-xl bg-amber-500 px-5 py-2 text-sm font-semibold text-stone-900 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSearching ? "Searching..." : "Search"}
                </button>
              </form>
              {featureSessionHistory && currentSessionId ? (
                <p className="mt-2 text-xs text-stone-500">Session ID: {currentSessionId}</p>
              ) : null}
            </section>

            <SearchResultPanel
              isLoading={isSearching}
              errorMessage={searchError}
              result={result}
              latestUserQuery={lastSubmittedQuery}
              sessionMessages={currentSession?.messages || []}
            />
            {featureOpsDashboard ? <OpsDashboard onKeysChanged={loadKeys} /> : null}
          </div>
        </div>
      </div>
    </main>
  );
}
