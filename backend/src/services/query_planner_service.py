import time

from src.config.settings import Settings
from src.services.types import ProviderAttemptData, QueryPlanResult


class QueryPlannerService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _estimate_complexity(self, sub_queries: list[str]) -> str:
        count = len(sub_queries)
        if count <= 2:
            return "simple"
        if count == 3:
            return "medium"
        return "complex"

    def _budget_by_complexity(self, complexity: str) -> int:
        if complexity == "simple":
            return max(1, self.settings.planner_simple_budget)
        if complexity == "medium":
            return max(1, self.settings.planner_medium_budget)
        return max(1, self.settings.planner_complex_budget)

    def _priority_score(self, q: str) -> int:
        ql = q.lower()
        score = 0
        if "overview" in ql or "definition" in ql:
            score += 3
        if "architecture" in ql or "components" in ql:
            score += 2
        if "use case" in ql or "limitations" in ql:
            score += 1
        return score

    async def plan(self, sub_queries: list[str]) -> QueryPlanResult:
        started_at = time.perf_counter()
        complexity = self._estimate_complexity(sub_queries)
        budget = self._budget_by_complexity(complexity)
        ordered = sorted(sub_queries, key=self._priority_score, reverse=True)
        planned = ordered[: min(budget, len(ordered))]
        latency_ms = int((time.perf_counter() - started_at) * 1000)

        return QueryPlanResult(
            complexity=complexity,
            retrieval_budget=budget,
            planned_sub_queries=planned,
            attempt=ProviderAttemptData(
                provider="query_planner",
                status="success",
                reason=f"planned_{complexity}",
                latency_ms=latency_ms,
                result_count=len(planned),
            ),
        )
