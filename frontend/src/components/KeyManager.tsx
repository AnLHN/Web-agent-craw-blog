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
    <section className="rounded-lg border border-[#dfe6dc] bg-white p-5 shadow-sm shadow-[#12312f]/5">
      <h2 className="text-lg font-extrabold text-[#18201c]">Tavily Key Manager</h2>
      <p className="mt-1 text-sm leading-6 text-[#66736b]">
        Search luon uu tien Tavily truoc. Them key tai day de kich hoat xoay vong key.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 grid gap-3 md:grid-cols-[2fr_1fr_auto]">
        <input
          type="text"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="tvly-..."
          className="rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2 text-sm focus:border-[#0f766e] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#0f766e]/10"
        />
        <input
          type="text"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Label (optional)"
          className="rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] px-3 py-2 text-sm focus:border-[#0f766e] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#0f766e]/10"
        />
        <button
          type="submit"
          className="rounded-lg bg-[#0f766e] px-4 py-2 text-sm font-bold text-white shadow-lg shadow-[#0f766e]/20 transition hover:bg-[#115e59] disabled:opacity-50"
          disabled={isLoading}
        >
          {isLoading ? "Adding..." : "Add key"}
        </button>
      </form>

      {errorMessage ? <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{errorMessage}</p> : null}

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-[#dfe6dc] text-[#66736b]">
              <th className="py-2 pr-3 font-bold">Label</th>
              <th className="py-2 pr-3 font-bold">Masked key</th>
              <th className="py-2 pr-3 font-bold">Status</th>
              <th className="py-2 pr-3 font-bold">Last used</th>
              <th className="py-2 pr-3 font-bold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-3 text-[#66736b]">
                  Chua co key. He thong hien dang test bang luong fallback SearXNG.
                </td>
              </tr>
            ) : (
              keys.map((key) => (
                <tr key={key.id} className="border-b border-[#edf2ec] align-top">
                  <td className="py-2 pr-3 font-medium text-[#18201c]">{key.label}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{key.masked_key}</td>
                  <td className="py-2 pr-3">
                    <span className="rounded-full bg-[#e6f3ef] px-2 py-1 text-xs font-bold text-[#115e59]">
                      {key.status}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-[#66736b]">{prettyDate(key.last_used_at)}</td>
                  <td className="py-2 pr-3">
                    <button
                      type="button"
                      onClick={() => onDelete(key.id)}
                      className="rounded-md border border-[#dfe6dc] px-3 py-1 text-xs font-bold text-[#4d5a53] transition hover:border-red-300 hover:bg-red-50 hover:text-red-700"
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
