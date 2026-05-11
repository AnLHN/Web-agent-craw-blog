"use client";

import { FormEvent, useState } from "react";

import { TavilyKeyInfo } from "@/types/api";
import { prettyDate } from "@/utils/date";

type KeyManagerProps = {
  keys: TavilyKeyInfo[];
  isLoading: boolean;
  errorMessage: string | null;
  onAdd: (apiKey: string, label: string) => Promise<void>;
  onDelete: (keyId: string) => Promise<void>;
};

export function KeyManager({
  keys,
  isLoading,
  errorMessage,
  onAdd,
  onDelete,
}: KeyManagerProps) {
  const [apiKey, setApiKey] = useState("");
  const [label, setLabel] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!apiKey.trim()) {
      return;
    }

    await onAdd(apiKey.trim(), label.trim());
    setApiKey("");
    setLabel("");
  }

  return (
    <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm backdrop-blur">
      <h2 className="text-lg font-semibold text-stone-900">Tavily Key Manager</h2>
      <p className="mt-1 text-sm text-stone-600">
        Search luon uu tien Tavily truoc. Them key tai day de kich hoat xoay vong key.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 grid gap-3 md:grid-cols-[2fr_1fr_auto]">
        <input
          type="text"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="tvly-..."
          className="rounded-xl border border-stone-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
        />
        <input
          type="text"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Label (optional)"
          className="rounded-xl border border-stone-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-xl bg-stone-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-stone-700 disabled:opacity-50"
          disabled={isLoading}
        >
          {isLoading ? "Adding..." : "Add key"}
        </button>
      </form>

      {errorMessage ? <p className="mt-3 text-sm text-red-700">{errorMessage}</p> : null}

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-stone-200 text-stone-600">
              <th className="py-2 pr-3 font-medium">Label</th>
              <th className="py-2 pr-3 font-medium">Masked key</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Last used</th>
              <th className="py-2 pr-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-3 text-stone-500">
                  Chua co key. He thong hien dang test bang luong fallback SearXNG.
                </td>
              </tr>
            ) : (
              keys.map((key) => (
                <tr key={key.id} className="border-b border-stone-100 align-top">
                  <td className="py-2 pr-3 text-stone-900">{key.label}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{key.masked_key}</td>
                  <td className="py-2 pr-3">
                    <span className="rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-700">
                      {key.status}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-stone-600">{prettyDate(key.last_used_at)}</td>
                  <td className="py-2 pr-3">
                    <button
                      type="button"
                      onClick={() => onDelete(key.id)}
                      className="rounded-md border border-stone-300 px-3 py-1 text-xs text-stone-700 transition hover:border-red-400 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
