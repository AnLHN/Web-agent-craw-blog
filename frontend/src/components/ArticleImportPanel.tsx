"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  checkArticleLlmHealth,
  dryRunWordPressImport,
  fetchArticleImport,
  importArticle,
  pasteWordPressImport,
  translateArticleImport,
} from "@/services/apiClient";
import { ArticleBlock, ArticleImportRun, ArticleLlmHealthData } from "@/types/api";

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: "Queued",
    fetched: "Fetched",
    extracted: "Extracted",
    translated: "Translated",
    draft_ready: "Draft Ready",
    pasted: "Pasted",
    failed: "Failed",
  };
  return map[status] || status;
}

function metadataText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function translationMessage(metadata: Record<string, unknown>): string | null {
  if (String(metadata.translation_status || "") === "failed") {
    const failedError = metadataText(metadata.translation_error);
    if (failedError.includes("ninerouter_http_429")) {
      return "9Router/model rate limit reached. Please wait for the quota window to reset, then continue translate.";
    }
    if (failedError.includes("ninerouter_http_500") || failedError.includes("ninerouter_http_502") || failedError.includes("ninerouter_http_503") || failedError.includes("ninerouter_http_504") || failedError.includes("UNAVAILABLE")) {
      return "9Router/model is temporarily unavailable. Please wait a bit and retry translate.";
    }
    if (failedError && failedError !== "-") {
      return failedError;
    }
    return "Translation failed. Please retry after a short wait.";
  }
  if (metadata.translation_pause_reason) {
    return "Translation paused to avoid provider overload/rate limits. Press Translate again after a short wait to continue.";
  }
  const error = metadataText(metadata.translation_error);
  if (!error || error === "-") {
    return null;
  }
  if (error.includes("ninerouter_http_429")) {
    return "9Router/model rate limit reached. Wait for the quota window to reset, then press Translate again.";
  }
  return error;
}

function blockText(block: ArticleBlock): string {
  return block.translated_text || block.source_text || block.metadata.caption as string || "";
}

function translationCompletionPct(run: ArticleImportRun): number {
  const textBlocks = run.blocks.filter((block) => block.block_type !== "image" && block.block_type !== "unknown");
  if (textBlocks.length === 0) {
    return 100;
  }
  const translatedCount = textBlocks.filter((block) => Boolean((block.translated_text || "").trim())).length;
  return Math.max(0, Math.min(100, Math.trunc((translatedCount / textBlocks.length) * 100)));
}

function importProgress(run: ArticleImportRun | null): { pct: number; stage: string; message: string; active: boolean } | null {
  if (!run) {
    return null;
  }
  const pctRaw = Number(run.metadata.import_progress_pct ?? 0);
  const savedPct = Number.isFinite(pctRaw) ? Math.max(0, Math.min(100, Math.trunc(pctRaw))) : 0;
  const computedPct = translationCompletionPct(run);
  const pct = Math.max(savedPct, computedPct);
  const translationStatus = String(run.metadata.translation_status || "");
  const pauseReason = metadataText(run.metadata.translation_pause_reason);
  const hasPauseReason = pauseReason !== "-";
  const stageRaw = metadataText(run.metadata.import_progress_stage);
  const messageRaw = metadataText(run.metadata.import_progress_message);

  if (translationStatus === "partial" || hasPauseReason) {
    return {
      pct,
      stage: "paused",
      message: "Translation paused. Press Translate to continue.",
      active: false,
    };
  }
  if (translationStatus === "failed") {
    return {
      pct,
      stage: "failed",
      message: "Translation failed. Retry after a short wait.",
      active: false,
    };
  }
  return {
    pct,
    stage: stageRaw,
    message: messageRaw,
    active: Boolean(run.metadata.import_in_progress),
  };
}

function responseErrorMessage(response: {
  error?: { message?: string; details?: Record<string, unknown> | null } | null;
}): string {
  const detailMessage = response.error?.details?.message;
  if (typeof detailMessage === "string" && detailMessage.trim()) {
    return detailMessage;
  }
  const detailStatus = response.error?.details?.status;
  if (typeof detailStatus === "string" && detailStatus.trim()) {
    return detailStatus;
  }
  return response.error?.message || "Request failed.";
}

function unknownErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export function ArticleImportPanel({ authToken }: { authToken: string }) {
  const nineRouterDashboardUrl =
    process.env.NEXT_PUBLIC_9ROUTER_DASHBOARD_URL || "http://localhost:20128/dashboard";
  const [url, setUrl] = useState("");
  const [wordpressTargetUrl, setWordpressTargetUrl] = useState("");
  const [glossaryKey, setGlossaryKey] = useState("ai-default");
  const [run, setRun] = useState<ArticleImportRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [isDryRunning, setIsDryRunning] = useState(false);
  const [isPasting, setIsPasting] = useState(false);
  const [autoContinueTranslate, setAutoContinueTranslate] = useState(false);
  const [autoRetrySeconds, setAutoRetrySeconds] = useState(0);
  const [llmHealth, setLlmHealth] = useState<ArticleLlmHealthData | null>(null);
  const [llmHealthError, setLlmHealthError] = useState<string | null>(null);
  const [isCheckingLlm, setIsCheckingLlm] = useState(false);
  const [isAutoContinueSuppressed, setIsAutoContinueSuppressed] = useState(false);

  const assetSummary = useMemo(() => {
    if (!run) {
      return { downloaded: 0, skipped: 0, failed: 0 };
    }
    return {
      downloaded: run.assets.filter((asset) => asset.download_status === "downloaded").length,
      skipped: run.assets.filter((asset) => asset.download_status === "skipped").length,
      failed: run.assets.filter((asset) => asset.download_status === "failed").length,
    };
  }, [run]);
  const currentTranslationMessage = run ? translationMessage(run.metadata) : null;
  const progress = useMemo(() => importProgress(run), [run]);
  const runId = run?.id ?? null;
  const isImportInProgress = Boolean(run?.metadata.import_in_progress);
  const shouldAutoContinue =
    autoContinueTranslate &&
    !isAutoContinueSuppressed &&
    Boolean(run) &&
    Boolean(run?.metadata.translation_pause_reason) &&
    String(run?.metadata.translation_status || "") === "partial" &&
    !isTranslating &&
    !isImporting &&
    !Boolean(run?.metadata.import_in_progress);

  useEffect(() => {
    if (!runId || (!isImportInProgress && !isTranslating)) {
      return;
    }
    let isMounted = true;
    const timer = setInterval(async () => {
      try {
        const response = await fetchArticleImport(runId);
        if (!isMounted || !response.success || !response.data) {
          return;
        }
        setRun(response.data.run);
      } catch {
        // Keep current UI state; polling will retry.
      }
    }, 1200);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, [runId, isImportInProgress, isTranslating]);

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!url.trim()) {
      return;
    }
    setIsImporting(true);
    setError(null);
    try {
      const response = await importArticle(authToken, {
        url: url.trim(),
        mode: "draft",
        target_language: "vi",
        glossary_key: glossaryKey.trim() || undefined,
        wordpress_target_url: wordpressTargetUrl.trim() || undefined,
        async_mode: true,
      });
      if (!response.success || !response.data) {
        setError(response.error?.message || "Article import failed.");
        return;
      }
      setRun(response.data.run);
    } catch (error) {
      setError(unknownErrorMessage(error, "Article import request failed."));
    } finally {
      setIsImporting(false);
    }
  }

  async function handleDryRun() {
    if (!run) {
      return;
    }
    setIsAutoContinueSuppressed(true);
    setAutoContinueTranslate(false);
    setAutoRetrySeconds(0);
    setIsDryRunning(true);
    setError(null);
    try {
      const response = await dryRunWordPressImport(authToken, run.id);
      if (!response.success || !response.data) {
        setError(responseErrorMessage(response));
        if (response.data?.run) {
          setRun(response.data.run);
        }
        return;
      }
      setRun(response.data.run);
    } catch (error) {
      setError(unknownErrorMessage(error, "WordPress dry-run request failed."));
    } finally {
      setIsDryRunning(false);
    }
  }

  async function handleTranslate() {
    if (!run) {
      return;
    }
    setIsAutoContinueSuppressed(false);
    setIsTranslating(true);
    setError(null);
    try {
      const response = await translateArticleImport(authToken, run.id);
      if (!response.success || !response.data) {
        setError(responseErrorMessage(response));
        if (response.data?.run) {
          setRun(response.data.run);
        }
        return;
      }
      setRun(response.data.run);
    } catch (error) {
      setError(unknownErrorMessage(error, "Article translation request failed."));
    } finally {
      setIsTranslating(false);
    }
  }

  useEffect(() => {
    if (!run) {
      return;
    }
    if (!shouldAutoContinue) {
      return;
    }

    let secondsLeft = 20;
    const init = setTimeout(() => setAutoRetrySeconds(secondsLeft), 0);
    const countdown = setInterval(() => {
      secondsLeft -= 1;
      setAutoRetrySeconds(Math.max(0, secondsLeft));
    }, 1000);

    const timer = setTimeout(() => {
      setAutoRetrySeconds(0);
      void (async () => {
        setIsTranslating(true);
        setError(null);
        try {
          const response = await translateArticleImport(authToken, run.id);
          if (!response.success || !response.data) {
            setError(responseErrorMessage(response));
            if (response.data?.run) {
              setRun(response.data.run);
            }
            return;
          }
          setRun(response.data.run);
        } catch (error) {
          setError(unknownErrorMessage(error, "Article translation request failed."));
        } finally {
          setIsTranslating(false);
        }
      })();
    }, 20000);

    return () => {
      clearTimeout(init);
      clearInterval(countdown);
      clearTimeout(timer);
      setTimeout(() => setAutoRetrySeconds(0), 0);
    };
  }, [
    authToken,
    run,
    shouldAutoContinue,
  ]);

  useEffect(() => {
    if (!run || !isTranslating) {
      return;
    }
    const translationStatus = String(run.metadata.translation_status || "");
    const stage = String(run.metadata.import_progress_stage || "");
    const paused = Boolean(run.metadata.translation_pause_reason) || translationStatus === "partial" || stage === "paused";
    const finished = translationStatus === "translated" || translationStatus === "failed" || stage === "done" || stage === "failed";
    if (paused || finished || !Boolean(run.metadata.import_in_progress)) {
      const timer = setTimeout(() => setIsTranslating(false), 0);
      return () => clearTimeout(timer);
    }
  }, [run, isTranslating]);

  async function handlePaste() {
    if (!run) {
      return;
    }
    setIsAutoContinueSuppressed(true);
    setAutoContinueTranslate(false);
    setAutoRetrySeconds(0);
    setIsPasting(true);
    setError(null);
    try {
      const response = await pasteWordPressImport(authToken, run.id);
      if (!response.success || !response.data) {
        setError(responseErrorMessage(response));
        if (response.data?.run) {
          setRun(response.data.run);
        }
        return;
      }
      setRun(response.data.run);
    } catch (error) {
      setError(unknownErrorMessage(error, "WordPress paste request failed."));
    } finally {
      setIsPasting(false);
    }
  }

  async function handleCheckLlmHealth() {
    setIsCheckingLlm(true);
    setLlmHealthError(null);
    try {
      const response = await checkArticleLlmHealth();
      if (!response.data) {
        setLlmHealth(null);
        setLlmHealthError(response.error?.message || "Khong kiem tra duoc 9router.");
        return;
      }
      setLlmHealth(response.data);
      setLlmHealthError(response.success ? null : response.error?.message || response.data.message);
    } catch (error) {
      setLlmHealth(null);
      setLlmHealthError(unknownErrorMessage(error, "LLM health check request failed."));
    } finally {
      setIsCheckingLlm(false);
    }
  }

  return (
    <section className="w-full min-w-0 space-y-4 overflow-hidden">
      <div className="min-w-0">
        <p className="text-xs font-extrabold uppercase tracking-[0.16em] text-[#d97706]">Article Import</p>
        <h3 className="mt-1 text-2xl font-extrabold text-[#18201c]">URL to WordPress draft</h3>
      </div>

      <div className="grid w-full min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <form onSubmit={handleImport} className="grid min-w-0 max-w-3xl gap-4 rounded-lg border border-[#dfe6dc] bg-white p-5 shadow-sm shadow-[#12312f]/5">
          <label className="grid min-w-0 gap-1">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">Source URL</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.com/article"
              className="min-w-0 rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2.5 text-sm outline-none focus:border-[#0f766e] focus:bg-white focus:ring-4 focus:ring-[#0f766e]/10"
            />
          </label>
          <div className="grid min-w-0 gap-3 md:grid-cols-2">
            <label className="grid min-w-0 gap-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">Glossary</span>
              <input
                type="text"
                value={glossaryKey}
                onChange={(event) => setGlossaryKey(event.target.value)}
                className="min-w-0 rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2.5 text-sm outline-none focus:border-[#0f766e] focus:bg-white focus:ring-4 focus:ring-[#0f766e]/10"
              />
            </label>
            <label className="grid min-w-0 gap-1">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">WordPress Target URL</span>
              <input
                type="url"
                value={wordpressTargetUrl}
                onChange={(event) => setWordpressTargetUrl(event.target.value)}
                placeholder="https://site.com/wp-admin/post-new.php"
                className="min-w-0 rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2.5 text-sm outline-none focus:border-[#0f766e] focus:bg-white focus:ring-4 focus:ring-[#0f766e]/10"
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={isImporting}
            className="w-fit rounded-lg bg-[#d97706] px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-[#d97706]/20 hover:bg-[#b45309] disabled:opacity-60"
          >
            {isImporting ? "Starting..." : "Fetch & Build Draft"}
          </button>
        </form>

        <div className="grid min-w-0 content-start gap-3 rounded-lg border border-[#dfe6dc] bg-white p-5 shadow-sm shadow-[#12312f]/5">
          <div className="min-w-0">
            <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-[#0f766e]">9router OpenAI</p>
            <h4 className="mt-1 text-sm font-bold text-[#18201c]">API health</h4>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleCheckLlmHealth}
              disabled={isCheckingLlm}
              className="rounded-lg border border-[#dfe6dc] px-3 py-2 text-xs font-bold text-[#12312f] hover:border-[#0f766e] hover:bg-[#e6f3ef] disabled:opacity-60"
            >
              {isCheckingLlm ? "Checking..." : "Check 9router"}
            </button>
            <a
              href={nineRouterDashboardUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg bg-[#0f766e] px-3 py-2 text-xs font-bold text-white shadow-sm shadow-[#0f766e]/20 hover:bg-[#115e59]"
            >
              Open dashboard
            </a>
          </div>
          {llmHealth ? (
            <div className="min-w-0 space-y-1 rounded-lg bg-[#f7f8f4] p-3 text-xs text-[#66736b]">
              <p className={llmHealth.ok ? "font-semibold text-emerald-700" : "font-semibold text-orange-700"}>
                {llmHealth.ok ? "Ready" : "Not ready"} · {llmHealth.status}
              </p>
              <p className="break-words">Model: {llmHealth.model || "-"}</p>
              <p className="break-all">Base URL: {llmHealth.base_url || "-"}</p>
              <p>Router auth: {llmHealth.has_api_key ? "configured" : "not set / optional"}</p>
              <p>Latency: {llmHealth.latency_ms}ms</p>
            </div>
          ) : null}
          {llmHealthError ? (
            <p className="break-words rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs text-orange-800">
              {llmHealthError}
            </p>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="max-w-3xl break-words rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-sm font-medium text-orange-800">
          {error}
        </div>
      ) : null}

      {run ? (
        <div className="grid min-w-0 gap-4 overflow-hidden">
          {progress ? (
            <div className="min-w-0 rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5">
              <div className="mb-2 flex items-center justify-between gap-2 text-xs text-stone-600">
                <p className="font-semibold text-blue-700">
                  Import progress: {progress.pct}%
                </p>
                <p className="uppercase tracking-wide">{progress.stage}</p>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-[#e6eee7]">
                <div
                  className="h-2 rounded-full bg-[#0f766e] transition-all duration-500"
                  style={{ width: `${progress.pct}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-stone-600">
                {progress.message}
                {progress.active ? " (running)" : ""}
              </p>
            </div>
          ) : null}

          <div className="grid min-w-0 gap-3 rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5 md:grid-cols-4">
            <div className="min-w-0">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-[#0f766e]">Status</p>
              <p className="text-sm font-semibold text-stone-900">{statusLabel(run.status)}</p>
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-[#0f766e]">Blocks</p>
              <p className="text-sm font-semibold text-stone-900">{run.blocks.length}</p>
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-[#0f766e]">Assets</p>
              <p className="break-words text-sm font-semibold text-stone-900">
                {assetSummary.downloaded} ok / {assetSummary.skipped} skipped / {assetSummary.failed} failed
              </p>
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-[#0f766e]">Run ID</p>
              <p className="break-all text-xs text-stone-600">{run.id}</p>
            </div>
          </div>

          <div className="min-w-0 overflow-hidden rounded-lg border border-[#dfe6dc] bg-white p-5 shadow-sm shadow-[#12312f]/5">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-[#0f766e]">Draft</p>
                <h4 className="break-words text-lg font-extrabold text-[#18201c]">{run.draft?.title || run.source.title || "Untitled"}</h4>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={handleTranslate}
                  disabled={isTranslating}
                  className="rounded-lg border border-[#dfe6dc] px-3 py-2 text-xs font-bold text-[#12312f] hover:border-[#0f766e] hover:bg-[#e6f3ef] disabled:opacity-60"
                >
                  {isTranslating ? "Translating..." : "Translate"}
                </button>
                <label className="flex items-center gap-1 rounded-lg border border-[#dfe6dc] px-2 py-1 text-[11px] font-bold text-[#12312f]">
                  <input
                    type="checkbox"
                    checked={autoContinueTranslate}
                    onChange={(event) => setAutoContinueTranslate(event.target.checked)}
                  />
                  Auto
                </label>
                <button
                  type="button"
                  onClick={handleDryRun}
                  disabled={isDryRunning}
                  className="rounded-lg border border-[#dfe6dc] px-3 py-2 text-xs font-bold text-[#12312f] hover:border-[#0f766e] hover:bg-[#e6f3ef] disabled:opacity-60"
                >
                  {isDryRunning ? "Checking..." : "Dry Run"}
                </button>
                <button
                  type="button"
                  onClick={handlePaste}
                  disabled={isPasting || !run.draft?.content}
                  className="rounded-lg bg-[#0f766e] px-3 py-2 text-xs font-bold text-white shadow-sm shadow-[#0f766e]/20 hover:bg-[#115e59] disabled:opacity-60"
                >
                  {isPasting ? "Pasting..." : "Paste Draft"}
                </button>
              </div>
            </div>
            {run.draft?.excerpt ? <p className="mt-2 break-words text-sm leading-6 text-[#66736b]">{run.draft.excerpt}</p> : null}
            <div className="mt-3 grid min-w-0 gap-2 text-xs text-[#66736b] md:grid-cols-2">
              <p className="break-words">Slug: {run.draft?.slug || "-"}</p>
              <p className="break-words">Source: {run.source.domain}</p>
              <p className="break-words">Translation: {metadataText(run.metadata.translation_status)}</p>
              <p className="break-words">WordPress: {metadataText(run.metadata.wordpress_paste_status || run.metadata.wordpress_dry_run_status)}</p>
              {currentTranslationMessage ? (
                <p className="break-words text-orange-700 md:col-span-2">
                  Translation note: {currentTranslationMessage}
                </p>
              ) : null}
              {shouldAutoContinue && autoRetrySeconds > 0 ? (
                <p className="break-words font-bold text-[#0f766e] md:col-span-2">
                  Auto continue in {autoRetrySeconds}s...
                </p>
              ) : null}
              {run.metadata.wordpress_dry_run_message || run.metadata.wordpress_paste_message ? (
                <p className="break-words text-orange-700 md:col-span-2">
                  WordPress message:{" "}
                  {metadataText(run.metadata.wordpress_paste_message || run.metadata.wordpress_dry_run_message)}
                </p>
              ) : null}
            </div>
            {run.draft?.content ? (
              <pre className="mt-4 max-h-72 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-[#111917] p-4 font-mono text-xs leading-5 text-[#e8efe9]">
                {run.draft.content}
              </pre>
            ) : null}
          </div>

          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <div className="min-w-0 overflow-hidden rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5">
              <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-[#0f766e]">Blocks</p>
              <div className="mt-3 max-h-96 space-y-2 overflow-auto">
                {run.blocks.map((block) => (
                  <div key={block.id} className="min-w-0 rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] p-3">
                    <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-[#0f766e]">
                      {block.order_index + 1}. {block.block_type}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-[#4d5a53]">{blockText(block) || "-"}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="min-w-0 overflow-hidden rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5">
              <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-[#0f766e]">Assets</p>
              <div className="mt-3 max-h-96 space-y-2 overflow-auto">
                {run.assets.length === 0 ? <p className="text-sm text-[#66736b]">No image assets.</p> : null}
                {run.assets.map((asset) => (
                  <div key={asset.id} className="min-w-0 rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] p-3">
                    <div className="flex min-w-0 items-center justify-between gap-2">
                      <p className="min-w-0 break-words text-sm font-bold text-[#18201c]">{asset.id}</p>
                      <span className="rounded-full bg-white px-2 py-1 text-[11px] font-bold text-[#0f766e]">
                        {asset.download_status}
                      </span>
                    </div>
                    <p className="mt-1 break-all font-mono text-xs text-[#66736b]">{asset.source_url}</p>
                    {asset.local_path ? <p className="mt-1 break-all font-mono text-xs text-[#66736b]">{asset.local_path}</p> : null}
                    {asset.caption ? <p className="mt-2 break-words text-sm leading-6 text-[#4d5a53]">{asset.caption}</p> : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
