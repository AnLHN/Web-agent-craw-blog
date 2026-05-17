from pathlib import Path

import respx
from fastapi.testclient import TestClient
from httpx import Response

from src.config.settings import Settings
from src.main import create_app


def test_empty_llm_max_tokens_env_value_uses_default() -> None:
    settings = Settings(llm_max_tokens="")

    assert settings.llm_max_tokens is None


def build_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings_kwargs: dict[str, object] = {
        "cors_origins": ["http://localhost:3000"],
        "searxng_base_url": "https://searx.test",
        "searxng_backup_base_urls": "",
        "tavily_key_store_path": str(tmp_path / "tavily_keys.json"),
        "llm_runtime_store_path": str(tmp_path / "llm_runtime.json"),
        "result_cache_ttl_seconds": 300,
        "quality_min_results": 2,
        "quality_min_unique_domains": 1,
        "request_timeout_seconds": 5.0,
        "llm_enabled": False,
        "llm_base_url": "http://localhost:8007/v1",
        "llm_model": "local-vllm",
    }
    settings_kwargs.update(overrides)
    settings = Settings(**settings_kwargs)
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


def test_chat_session_history_and_replay(tmp_path: Path) -> None:
    client = build_client(tmp_path, chat_session_store_path=str(tmp_path / "chat_sessions.json"))

    created = client.post("/api/v1/chat/sessions", json={"title": "Research session"})
    assert created.status_code == 201
    session_id = created.json()["data"]["session"]["id"]

    added = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"role": "user", "content": "RAG la gi"},
    )
    assert added.status_code == 200
    assert added.json()["data"]["session"]["message_count"] == 1

    listed = client.get("/api/v1/chat/sessions")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    replayed = client.post(f"/api/v1/chat/sessions/{session_id}/replay")
    assert replayed.status_code == 200
    replayed_session = replayed.json()["data"]["session"]
    assert replayed_session["id"] != session_id
    assert replayed_session["message_count"] == 1
    assert replayed_session["metadata"]["replayed_from_session_id"] == session_id


def test_search_with_session_id_persists_user_and_assistant_messages(tmp_path: Path) -> None:
    client = build_client(tmp_path, chat_session_store_path=str(tmp_path / "chat_sessions.json"))
    created = client.post("/api/v1/chat/sessions", json={"title": "Search session"})
    session_id = created.json()["data"]["session"]["id"]

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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
        response = client.post(
            "/api/v1/search",
            json={"query": "latest ai news", "top_k": 5, "session_id": session_id},
        )

    assert response.status_code == 200
    session = client.get(f"/api/v1/chat/sessions/{session_id}").json()["data"]["session"]
    assert session["message_count"] == 2
    assert session["messages"][0]["role"] == "user"
    assert session["messages"][1]["role"] == "assistant"
    assert session["messages"][1]["metadata"]["provider_used"] in {"searxng_fallback", "tavily_low_quality", "tavily"}


def test_tavily_key_update_reset_and_metrics(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    created = client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-12345", "label": "Primary"},
    )
    key_id = created.json()["data"]["keys"][0]["id"]

    updated = client.patch(
        f"/api/v1/keys/tavily/{key_id}",
        json={"label": "Disabled primary", "status": "disabled"},
    )
    assert updated.status_code == 200
    key = updated.json()["data"]["keys"][0]
    assert key["label"] == "Disabled primary"
    assert key["status"] == "disabled"

    metrics = client.get("/api/v1/keys/tavily/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["data"]["total_keys"] == 1

    reset = client.post(f"/api/v1/keys/tavily/{key_id}/cooldown/reset")
    assert reset.status_code == 200
    assert reset.json()["data"]["keys"][0]["status"] == "active"


def test_llm_runtime_config_patch_and_health_and_test(tmp_path: Path) -> None:
    client = build_client(tmp_path, llm_enabled=True, llm_base_url="http://vllm.test/v1")

    with respx.mock(assert_all_called=True) as router:
        router.get("http://vllm.test/v1/models").mock(return_value=Response(200, json={"data": []}))
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": "health test ok"},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )
        )

        patched = client.patch(
            "/api/v1/llm/config",
            json={"base_url": "http://vllm.test/v1", "model": "gemma-local", "temperature": 0.4, "max_tokens": 512},
        )
        health = client.get("/api/v1/llm/health")
        dry_run = client.post("/api/v1/llm/test", json={"prompt": "hello"})

    assert patched.status_code == 200
    patched_payload = patched.json()
    assert patched_payload["success"] is True
    assert patched_payload["data"]["config"]["model"] == "gemma-local"
    assert patched_payload["data"]["config"]["max_tokens"] == 512

    assert health.status_code == 200
    assert health.json()["success"] is True
    assert health.json()["data"]["ok"] is True

    assert dry_run.status_code == 200
    assert dry_run.json()["success"] is True
    assert dry_run.json()["data"]["status"] == "success"


