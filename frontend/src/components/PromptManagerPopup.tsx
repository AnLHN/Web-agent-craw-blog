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
    summary_max_chars: 512,
    summary_system_prompt:
      "Ban la tro ly tong hop thong tin web chinh xac. Tra loi ngan gon, ro y, dung du lieu tu nguon. Khong bia them thong tin ngoai nguon; neu thieu du lieu thi noi ro.",
    updated_at: "",
  };
}

export function PromptManagerPanel() {
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
    const res = await patchLlmConfig({
      summary_system_prompt: (config.summary_system_prompt || "").trim(),
      summary_max_chars: config.summary_max_chars ?? 512,
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
    <section className="rounded-lg border border-stone-300 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">Prompt Manager</h2>
          <p className="mt-1 text-sm text-stone-600">Final summarizer prompt va target output length.</p>
        </div>
        {loading ? <span className="text-xs text-stone-500">Loading...</span> : null}
      </div>

      <form onSubmit={handleSave} className="mt-4 grid gap-3">
        <label className="text-xs font-medium text-stone-700">System Prompt</label>
        <textarea
          value={config.summary_system_prompt || ""}
          onChange={(event) =>
            setConfig((prev) => ({
              ...prev,
              summary_system_prompt: event.target.value,
            }))
          }
          className="min-h-64 w-full rounded-md border border-stone-300 px-3 py-2 text-sm leading-6 focus:border-amber-500 focus:outline-none"
        />
        <label className="text-xs font-medium text-stone-700">Target Output Length</label>
        <input
          type="number"
          min={120}
          max={4000}
          value={config.summary_max_chars ?? 512}
          onChange={(event) =>
            setConfig((prev) => ({
              ...prev,
              summary_max_chars: Number(event.target.value) || 512,
            }))
          }
          className="w-44 rounded-md border border-stone-300 px-2 py-1 text-sm focus:border-amber-500 focus:outline-none"
        />
        <p className="-mt-2 text-xs text-stone-500">
          LLM se tu viet/rewrite de vua do dai nay; backend chi cat tho nhu lop bao ve cuoi cung.
        </p>
        <button
          type="submit"
          disabled={saving}
          className="w-fit rounded-md bg-stone-900 px-4 py-2 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save Prompt"}
        </button>
        {message ? <p className="text-xs text-stone-700">{message}</p> : null}
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
    const res = await patchLlmConfig({
      summary_system_prompt: (config.summary_system_prompt || "").trim(),
      summary_max_chars: config.summary_max_chars ?? 512,
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
        className="fixed left-0 top-1/2 z-40 -translate-y-1/2 rounded-r-xl border border-l-0 border-stone-300 bg-amber-400 px-3 py-2 text-xs font-semibold text-stone-900 shadow-sm hover:bg-amber-300"
      >
        Prompt
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-stone-300 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-stone-900">Prompt Manager</h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-stone-300 px-2 py-1 text-xs text-stone-700 hover:bg-stone-100"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleSave} className="mt-3 grid gap-3">
              <label className="text-xs font-medium text-stone-700">
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
                className="h-48 w-full rounded-md border border-stone-300 px-3 py-2 text-xs"
              />
              <label className="text-xs font-medium text-stone-700">
                Target Output Length
              </label>
              <input
                type="number"
                min={120}
                max={4000}
                value={config.summary_max_chars ?? 512}
                onChange={(event) =>
                  setConfig((prev) => ({
                    ...prev,
                    summary_max_chars: Number(event.target.value) || 512,
                  }))
                }
                className="w-40 rounded-md border border-stone-300 px-2 py-1 text-sm"
              />
              <p className="-mt-2 text-xs text-stone-500">
                LLM se tu viet/rewrite de vua do dai nay; backend chi cat tho nhu lop bao ve cuoi cung.
              </p>
              <button
                type="submit"
                disabled={saving}
                className="w-fit rounded-md bg-stone-900 px-3 py-1 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-60"
              >
                {saving ? "Saving..." : "Save Prompt"}
              </button>
              {message ? <p className="text-xs text-stone-700">{message}</p> : null}
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
