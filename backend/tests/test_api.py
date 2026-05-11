from pathlib import Path

import respx
from fastapi.testclient import TestClient
from httpx import Response

from src.config.settings import Settings
from src.main import create_app


def build_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        cors_origins=["http://localhost:3000"],
        searxng_base_url="https://searx.test",
        searxng_backup_base_urls="",
        tavily_key_store_path=str(tmp_path / "tavily_keys.json"),
        quality_min_results=2,
        quality_min_unique_domains=1,
        request_timeout_seconds=5.0,
    )
    app = create_app(settings_override=settings)
    return TestClient(app)


def test_health_endpoint(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "ok"


def test_validation_error_response_shape(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.post("/api/v1/search", json={"query": "x", "top_k": 5})

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_not_found_response_shape(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "HTTP_ERROR"


def test_search_fallback_to_searxng_when_no_tavily_keys(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Alpha",
                            "url": "https://example.com/a",
                            "content": "Alpha content",
                        },
                        {
                            "title": "Beta",
                            "url": "https://news.example.org/b",
                            "content": "Beta content",
                        },
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "latest ai news", "top_k": 5})

    assert searx_mock.called
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "searxng_fallback"
    assert len(payload["data"]["sources"]) == 2


def test_search_returns_structured_empty_result_when_no_provider_has_data(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
            return_value=Response(200, json={"results": []})
        )

        response = client.post("/api/v1/search", json={"query": "no results", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "none"
    assert payload["data"]["sources"] == []


def test_search_cache_hit_reuses_previous_result(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Alpha",
                            "url": "https://example.com/a",
                            "content": "Alpha content",
                        },
                        {
                            "title": "Beta",
                            "url": "https://news.example.org/b",
                            "content": "Beta content",
                        },
                    ]
                },
            )
        )

        first = client.post("/api/v1/search", json={"query": "cache me", "top_k": 5})
        second = client.post("/api/v1/search", json={"query": "cache me", "top_k": 5})

    assert first.status_code == 200
    assert second.status_code == 200
    assert searx_mock.call_count == 1
    second_payload = second.json()
    assert second_payload["success"] is True
    assert second_payload["data"]["attempts"][0]["provider"] == "cache"


def test_search_uses_tavily_first_when_keys_exist(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    add_key_resp = client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-12345", "label": "Primary key"},
    )
    assert add_key_resp.status_code == 201

    with respx.mock(assert_all_called=False) as router:
        tavily_mock = router.post("https://api.tavily.com/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Official Python",
                            "url": "https://python.org/docs",
                            "content": "Python official documentation",
                            "score": 0.92,
                        },
                        {
                            "title": "FastAPI docs",
                            "url": "https://fastapi.tiangolo.com/",
                            "content": "FastAPI tutorial",
                            "score": 0.89,
                        },
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "python framework", "top_k": 5})

    assert tavily_mock.called
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "tavily"


def test_search_fallback_to_searxng_on_tavily_rate_limit(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    client.post("/api/v1/keys/tavily", json={"api_key": "tvly-test-key-67890", "label": "backup"})

    with respx.mock(assert_all_called=True) as router:
        tavily_mock = router.post("https://api.tavily.com/search").mock(
            return_value=Response(429, json={"error": "rate limited"})
        )
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "SearX result",
                            "url": "https://example.net/result",
                            "content": "Fallback content",
                        },
                        {
                            "title": "SearX result 2",
                            "url": "https://example.edu/result2",
                            "content": "Fallback content 2",
                        },
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "fallback scenario", "top_k": 5})

    assert tavily_mock.called
    assert searx_mock.called
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "searxng_fallback"
    tavily_attempts = [item for item in payload["data"]["attempts"] if item["provider"] == "tavily"]
    assert len(tavily_attempts) >= 1