def test_ops_audit_logs_endpoint(tmp_path: Path) -> None:
    client = build_client(tmp_path, llm_enabled=True, llm_base_url="http://vllm.test/v1")

    with respx.mock(assert_all_called=False):
        client.patch(
            "/api/v1/llm/config",
            json={"model": "gemma-local"},
        )
        response = client.get("/api/v1/ops/audit/logs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] >= 1


def test_rbac_blocks_sensitive_endpoints_when_enabled(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        rbac_enabled=True,
        rbac_admin_token="secret-admin-token",
    )

    add_without_role = client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-12345", "label": "Primary"},
    )
    assert add_without_role.status_code == 403

    add_operator = client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-12345", "label": "Primary"},
        headers={"X-Role": "operator"},
    )
    assert add_operator.status_code == 201

    patch_llm_without_token = client.patch(
        "/api/v1/llm/config",
        json={"model": "abc"},
        headers={"X-Role": "admin"},
    )
    assert patch_llm_without_token.status_code == 403

    patch_llm_with_token = client.patch(
        "/api/v1/llm/config",
        json={"model": "abc"},
        headers={"X-Role": "admin", "X-Admin-Token": "secret-admin-token"},
    )
    assert patch_llm_with_token.status_code == 200


def test_feature_flags_disable_session_and_ops_endpoints(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        feature_session_history=False,
        feature_ops_dashboard=False,
        feature_llm_runtime_config=False,
    )

    session_create = client.post("/api/v1/chat/sessions", json={"title": "x"})
    assert session_create.status_code == 201
    assert session_create.json()["success"] is False
    assert session_create.json()["error"]["code"] == "FEATURE_DISABLED"

    ops_metrics = client.get("/api/v1/keys/tavily/metrics")
    assert ops_metrics.status_code == 200
    assert ops_metrics.json()["success"] is False
    assert ops_metrics.json()["error"]["code"] == "FEATURE_DISABLED"

    llm_config = client.get("/api/v1/llm/config")
    assert llm_config.status_code == 200
    assert llm_config.json()["success"] is False
    assert llm_config.json()["error"]["code"] == "FEATURE_DISABLED"


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


def test_search_fallback_to_searxng_when_all_tavily_keys_disabled(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    created = client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-12345", "label": "Primary"},
    )
    assert created.status_code == 201
    key_id = created.json()["data"]["keys"][0]["id"]

    disabled = client.patch(
        f"/api/v1/keys/tavily/{key_id}",
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200

    with respx.mock(assert_all_called=True) as router:
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {"title": "Alpha", "url": "https://example.com/a", "content": "Alpha content"},
                        {"title": "Beta", "url": "https://example.com/b", "content": "Beta content"},
                    ]
                },
            )
        )
        response = client.post("/api/v1/search", json={"query": "disabled tavily keys", "top_k": 5})

    assert searx_mock.called
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "searxng_fallback"


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
        first_call_count = searx_mock.call_count
        second = client.post("/api/v1/search", json={"query": "cache me", "top_k": 5})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_call_count >= 1
    assert searx_mock.call_count == first_call_count
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


