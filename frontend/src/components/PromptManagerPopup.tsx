"use client";

import { FormEvent, useEffect, useState } from "react";

import { fetchLlmConfig, patchLlmConfig } from "@/services/apiClient";
import { LlmRuntimeConfig } from "@/types/api";

function defaultPromptConfig(): LlmRuntimeConfig {
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

export function PromptManagerPanel({ authToken }: { authToken: string }) {
  const [config, setConfig] = useState<LlmRuntimeConfig>(defaultPromptConfig());
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      const res = await fetchLlmConfig();
      if (res.success && res.data) {
        setConfig({
          ...defaultPromptConfig(),
          ...res.data.config,
        });
      } else {
        setMessage(res.error?.message || "Khong tai duoc Prompt Manager.");
      }
      setLoading(false);
    })();
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const res = await patchLlmConfig(authToken, {
      summary_system_prompt: (config.summary_system_prompt || "").trim(),
      summary_max_tokens: config.summary_max_tokens ?? 512,
    });
    setSaving(false);
    if (!res.success || !res.data) {
      setMessage(res.error?.message || "Luu prompt that bai.");
      return;
    }
    setConfig({
      ...defaultPromptConfig(),
      ...res.data.config,
    });
    setMessage("Da luu Prompt Manager.");
  }

  return (
    <section className="rounded-lg border border-[#dfe6dc] bg-white p-5 shadow-sm shadow-[#12312f]/5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-extrabold text-[#18201c]">Prompt Manager</h2>
          <p className="mt-1 text-sm text-[#66736b]">Final summarizer prompt va target output length.</p>
        </div>
        {loading ? <span className="text-xs font-medium text-[#66736b]">Loading...</span> : null}
      </div>

      <form onSubmit={handleSave} className="mt-4 grid gap-3">
        <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">System Prompt</label>
        <textarea
          value={config.summary_system_prompt || ""}
          onChange={(event) =>
            setConfig((prev) => ({
              ...prev,
              summary_system_prompt: event.target.value,
            }))
          }
          className="min-h-64 w-full rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2 text-sm leading-6 focus:border-[#0f766e] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#0f766e]/10"
        />
        <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">Target Output Length (tokens)</label>
        <input
          type="number"
          min={32}
          max={16384}
          value={config.summary_max_tokens ?? 512}
          onChange={(event) =>
            setConfig((prev) => ({
              ...prev,
              summary_max_tokens: Number(event.target.value) || 512,
            }))
          }
          className="w-44 rounded-md border border-[#dfe6dc] bg-[#fbfcf7] px-2 py-1.5 text-sm focus:border-[#0f766e] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#0f766e]/10"
        />
        <p className="-mt-2 text-xs text-[#66736b]">
          Output length dung theo token budget cua OpenAI-compatible API.
        </p>
        <button
          type="submit"
          disabled={saving}
          className="w-fit rounded-lg bg-[#0f766e] px-4 py-2 text-xs font-bold text-white shadow-lg shadow-[#0f766e]/20 hover:bg-[#115e59] disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save Prompt"}
        </button>
        {message ? <p className="text-xs text-[#4d5a53]">{message}</p> : null}
      </form>
    </section>
  );
}

export function PromptManagerPopup() {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<LlmRuntimeConfig>(defaultPromptConfig());
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    void (async () => {
      const res = await fetchLlmConfig();
      if (res.success && res.data) {
        setConfig({
          ...defaultPromptConfig(),
          ...res.data.config,
        });
      }
    })();
  }, [open]);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const token = window.localStorage.getItem("web_agent_auth_token") || "";
    const res = await patchLlmConfig(token, {
      summary_system_prompt: (config.summary_system_prompt || "").trim(),
      summary_max_tokens: config.summary_max_tokens ?? 512,
    });
    setSaving(false);
    if (!res.success || !res.data) {
      setMessage(res.error?.message || "Luu prompt that bai.");
      return;
    }
    setConfig({
      ...defaultPromptConfig(),
      ...res.data.config,
    });
    setMessage("Da luu Prompt Manager.");
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed left-0 top-1/2 z-40 -translate-y-1/2 rounded-r-lg border border-l-0 border-[#dfe6dc] bg-[#f2b84b] px-3 py-2 text-xs font-bold text-[#12312f] shadow-sm hover:bg-[#ffd166]"
      >
        Prompt
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#12312f]/45 p-4 backdrop-blur-sm">
          <div className="surface-in w-full max-w-2xl rounded-lg border border-[#dfe6dc] bg-white p-5 shadow-2xl shadow-black/20">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-extrabold text-[#18201c]">Prompt Manager</h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-[#dfe6dc] px-2 py-1 text-xs font-bold text-[#12312f] hover:bg-[#e6f3ef]"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleSave} className="mt-3 grid gap-3">
              <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">
                System Prompt
              </label>
              <textarea
                value={config.summary_system_prompt || ""}
                onChange={(event) =>
                  setConfig((prev) => ({
                    ...prev,
                    summary_system_prompt: event.target.value,
                  }))
                }
                className="h-48 w-full rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2 text-xs focus:border-[#0f766e] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#0f766e]/10"
              />
              <label className="text-xs font-bold uppercase tracking-[0.12em] text-[#0f766e]">
                Target Output Length (tokens)
              </label>
              <input
                type="number"
                min={32}
                max={16384}
                value={config.summary_max_tokens ?? 512}
                onChange={(event) =>
                  setConfig((prev) => ({
                    ...prev,
                    summary_max_tokens: Number(event.target.value) || 512,
                  }))
                }
                className="w-40 rounded-md border border-[#dfe6dc] bg-[#fbfcf7] px-2 py-1.5 text-sm focus:border-[#0f766e] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#0f766e]/10"
              />
              <p className="-mt-2 text-xs text-[#66736b]">
                Output length dung theo token budget cua OpenAI-compatible API.
              </p>
              <button
                type="submit"
                disabled={saving}
                className="w-fit rounded-md bg-[#0f766e] px-3 py-1.5 text-xs font-bold text-white shadow-sm shadow-[#0f766e]/20 hover:bg-[#115e59] disabled:opacity-60"
              >
                {saving ? "Saving..." : "Save Prompt"}
              </button>
              {message ? <p className="text-xs text-[#4d5a53]">{message}</p> : null}
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
