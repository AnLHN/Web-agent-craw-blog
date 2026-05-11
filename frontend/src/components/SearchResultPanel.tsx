import { SearchData } from "@/types/api";

type SearchResultPanelProps = {
  isLoading: boolean;
  errorMessage: string | null;
  result: SearchData | null;
};

export function SearchResultPanel({
  isLoading,
  errorMessage,
  result,
}: SearchResultPanelProps) {
  if (isLoading) {
    return (
      <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm">
        <p className="text-sm text-stone-600">Dang truy van va tong hop ket qua...</p>
      </section>
    );
  }

  if (errorMessage) {
    return (
      <section className="rounded-2xl border border-red-300 bg-red-50 p-5 shadow-sm">
        <p className="text-sm text-red-700">{errorMessage}</p>
      </section>
    );
  }

  if (!result) {
    return (
      <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm">
        <p className="text-sm text-stone-600">
          Nhap truy van de bat dau. He thong se thu Tavily truoc, chi fallback sang
          SearXNG khi can.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-stone-900">Summary</h2>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800">
          Provider: {result.provider_used}
        </span>
        <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800">
          Confidence: {(result.confidence * 100).toFixed(0)}%
        </span>
      </div>

      <p className="mt-3 leading-7 text-stone-700">{result.summary}</p>

      <h3 className="mt-6 text-sm font-semibold uppercase tracking-wide text-stone-500">
        Sources
      </h3>
      <ul className="mt-2 space-y-3">
        {result.sources.map((source) => (
          <li key={source.url} className="rounded-xl border border-stone-200 p-3">
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-stone-900 hover:underline"
            >
              {source.title}
            </a>
            <p className="mt-1 text-sm text-stone-600">{source.snippet}</p>
            <p className="mt-2 text-xs text-stone-500">{source.domain}</p>
          </li>
        ))}
      </ul>

      <h3 className="mt-6 text-sm font-semibold uppercase tracking-wide text-stone-500">
        Pipeline attempts
      </h3>
      <div className="mt-2 overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-stone-200 text-stone-600">
              <th className="py-2 pr-3">Provider</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3">Reason</th>
              <th className="py-2 pr-3">Latency</th>
              <th className="py-2 pr-3">Results</th>
            </tr>
          </thead>
          <tbody>
            {result.attempts.map((attempt, index) => (
              <tr key={`${attempt.provider}-${index}`} className="border-b border-stone-100">
                <td className="py-2 pr-3">{attempt.provider}</td>
                <td className="py-2 pr-3">{attempt.status}</td>
                <td className="py-2 pr-3">{attempt.reason}</td>
                <td className="py-2 pr-3">{attempt.latency_ms} ms</td>
                <td className="py-2 pr-3">{attempt.result_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
