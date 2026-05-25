from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import respx
from fastapi.testclient import TestClient
from httpx import Response

from src.config.settings import Settings
from src.main import create_app


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def summarize(samples: list[float]) -> dict[str, float]:
    return {
        "count": float(len(samples)),
        "latency_avg_ms": statistics.fmean(samples) if samples else 0.0,
        "latency_p50_ms": percentile(samples, 50),
        "latency_p95_ms": percentile(samples, 95),
    }


def build_client(tmp_dir: Path) -> TestClient:
    settings = Settings(
        cors_origins=["http://localhost:3000"],
        searxng_base_url="https://searx.test",
        searxng_backup_base_urls="",
        tavily_key_store_path=str(tmp_dir / "tavily_keys.json"),
        chat_session_store_path=str(tmp_dir / "chat_sessions.json"),
        llm_runtime_store_path=str(tmp_dir / "llm_runtime.json"),
        audit_log_store_path=str(tmp_dir / "audit_logs.jsonl"),
        auth_store_path=str(tmp_dir / "auth_store.json"),
        auth_token_secret="benchmark-secret",
        quality_min_results=2,
        quality_min_unique_domains=1,
        request_timeout_seconds=5.0,
        llm_enabled=False,
    )
    return TestClient(create_app(settings_override=settings))


def time_request(client: TestClient, method: str, path: str, **kwargs: Any) -> tuple[float, int, dict[str, Any]]:
    started = time.perf_counter()
    response = client.request(method, path, **kwargs)
    latency_ms = (time.perf_counter() - started) * 1000.0
    return latency_ms, response.status_code, response.json()


def run_benchmark(rounds: int, output_dir: Path) -> dict[str, Any]:
    tmp_dir = output_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    client = build_client(tmp_dir)

    endpoint_samples: dict[str, list[float]] = {
        "health": [],
        "ready": [],
        "auth_register": [],
        "auth_login": [],
        "admin_users": [],
        "admin_audit_events": [],
        "admin_system_status": [],
        "search": [],
    }
    status_counts: dict[str, dict[str, int]] = {key: {} for key in endpoint_samples}

    admin_token = ""

    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.tavily.com/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {"title": "RAG overview", "url": "https://example.com/rag", "content": "RAG combines retrieval and generation.", "score": 0.9},
                        {"title": "RAG architecture", "url": "https://example.org/rag", "content": "RAG uses indexing, retrieval, and synthesis.", "score": 0.86},
                    ]
                },
            )
        )

        for i in range(rounds):
            for name, method, path, kwargs in [
                ("health", "GET", "/api/v1/health", {}),
                ("ready", "GET", "/api/v1/ready", {}),
                ("auth_register", "POST", "/api/v1/auth/register", {"json": {"email": f"bench{i}@example.com", "password": "super-secret-123"}}),
                ("auth_login", "POST", "/api/v1/auth/login", {"json": {"email": f"bench{i}@example.com", "password": "super-secret-123"}}),
                ("search", "POST", "/api/v1/search", {"json": {"query": "rag architecture", "top_k": 5}}),
            ]:
                latency_ms, status_code, payload = time_request(client, method, path, **kwargs)
                endpoint_samples[name].append(latency_ms)
                status_key = str(status_code)
                status_counts[name][status_key] = status_counts[name].get(status_key, 0) + 1
                if name == "auth_register" and i == 0 and payload.get("success"):
                    admin_token = payload["data"]["access_token"]

            admin_headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
            for name, method, path, kwargs in [
                ("admin_users", "GET", "/api/v1/admin/users", {"headers": admin_headers}),
                ("admin_audit_events", "GET", "/api/v1/admin/audit-events?limit=20", {"headers": admin_headers}),
                ("admin_system_status", "GET", "/api/v1/admin/system-status", {"headers": admin_headers}),
            ]:
                latency_ms, status_code, _ = time_request(client, method, path, **kwargs)
                endpoint_samples[name].append(latency_ms)
                status_key = str(status_code)
                status_counts[name][status_key] = status_counts[name].get(status_key, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rounds": rounds,
        "notes": {
            "search": "Tavily is mocked for deterministic local/CI runs.",
            "article_import": "Live fetch/translate/WordPress timings are excluded from this deterministic benchmark; use an environment-specific runbook for live providers.",
        },
        "endpoints": {
            name: {**summarize(samples), "status_counts": status_counts[name]}
            for name, samples in endpoint_samples.items()
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Benchmark Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Rounds: `{report['rounds']}`",
        "",
        "| Endpoint | Count | Avg ms | P50 ms | P95 ms | Status counts |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, data in report["endpoints"].items():
        lines.append(
            f"| {name} | {int(data['count'])} | {data['latency_avg_ms']:.2f} | {data['latency_p50_ms']:.2f} | {data['latency_p95_ms']:.2f} | `{json.dumps(data['status_counts'], sort_keys=True)}` |"
        )
    lines.extend(["", "## Notes"])
    for name, note in report.get("notes", {}).items():
        lines.append(f"- {name}: {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate production readiness benchmark artifacts")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-artifacts"))
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_benchmark(rounds=max(1, args.rounds), output_dir=output_dir)
    (output_dir / "benchmark-report.json").write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    write_markdown(report, output_dir / "benchmark-report.md")
    print(f"Wrote {output_dir / 'benchmark-report.json'}")
    print(f"Wrote {output_dir / 'benchmark-report.md'}")


if __name__ == "__main__":
    main()
