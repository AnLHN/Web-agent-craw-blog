import { ChatMessage, SearchData } from "@/types/api";

type SearchResultPanelProps = {
  isLoading: boolean;
  errorMessage: string | null;
  result: SearchData | null;
  latestUserQuery: string;
  streamedAnswer?: string;
  processingStatus?: string;
  sessionMessages?: ChatMessage[];
};

function normalizeSummary(summary: string): string {
  return summary
    .replace(/\*\*/g, "")
    .replace(/^\s*#{1,6}\s+/gm, "")
    .replace(/^\s*(skip to content|skip to main content|jump to content)\b[\s:#\-|]*/i, "")
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
        className={`max-w-[85%] rounded-lg px-4 py-3 text-sm leading-7 shadow-sm ${
          isUser
            ? "bg-[#12312f] text-white shadow-[#12312f]/15"
            : "border border-[#dfe6dc] bg-white text-[#28342e]"
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
  streamedAnswer = "",
  processingStatus = "",
  sessionMessages = [],
}: SearchResultPanelProps) {
  const assistantContent = result ? normalizeSummary(result.summary) : "";
  const hasSessionMessages = sessionMessages.length > 0;
  const pendingUserVisible =
    Boolean(latestUserQuery) &&
    (isLoading || (!hasSessionMessages && !result && !errorMessage));
  const loadingAssistantText = streamedAnswer?.trim()
    ? normalizeSummary(streamedAnswer)
    : (processingStatus || "Đang xử lý...");

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-extrabold uppercase tracking-[0.14em] text-[#0f766e]">Cuộc trò chuyện tìm kiếm web</h2>
        {result ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-[#e6f3ef] px-3 py-1 text-xs font-bold text-[#115e59]">
              Provider: {result.provider_used}
            </span>
            <span className="rounded-full bg-[#fff4d6] px-3 py-1 text-xs font-bold text-[#92400e]">
              Confidence: {(result.confidence * 100).toFixed(0)}%
            </span>
          </div>
        ) : null}
      </div>

      <div className="space-y-3">
        {!hasSessionMessages && !latestUserQuery && !isLoading && !errorMessage && !result ? (
          <ChatBubble
            role="assistant"
            content="Xin chào. Bạn cứ nhập câu hỏi ở ô bên dưới, mình sẽ tìm nguồn web và trả lời theo dạng chat để bạn dễ theo dõi."
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

        {pendingUserVisible ? <ChatBubble role="user" content={latestUserQuery} compact /> : null}

        {isLoading ? <ChatBubble role="assistant" content={loadingAssistantText} compact /> : null}

        {errorMessage ? <ChatBubble role="assistant" content={errorMessage} compact /> : null}

        {!hasSessionMessages && result && !isLoading && !errorMessage ? (
          <ChatBubble role="assistant" content={assistantContent} />
        ) : null}
      </div>

      {result && !isLoading && !errorMessage ? (
        <>
          <details className="rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5">
            <summary className="cursor-pointer text-sm font-extrabold uppercase tracking-[0.14em] text-[#66736b]">
              Nguồn ({result.sources.length})
            </summary>
            <ul className="mt-3 space-y-3">
              {result.sources.map((source) => (
                <li key={source.url} className="rounded-lg border border-[#dfe6dc] bg-[#fbfcf7] p-3">
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-bold text-[#18201c] hover:text-[#0f766e]"
                  >
                    {source.title}
                  </a>
                  <p className="mt-1 text-sm leading-6 text-[#66736b]">{source.snippet}</p>
                  <p className="mt-2 font-mono text-xs text-[#0f766e]">{source.domain}</p>
                </li>
              ))}
            </ul>
          </details>

          <details className="rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5">
            <summary className="cursor-pointer text-sm font-extrabold uppercase tracking-[0.14em] text-[#66736b]">
              Pipeline attempts ({result.attempts.length})
            </summary>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-[#dfe6dc] text-[#66736b]">
                    <th className="py-2 pr-3">Provider</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Reason</th>
                    <th className="py-2 pr-3">Latency</th>
                    <th className="py-2 pr-3">Results</th>
                  </tr>
                </thead>
                <tbody>
                  {result.attempts.map((attempt, index) => (
                    <tr key={`${attempt.provider}-${index}`} className="border-b border-[#edf2ec]">
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
            <details className="rounded-lg border border-[#dfe6dc] bg-white p-4 shadow-sm shadow-[#12312f]/5">
              <summary className="cursor-pointer text-sm font-extrabold uppercase tracking-[0.14em] text-[#66736b]">
                Debug Trace
              </summary>

              <div className="mt-3 space-y-3 text-sm text-[#4d5a53]">
                <div>
                  <p className="font-bold text-[#18201c]">Query Analysis</p>
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
