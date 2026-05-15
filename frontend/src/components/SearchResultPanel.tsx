import { ChatMessage, SearchData } from "@/types/api";

type SearchResultPanelProps = {
  isLoading: boolean;
  errorMessage: string | null;
  result: SearchData | null;
  latestUserQuery: string;
  sessionMessages?: ChatMessage[];
};

function normalizeSummary(summary: string): string {
  return summary
    .replace(/\*\*/g, "")
    .replace(/^Duoi day la ban tom tat ngan gon va de doc ve .*?:\s*/i, "")
    .replace(/^Duoi day la tom tat .*?:\s*/i, "")
    .trim();
}

function ChatBubble(props: {
  role: "user" | "assistant";
  content: string;
  compact?: boolean;
}) {
  const isUser = props.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-7 shadow-sm ${
          isUser
            ? "bg-amber-500 text-stone-900"
            : "border border-stone-200 bg-stone-50 text-stone-800"
        } ${props.compact ? "leading-6" : ""}`}
      >
        <p className="whitespace-pre-line">{props.content}</p>
      </div>
    </div>
  );
}

export function SearchResultPanel({
  isLoading,
  errorMessage,
  result,
  latestUserQuery,
  sessionMessages = [],
}: SearchResultPanelProps) {
  const assistantContent = result ? normalizeSummary(result.summary) : "";
  const hasSessionMessages = sessionMessages.length > 0;

  return (
    <section className="rounded-2xl border border-stone-300 bg-white/90 p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-stone-900">Chat</h2>
        {result ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800">
              Provider: {result.provider_used}
            </span>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800">
              Confidence: {(result.confidence * 100).toFixed(0)}%
            </span>
          </div>
        ) : null}
      </div>

      <div className="space-y-3 rounded-xl border border-stone-200 bg-white p-3">
        {!hasSessionMessages && !latestUserQuery && !isLoading && !errorMessage && !result ? (
          <ChatBubble
            role="assistant"
            content="Xin chao. Ban cu nhap cau hoi o o tren, minh se tra ve cau tra loi theo kieu chat de doc de theo doi."
          />
        ) : null}

        {hasSessionMessages
          ? sessionMessages.map((message) => (
              <ChatBubble
                key={message.id}
                role={message.role === "assistant" ? "assistant" : "user"}
                content={message.content}
                compact={message.role === "user"}
              />
            ))
          : null}

        {!hasSessionMessages && latestUserQuery ? <ChatBubble role="user" content={latestUserQuery} compact /> : null}

        {isLoading ? (
          <ChatBubble
            role="assistant"
            content="Dang tim nguon va tong hop cau tra loi..."
            compact
          />
        ) : null}

        {errorMessage ? <ChatBubble role="assistant" content={errorMessage} compact /> : null}

        {!hasSessionMessages && result && !isLoading && !errorMessage ? (
          <ChatBubble role="assistant" content={assistantContent} />
        ) : null}
      </div>

      {result && !isLoading && !errorMessage ? (
        <>
      <details className="mt-6 rounded-xl border border-stone-200 bg-stone-50 p-3">
        <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide text-stone-600">
          Sources ({result.sources.length})
        </summary>
        <ul className="mt-3 space-y-3">
          {result.sources.map((source) => (
            <li key={source.url} className="rounded-xl border border-stone-200 bg-white p-3">
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
      </details>

      <details className="mt-4 rounded-xl border border-stone-200 bg-stone-50 p-3">
        <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide text-stone-600">
          Pipeline attempts ({result.attempts.length})
        </summary>
        <div className="mt-3 overflow-x-auto">
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
      </details>

      {result.query_analysis ? (
        <details className="mt-4 rounded-xl border border-stone-200 bg-stone-50 p-4">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide text-stone-600">
            Debug Trace
          </summary>

          <div className="mt-3 space-y-3 text-sm text-stone-700">
                  <div>
                    <p className="font-medium text-stone-900">Query Analysis</p>
                    <p>Original: {result.query_analysis.original_query}</p>
                    <p>Normalized: {result.query_analysis.normalized_query}</p>
                    <p>Intent: {result.query_analysis.intent}</p>
                    <p>Complexity: {result.query_analysis.complexity}</p>
                    <p>Retrieval budget: {result.query_analysis.retrieval_budget}</p>
                  </div>
          </div>
        </details>
      ) : null}
        </>
      ) : null}
    </section>
  );
}
