"use client";

import { FormEvent, useState } from "react";

import {
  fetchAdminSystemStatus,
  fetchAuditLogs,
  fetchLlmConfig,
  fetchLlmHealth,
  fetchTavilyKeyMetrics,
  patchLlmConfig,
  resetTavilyKeyCooldown,
  runLlmTest,
  updateTavilyKey,
} from "@/services/apiClient";
import { AdminSystemStatusData, AuditLogItem, LlmRuntimeConfig, TavilyKeyMetricsData } from "@/types/api";

type OpsDashboardProps = {
  authToken: string;
  onKeysChanged: () => Promise<void>;
};

export function OpsDashboard({ authToken, onKeysChanged }: OpsDashboardProps) {
  const [metrics, setMetrics] = useState<TavilyKeyMetricsData | null>(null);
  const [llmConfig, setLlmConfig] = useState<LlmRuntimeConfig | null>(null);
  const [systemStatus, setSystemStatus] = useState<AdminSystemStatusData | null>(null);
  const [audit, setAudit] = useState<AuditLogItem[]>([]);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [llmHealthMessage, setLlmHealthMessage] = useState<string>("");
  const [testOutput, setTestOutput] = useState<string>("");
  const [testPrompt, setTestPrompt] = useState("Tra loi mot cau ve trang thai he thong.");
  const [isLoading, setIsLoading] = useState(false);

  function safeConfig(prev: LlmRuntimeConfig | null): LlmRuntimeConfig {
    if (prev) {
      return prev;
    }
    return {
      base_url: "",
      model: "",
      temperature: 0.2,
      max_tokens: null,
      summary_max_tokens: 512,
      summary_max_chars: 512,
      summary_system_prompt:
        "Ban la tro ly tong hop thong tin web chinh xac. Tra loi ngan gon, ro y, dung du lieu tu nguon. Khong bia them thong tin ngoai nguon; neu thieu du lieu thi noi ro.",
      updated_at: "",
    };
  }

  async function reloadAll() {
    setIsLoading(true);
    setStatusMessage("");
    try {
      const [metricsRes, configRes, systemStatusRes, auditRes] = await Promise.all([
        fetchTavilyKeyMetrics(),
        fetchLlmConfig(),
        fetchAdminSystemStatus(authToken),
        fetchAuditLogs(40),
      ]);
      if (metricsRes.success && metricsRes.data) {
        setMetrics(metricsRes.data);
      }
      if (configRes.success && configRes.data) {
        setLlmConfig(configRes.data.config);
      }
      if (systemStatusRes.success && systemStatusRes.data) {
        setSystemStatus(systemStatusRes.data);
      }
      if (auditRes.success && auditRes.data) {
        setAudit(auditRes.data.events);
      }
    } finally {
      setIsLoading(false);
    }
  }

  async function handleToggleKey(keyId: string, currentStatus: string) {
    const nextStatus = currentStatus === "disabled" ? "active" : "disabled";
    const response = await updateTavilyKey(authToken, keyId, { status: nextStatus });
    if (!response.success) {
      setStatusMessage(response.error?.message || "Cap nhat key that bai.");
      return;
    }
    setStatusMessage(`Da chuyen key ${keyId.slice(0, 8)} sang ${nextStatus}.`);
    await Promise.all([reloadAll(), onKeysChanged()]);
  }

  async function handleResetCooldown(keyId: string) {
    const response = await resetTavilyKeyCooldown(authToken, keyId);
    if (!response.success) {
      setStatusMessage(response.error?.message || "Reset cooldown that bai.");
      return;
    }
    setStatusMessage(`Da reset cooldown cho key ${keyId.slice(0, 8)}.`);
    await Promise.all([reloadAll(), onKeysChanged()]);
  }

  async function handleCheckLlmHealth() {
    const response = await fetchLlmHealth();
    if (!response.success || !response.data) {
      setLlmHealthMessage(response.error?.message || "LLM health check that bai.");
      return;
    }
    setLlmHealthMessage(
      response.data.ok
        ? `LLM OK (${response.data.latency_ms} ms)`
        : `LLM FAIL: ${response.data.message}`,
    );
  }

  async function handleSaveLlmConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!llmConfig) {
      return;
    }
    const response = await patchLlmConfig(authToken, {
      base_url: llmConfig.base_url,
      model: llmConfig.model,
      temperature: llmConfig.temperature,
      max_tokens: llmConfig.max_tokens ?? null,
      summary_max_tokens: llmConfig.summary_max_tokens ?? 512,
      summary_system_prompt: llmConfig.summary_system_prompt,
    });
    if (!response.success || !response.data) {
      setStatusMessage(response.error?.message || "Luu LLM config that bai.");
      return;
    }
    setLlmConfig(response.data.config);
    setStatusMessage("Da cap nhat LLM runtime config.");
    await reloadAll();
  }

  async function handleLlmTest() {
    const response = await runLlmTest(authToken, testPrompt.trim());
    if (!response.success || !response.data) {
      setTestOutput(response.error?.message || "LLM test that bai.");
      return;
    }
    setTestOutput(
      `${response.data.status} | ${response.data.finish_reason} | ${response.data.latency_ms} ms\n${response.data.response_preview}`,
    );
    await reloadAll();
  }

  return (
    <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-stone-900">Ops Dashboard</h2>
        <button
          type="button"
          onClick={() => void reloadAll()}
          className="rounded-lg border border-stone-300 bg-white px-3 py-1 text-xs text-stone-700 hover:bg-stone-100"
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {statusMessage ? <p className="mt-2 text-sm text-stone-700">{statusMessage}</p> : null}

      <div className="mt-4 rounded-xl border border-stone-200 p-3">
        <h3 className="text-sm font-semibold text-stone-800">System Status</h3>
        {systemStatus ? (
          <div className="mt-2 grid gap-2 text-xs text-stone-700 md:grid-cols-2">
            <p>Status: {systemStatus.status}</p>
            <p>Environment: {systemStatus.environment}</p>
            <p>Auth: {systemStatus.auth_store_backend} / {systemStatus.auth_service_type}</p>
            <p>Sessions: {systemStatus.session_store_backend} / {systemStatus.session_store_type}</p>
            <p>Database configured: {systemStatus.database_configured ? "yes" : "no"}</p>
            <p>RBAC: {systemStatus.rbac_enabled ? "enabled" : "disabled"}</p>
            <p>LLM: {systemStatus.llm_enabled && systemStatus.llm_configured ? "configured" : "not configured"}</p>
            <p>Tavily keys: {systemStatus.tavily_key_count}</p>
            <p>Article runs: {systemStatus.article_import_run_count}</p>
            <p>Article storage: {systemStatus.article_import_storage_path}</p>
          </div>
        ) : (
          <p className="mt-2 text-xs text-stone-500">System status has not been loaded yet.</p>
        )}
        {systemStatus ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(systemStatus.readiness_checks).map(([name, value]) => (
              <span key={name} className="rounded-full border border-stone-200 px-2 py-1 text-[11px] text-stone-700">
                {name}: {value}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-stone-200 p-3">
          <h3 className="text-sm font-semibold text-stone-800">Tavily Metrics</h3>
          <p className="mt-1 text-xs text-stone-600">
            Keys: {metrics?.total_keys ?? 0} | Active: {metrics?.active_keys ?? 0} | Unhealthy:{" "}
            {metrics?.unhealthy_keys ?? 0}
          </p>
          <div className="mt-3 space-y-2">
            {(metrics?.keys || []).map((key) => (
              <div key={key.id} className="rounded-lg border border-stone-200 p-2">
                <p className="text-xs font-medium text-stone-800">
                  {key.label} ({key.status})
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => void handleToggleKey(key.id, key.status)}
                    className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
                  >
                    {key.status === "disabled" ? "Enable" : "Disable"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleResetCooldown(key.id)}
                    className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
                  >
                    Reset cooldown
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-stone-200 p-3">
          <h3 className="text-sm font-semibold text-stone-800">LLM Runtime</h3>
          <form onSubmit={handleSaveLlmConfig} className="mt-2 grid gap-2">
            <input
              type="text"
              value={llmConfig?.base_url || ""}
              onChange={(event) =>
                setLlmConfig((prev) => ({ ...safeConfig(prev), base_url: event.target.value }))
              }
              placeholder="Base URL"
              className="rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <input
              type="text"
              value={llmConfig?.model || ""}
              onChange={(event) =>
                setLlmConfig((prev) => ({ ...safeConfig(prev), model: event.target.value }))
              }
              placeholder="Model"
              className="rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={llmConfig?.temperature ?? 0.2}
                onChange={(event) =>
                  setLlmConfig((prev) => ({
                    ...safeConfig(prev),
                    temperature: Number(event.target.value) || 0,
                  }))
                }
                className="rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <input
                type="number"
                min={1}
                max={16384}
                value={llmConfig?.max_tokens ?? ""}
                onChange={(event) =>
                  setLlmConfig((prev) => ({
                    ...safeConfig(prev),
                    max_tokens: Number(event.target.value) || null,
                  }))
                }
                placeholder="max tokens"
                className="rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
            </div>
            <input
              type="number"
              min={32}
              max={16384}
              value={llmConfig?.summary_max_tokens ?? 512}
              onChange={(event) =>
                setLlmConfig((prev) => ({
                  ...safeConfig(prev),
                  summary_max_tokens: Number(event.target.value) || 512,
                }))
              }
              placeholder="summary max tokens"
              className="rounded-md border border-stone-300 px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded-md bg-stone-900 px-3 py-1 text-xs font-medium text-white hover:bg-stone-700"
            >
              Save config
            </button>
          </form>
          <p className="mt-2 text-[11px] text-stone-500">
            Prompt output guard: summary se bi gioi han theo summary max tokens.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => void handleCheckLlmHealth()}
              className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
            >
              Health check
            </button>
            <button
              type="button"
              onClick={() => void handleLlmTest()}
              className="rounded-md border border-stone-300 px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-100"
            >
              Test run
            </button>
          </div>
          {llmHealthMessage ? <p className="mt-2 text-xs text-stone-600">{llmHealthMessage}</p> : null}
          <textarea
            value={testPrompt}
            onChange={(event) => setTestPrompt(event.target.value)}
            className="mt-2 h-16 w-full rounded-md border border-stone-300 px-2 py-1 text-xs"
          />
          {testOutput ? (
            <pre className="mt-2 whitespace-pre-wrap rounded-md border border-stone-200 bg-stone-50 p-2 text-xs text-stone-700">
              {testOutput}
            </pre>
          ) : null}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-stone-200 p-3">
        <h3 className="text-sm font-semibold text-stone-800">Audit Logs</h3>
        <div className="mt-2 max-h-48 overflow-auto">
          {audit.map((item, idx) => (
            <p key={`${item.timestamp}-${idx}`} className="text-xs text-stone-700">
              [{item.timestamp}] {item.actor_role} {item.action} {item.status}
            </p>
          ))}
          {audit.length === 0 ? <p className="text-xs text-stone-500">No audit logs yet.</p> : null}
        </div>
      </div>
    </section>
  );
}