def test_search_does_not_fallback_when_tavily_quality_is_sufficient(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-sufficient", "label": "Primary key"},
    )

    with respx.mock(assert_all_called=False) as router:
        tavily_mock = router.post("https://api.tavily.com/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Result 1",
                            "url": "https://source1.com/a",
                            "content": "Strong matching result one",
                            "score": 0.88,
                        },
                        {
                            "title": "Result 2",
                            "url": "https://source2.com/b",
                            "content": "Strong matching result two",
                            "score": 0.86,
                        },
                    ]
                },
            )
        )
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(200, json={"results": []})
        )

        response = client.post(
            "/api/v1/search", json={"query": "tavily priority success", "top_k": 5}
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "tavily"
    assert tavily_mock.called
    assert searx_mock.call_count == 0


def test_search_fallbacks_when_tavily_quality_below_threshold(tmp_path: Path) -> None:
    client = build_client(tmp_path, quality_min_results=3)
    client.post(
        "/api/v1/keys/tavily",
        json={"api_key": "tvly-test-key-low-quality", "label": "Primary key"},
    )

    with respx.mock(assert_all_called=True) as router:
        tavily_mock = router.post("https://api.tavily.com/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Only one result",
                            "url": "https://thin-source.com/a",
                            "content": "Insufficient quality response",
                            "score": 0.6,
                        }
                    ]
                },
            )
        )
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Fallback result",
                            "url": "https://fallback-source.org/1",
                            "content": "Fallback path executed",
                        },
                        {
                            "title": "Fallback result 2",
                            "url": "https://fallback-source.org/2",
                            "content": "Second fallback result",
                        },
                    ]
                },
            )
        )

        response = client.post(
            "/api/v1/search", json={"query": "force quality fallback", "top_k": 5}
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "searxng_fallback"
    assert tavily_mock.called
    assert searx_mock.called


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


def test_search_invalid_tavily_key_is_not_retried_many_times(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    client.post("/api/v1/keys/tavily", json={"api_key": "tvly-bad-key", "label": "bad-key"})

    with respx.mock(assert_all_called=True) as router:
        router.post("https://api.tavily.com/search").mock(
            return_value=Response(401, json={"error": "invalid api key"})
        )
        router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Fallback one",
                            "url": "https://fallback.test/one",
                            "content": "fallback",
                        },
                        {
                            "title": "Fallback two",
                            "url": "https://fallback.test/two",
                            "content": "fallback",
                        },
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "invalid key behavior", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["provider_used"] == "searxng_fallback"
    tavily_attempts = [item for item in payload["data"]["attempts"] if item["provider"] == "tavily"]
    assert 1 <= len(tavily_attempts) <= 2
    assert tavily_attempts[0]["reason"] == "http_401"


def test_search_uses_local_vllm_summary_when_enabled(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
    )

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
        llm_mock = router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "Tom tat tu local vLLM"
                            }
                        }
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "cache me", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["summary"] in {"Tom tat tu local vLLM", "Tom tat tu local vLLM."}
    llm_attempts = [item for item in payload["data"]["attempts"] if item["provider"] == "llm"]
    assert len(llm_attempts) == 1
    assert llm_attempts[0]["status"] == "success"
    assert searx_mock.called
    assert llm_mock.called


def test_search_stream_emits_status_token_and_done(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "Tom tat tu stream"}, "finish_reason": "stop"}]},
            )
        )

        with client.stream("POST", "/api/v1/search/stream", json={"query": "stream me", "top_k": 5}) as response:
            body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: status" in body
    assert "event: token" in body
    assert "Tom tat tu stream" in body
    assert "event: done" in body
    assert '"provider_used"' in body


