from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

import respx
from fastapi.testclient import TestClient
from httpx import Response

from src.config.settings import Settings
from src.main import create_app


def build_client(tmp_dir: Path, pipeline_mode: str) -> TestClient:
    settings = Settings(
        cors_origins=["http://localhost:3000"],
        searxng_base_url="https://searx.test",
        searxng_backup_base_urls="",
        tavily_key_store_path=str(tmp_dir / f"tavily_keys_{pipeline_mode}.json"),
        quality_min_results=2,
        quality_min_unique_domains=1,
        request_timeout_seconds=5.0,
        llm_enabled=False,
        pipeline_mode=pipeline_mode,
        max_sub_queries=4,
        planner_simple_budget=2,
        planner_medium_budget=3,
        planner_complex_budget=4,
        max_parallel_subquery=2,
    )
    app = create_app(settings_override=settings)
    return TestClient(app)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def run_mode(mode: str, rounds: int, queries: list[str]) -> dict[str, float]:
    tmp_dir = Path(".benchmark_tmp")
    tmp_dir.mkdir(exist_ok=True)
    client = build_client(tmp_dir=tmp_dir, pipeline_mode=mode)

    latencies_ms: list[float] = []
    fallback_count = 0
    coverage_values: list[float] = []
    cache_hit_rate_values: list[float] = []

    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.tavily.com/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "RAG overview",
                            "url": "https://example.com/rag-overview",
                            "content": "Retrieval-augmented generation combines retrieval and generation.",
                            "score": 0.92,
                        },
                        {
                            "title": "RAG architecture",
                            "url": "https://example.org/rag-architecture",
                            "content": "Typical RAG includes indexing, retrieval, and response synthesis.",
                            "score": 0.88,
                        },
                    ]
                },
            )
        )
        router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Fallback source",
                            "url": "https://fallback.test/rag",
                            "content": "Fallback source content.",
                        }
                    ]
                },
            )
        )

        for _ in range(rounds):
            for query in queries:
                started_at = time.perf_counter()
                response = client.post("/api/v1/search", json={"query": query, "top_k": 5})
                latency_ms = (time.perf_counter() - started_at) * 1000.0
                latencies_ms.append(latency_ms)

                if response.status_code != 200:
                    continue
                payload = response.json()
                data = payload.get("data") or {}
                provider_used = data.get("provider_used", "")
                if provider_used == "searxng_fallback":
                    fallback_count += 1

                qa = data.get("query_analysis") or {}
                coverage = float(qa.get("retrieval_coverage", 0.0) or 0.0)
                cache_hit_rate = float(qa.get("subquery_cache_hit_rate", 0.0) or 0.0)
                coverage_values.append(coverage)
                cache_hit_rate_values.append(cache_hit_rate)

    total = len(latencies_ms)
    return {
        "requests": float(total),
        "latency_p50_ms": percentile(latencies_ms, 50),
        "latency_p95_ms": percentile(latencies_ms, 95),
        "latency_avg_ms": statistics.fmean(latencies_ms) if latencies_ms else 0.0,
        "fallback_rate": (fallback_count / total) if total else 0.0,
        "avg_retrieval_coverage": statistics.fmean(coverage_values) if coverage_values else 0.0,
        "avg_subquery_cache_hit_rate": statistics.fmean(cache_hit_rate_values) if cache_hit_rate_values else 0.0,
    }


def print_report(classic: dict[str, float], multi: dict[str, float]) -> None:
    print("\n=== A/B Benchmark Report ===")
    print(f"{'Metric':40} {'classic':>14} {'multi_agent_balanced':>24}")
    print("-" * 82)
    keys = [
        "requests",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_avg_ms",
        "fallback_rate",
        "avg_retrieval_coverage",
        "avg_subquery_cache_hit_rate",
    ]
    for key in keys:
        print(f"{key:40} {classic[key]:14.4f} {multi[key]:24.4f}")

    print("\n=== Delta (multi vs classic) ===")
    for key in keys[1:]:
        base = classic[key]
        cur = multi[key]
        if base == 0:
            print(f"{key:40} n/a")
            continue
        delta_pct = ((cur - base) / base) * 100.0
        print(f"{key:40} {delta_pct:+.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B benchmark for classic vs multi-agent pipeline")
    parser.add_argument("--rounds", type=int, default=5, help="Number of loops over the query set")
    args = parser.parse_args()

    queries = [
        "rag architecture",
        "what is retrieval augmented generation",
        "rag vs fine tuning",
        "vector database in rag",
        "when to use searxng fallback",
    ]

    classic = run_mode(mode="classic", rounds=max(1, args.rounds), queries=queries)
    multi = run_mode(mode="multi_agent_balanced", rounds=max(1, args.rounds), queries=queries)
    print_report(classic=classic, multi=multi)


if __name__ == "__main__":
    main()
