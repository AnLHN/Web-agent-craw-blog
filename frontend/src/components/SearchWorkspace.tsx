"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  addTavilyKey,
  deleteTavilyKey,
  fetchTavilyKeys,
  searchWeb,
} from "@/services/apiClient";
import { SearchData, TavilyKeyInfo } from "@/types/api";

import { KeyManager } from "./KeyManager";
import { SearchResultPanel } from "./SearchResultPanel";

export function SearchWorkspace() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);

  const [result, setResult] = useState<SearchData | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  const [keys, setKeys] = useState<TavilyKeyInfo[]>([]);
  const [isLoadingKeys, setIsLoadingKeys] = useState(false);
  const [keysError, setKeysError] = useState<string | null>(null);

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

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadKeys();
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
      const response = await searchWeb(query.trim(), topK);
      if (!response.success || !response.data) {
        setResult(null);
        setSearchError(response.error?.message || "Search that bai.");
        return;
      }
      setResult(response.data);
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
        </section>

        <SearchResultPanel
          isLoading={isSearching}
          errorMessage={searchError}
          result={result}
        />
      </div>
    </main>
  );
}