def test_llm_summary_rewrites_to_length_budget_instead_of_cutting(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
        llm_summary_max_chars=120,
    )
    long_summary = (
        "ThinkPad la dong laptop doanh nghiep cua Lenovo voi do ben cao, ban phim tot, "
        "nhieu tuy chon bao mat va cau hinh cho cong viec van phong, ky thuat, lap trinh. "
        "Dong may nay co nhieu series nhu X, T, P va E cho cac nhu cau khac nhau."
    )
    compact_summary = "ThinkPad la laptop doanh nghiep cua Lenovo, noi bat ve do ben, ban phim tot va bao mat (lenovo.com)."

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Lenovo ThinkPad",
                            "url": "https://www.lenovo.com/thinkpad",
                            "content": "ThinkPad business laptops focus on performance, durability, keyboards and security.",
                        },
                        {
                            "title": "ThinkPad overview",
                            "url": "https://example.com/thinkpad",
                            "content": "ThinkPad includes X, T, P and E series for different users.",
                        },
                    ]
                },
            )
        )
        llm_mock = router.post("http://vllm.test/v1/chat/completions").mock(
            side_effect=[
                Response(200, json={"choices": [{"message": {"content": long_summary}, "finish_reason": "stop"}]}),
                Response(200, json={"choices": [{"message": {"content": compact_summary}, "finish_reason": "stop"}]}),
            ]
        )

        response = client.post("/api/v1/search", json={"query": "lenovo thinkpad", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["summary"] == compact_summary
    assert len(payload["data"]["summary"]) <= 120
    assert llm_mock.call_count == 2


def test_search_includes_query_planner_analysis_fields(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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

        response = client.post("/api/v1/search", json={"query": "ban biet kien truc rag hong", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    analysis = payload["data"]["query_analysis"]
    assert analysis is not None
    assert len(analysis["expanded_sub_queries"]) >= 1
    assert len(analysis["planned_sub_queries"]) >= 1
    assert analysis["complexity"] in {"simple", "medium", "complex"}
    assert analysis["retrieval_budget"] >= 1
    providers = [item["provider"] for item in payload["data"]["attempts"]]
    assert "query_analyst" in providers
    assert "query_planner" in providers


def test_search_runs_multi_query_retrieval_with_budget(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        planner_simple_budget=2,
        planner_medium_budget=3,
        planner_complex_budget=4,
        max_parallel_subquery=2,
        subquery_timeout_seconds=3.0,
    )

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
        response = client.post("/api/v1/search", json={"query": "rag architecture in machine learning", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["query_analysis"]["retrieval_budget"] >= 2
    assert searx_mock.call_count >= 2


def test_search_includes_evidence_merge_summary(tmp_path: Path) -> None:
    client = build_client(tmp_path, pipeline_mode="multi_agent_balanced")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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
                            "title": "Alpha duplicate",
                            "url": "https://example.com/a",
                            "content": "Alpha content duplicate",
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
        response = client.post("/api/v1/search", json={"query": "rag overview", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    qa = payload["data"]["query_analysis"]
    assert qa is not None
    assert qa["evidence_kept_count"] >= 1
    assert qa["evidence_dropped_count"] >= 1
    assert qa["evidence_dropped_reason_summary"] != ""
    providers = [item["provider"] for item in payload["data"]["attempts"]]
    assert "evidence_merge" in providers


def test_search_quality_gate_triggers_extra_round_when_coverage_low(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        pipeline_mode="multi_agent_balanced",
        quality_gate_min_coverage_sources=5,
        quality_gate_max_extra_rounds=1,
        max_sub_queries=4,
        planner_simple_budget=2,
        planner_complex_budget=2,
    )

    with respx.mock(assert_all_called=True) as router:
        searx_mock = router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "One",
                            "url": "https://only-source.test/1",
                            "content": "single source",
                        }
                    ]
                },
            )
        )
        response = client.post("/api/v1/search", json={"query": "rag basics", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    gate_attempts = [item for item in payload["data"]["attempts"] if item["provider"] == "quality_gate"]
    assert len(gate_attempts) >= 1
    assert gate_attempts[0]["reason"] == "coverage_low_trigger_extra_round"
    assert searx_mock.call_count >= 3


def test_search_includes_phase_f_telemetry_and_subquery_cache_hit(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        pipeline_mode="multi_agent_balanced",
        planner_complex_budget=2,
        planner_simple_budget=2,
        max_sub_queries=4,
    )

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
        first = client.post("/api/v1/search", json={"query": "rag architecture", "top_k": 5})
        first_count = searx_mock.call_count
        second = client.post("/api/v1/search", json={"query": "rag architecture followup", "top_k": 5})

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()

    first_qa = first_payload["data"]["query_analysis"]
    second_qa = second_payload["data"]["query_analysis"]

    assert first_qa["query_expansion_count"] >= 1
    assert 0.0 <= first_qa["subquery_cache_hit_rate"] <= 1.0
    assert first_qa["retrieval_coverage"] >= 0.0
    assert second_qa["subquery_cache_hit_rate"] >= 0.0
    assert searx_mock.call_count >= first_count


def test_llm_truncated_list_tail_is_cleaned(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "RAG co hai pha:\n1. Retrieval\n2."
                            },
                            "finish_reason": "stop",
                        }
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "rag la gi", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    summary = payload["data"]["summary"].strip()
    assert not summary.endswith("2.")
    assert not summary.endswith("*")
    assert "**" not in summary
    assert "Luu y" in summary or summary.endswith((".", "!", "?"))


def test_llm_preface_and_dangling_star_are_removed(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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
        router.post("http://vllm.test/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "Duoi day la ban tom tat ngan gon va de doc ve RAG:\n\n"
                                    "* RAG la kien truc ket hop retrieval va generation.\n"
                                    "* Tang tinh lien quan cua cau tra loi.\n"
                                    "*"
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ]
                },
            )
        )

        response = client.post("/api/v1/search", json={"query": "rag la gi", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    summary = payload["data"]["summary"].strip()
    assert not summary.lower().startswith("duoi day la")
    assert not summary.endswith("*")
    assert "**" not in summary
    assert summary.endswith((".", "!", "?"))


def test_query_analyst_llm_mode_generates_dynamic_subqueries(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        query_analyst_mode="llm",
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Company profile",
                            "url": "https://example.com/company",
                            "content": "Thong tin cong ty Nhat Tien Chung",
                        },
                        {
                            "title": "Leadership",
                            "url": "https://example.org/leadership",
                            "content": "Ban lanh dao va giam doc khu vuc",
                        },
                    ]
                },
            )
        )
        router.post("http://vllm.test/v1/chat/completions").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        '{"intent":"company_profile",'
                                        '"sub_queries":["nhat tien chung company profile",'
                                        '"nhat tien chung ceo",'
                                        '"nhat tien chung regional directors"],'
                                        '"analysis_reasoning_short":"Focus on profile and leadership"}'
                                    )
                                },
                                "finish_reason": "stop",
                            }
                        ]
                    },
                ),
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "Tom tat hop le."},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                ),
            ]
        )

        response = client.post(
            "/api/v1/search",
            json={
                "query": "cho toi biet ve cong ty Nhat Tien Chung va giam doc khu vuc",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    qa = payload["data"]["query_analysis"]
    assert qa is not None
    assert qa["intent"] == "company_profile"
    assert "nhat tien chung ceo" in qa["expanded_sub_queries"]
    analyst_attempts = [a for a in payload["data"]["attempts"] if a["provider"] == "query_analyst"]
    assert analyst_attempts
    assert analyst_attempts[0]["reason"] == "expanded_llm"


def test_query_analyst_llm_mode_fallbacks_to_rule_on_invalid_json(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        llm_enabled=True,
        query_analyst_mode="llm",
        llm_base_url="http://vllm.test/v1",
        llm_model="gemma-local",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://searx.test/search").mock(
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
        router.post("http://vllm.test/v1/chat/completions").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "not valid json"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                ),
                Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "Tom tat hop le."},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                ),
            ]
        )

        response = client.post("/api/v1/search", json={"query": "rag architecture", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    qa = payload["data"]["query_analysis"]
    assert qa is not None
    assert any("overview" in item.lower() for item in qa["expanded_sub_queries"])
    analyst_attempts = [a for a in payload["data"]["attempts"] if a["provider"] == "query_analyst"]
    assert analyst_attempts
    assert analyst_attempts[0]["reason"] == "expanded_rule_fallback"
