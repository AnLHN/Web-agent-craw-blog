import json
from pathlib import Path

import respx
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from src.config.settings import Settings
from src.main import create_app
from src.models.article_schemas import ArticleAsset, ArticleBlock, ArticleBlockType
from src.services.article_asset_service import ArticleAssetService
from src.services.article_extractor_service import ArticleExtractorService
from src.services.article_prompt_service import ArticlePromptService
from src.services.wordpress_automation_service import WordPressAutomationResult
from src.services.wordpress_draft_builder import WordPressDraftBuilder


def build_client(tmp_path: Path, **overrides: object) -> TestClient:
    settings_kwargs: dict[str, object] = {
        "cors_origins": ["http://localhost:3000"],
        "searxng_base_url": "https://searx.test",
        "searxng_backup_base_urls": "",
        "tavily_key_store_path": str(tmp_path / "tavily_keys.json"),
        "chat_session_store_path": str(tmp_path / "chat_sessions.json"),
        "llm_runtime_store_path": str(tmp_path / "llm_runtime.json"),
        "audit_log_store_path": str(tmp_path / "audit_logs.jsonl"),
        "article_import_storage_path": str(tmp_path / "article_imports"),
        "auth_store_path": str(tmp_path / "auth_store.json"),
        "auth_store_backend": "local",
        "database_url": "",
        "session_store_backend": "local",
        "auth_token_secret": "test-secret",
        "ninerouter_api_key": "",
        "ninerouter_base_url": "",
        "llm_enabled": False,
    }
    settings_kwargs.update(overrides)
    settings = Settings(**settings_kwargs)
    app = create_app(settings_override=settings)
    return TestClient(app)


ARTICLE_FIXTURE = """
<!doctype html>
<html>
  <head>
    <title>Fallback title</title>
    <meta property="og:title" content="Source Agent Tools">
    <meta name="author" content="Jane Doe">
    <meta property="article:published_time" content="2026-05-01T09:30:00Z">
  </head>
  <body>
    <header>Site header</header>
    <article>
      <h1>Source Agent Tools</h1>
      <p>Agents can call <a href="/docs/tools">tools</a> safely with <code>q_bmm_quantizer</code>.</p>
      <figure>
        <img src="/images/architecture.png" alt="Architecture diagram">
        <figcaption>System architecture</figcaption>
      </figure>
      <pre><code class="language-bash">npm install example-package</code></pre>
      <blockquote>Keep claims grounded.</blockquote>
      <ul><li>Read the <a href="/docs/quantization">quantization guide</a></li><li>Preserve inline API names</li></ul>
      <ol><li>Calibrate model</li><li>Export checkpoint</li></ol>
      <table><tr><td>Model</td><td>Gemini</td></tr></table>
    </article>
    <footer>Footer</footer>
  </body>
</html>
"""


class FakeWordPressAutomationService:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.pasted_title: str | None = None
        self.pasted_content: str | None = None

    async def dry_run(self) -> WordPressAutomationResult:
        if not self.ok:
            return WordPressAutomationResult(ok=False, status="failed", message="fake failure")
        return WordPressAutomationResult(
            ok=True,
            status="ready",
            message="fake ready",
            page_url="https://wordpress.example.com/wp-admin/post-new.php",
        )

    async def paste_draft(self, title: str, content: str) -> WordPressAutomationResult:
        self.pasted_title = title
        self.pasted_content = content
        if not self.ok:
            return WordPressAutomationResult(ok=False, status="failed", message="fake paste failure")
        return WordPressAutomationResult(
            ok=True,
            status="pasted",
            message="fake pasted",
            page_url="https://wordpress.example.com/wp-admin/post-new.php",
        )


def create_import_fixture(client: TestClient) -> dict:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/articles/agent-tools").mock(
            return_value=Response(200, html=ARTICLE_FIXTURE, headers={"content-type": "text/html; charset=utf-8"})
        )
        router.get("https://example.com/images/architecture.png").mock(
            return_value=Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
        )
        response = client.post("/api/v1/articles/import", json={"url": "https://example.com/articles/agent-tools"})
    assert response.status_code == 202
    return response.json()["data"]["run"]


def test_article_import_rbac_requires_bearer_when_enabled(tmp_path: Path) -> None:
    client = build_client(tmp_path, rbac_enabled=True)
    admin = client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "super-secret-123"})
    token = admin.json()["data"]["access_token"]

    denied = client.post("/api/v1/articles/import", json={"url": "https://example.com/articles/agent-tools"})
    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/articles/agent-tools").mock(
            return_value=Response(200, html=ARTICLE_FIXTURE, headers={"content-type": "text/html; charset=utf-8"})
        )
        router.get("https://example.com/images/architecture.png").mock(
            return_value=Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
        )
        allowed = client.post(
            "/api/v1/articles/import",
            json={"url": "https://example.com/articles/agent-tools"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 202
    assert allowed.json()["success"] is True


def test_article_import_create_fetches_and_extracts_phase_b_contract(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/articles/agent-tools").mock(
            return_value=Response(200, html=ARTICLE_FIXTURE, headers={"content-type": "text/html; charset=utf-8"})
        )
        router.get("https://example.com/images/architecture.png").mock(
            return_value=Response(
                200,
                content=b"fake-png-bytes",
                headers={"content-type": "image/png", "content-length": "14"},
            )
        )
        response = client.post(
            "/api/v1/articles/import",
            json={
                "url": "https://example.com/articles/agent-tools",
                "mode": "draft",
                "target_language": "vi",
                "glossary_key": "ai-default",
                "wordpress_target_url": "https://wordpress.example.com/wp-admin/post-new.php",
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is True
    run = payload["data"]["run"]
    assert run["id"].startswith("air_")
    assert run["status"] == "draft_ready"
    assert run["mode"] == "draft"
    assert run["target_language"] == "vi"
    assert run["source"]["url"] == "https://example.com/articles/agent-tools"
    assert run["source"]["domain"] == "example.com"
    assert run["source"]["title"] == "Source Agent Tools"
    assert run["source"]["author"] == "Jane Doe"
    assert run["storage"]["raw_snapshot_path"].endswith("raw.html")
    assert run["storage"]["extracted_json_path"].endswith("extracted.json")
    assert run["storage"]["draft_json_path"].endswith("draft.json")
    assert run["storage"]["assets_dir"].endswith("assets")
    assert run["draft"]["source_attribution"]["url"] == "https://example.com/articles/agent-tools"
    assert run["draft"]["source_attribution"]["title"] == "Source Agent Tools"
    assert run["metadata"]["contract_version"] == "article_import.phase_h"
    assert run["metadata"]["glossary_key"] == "ai-default"
    assert run["metadata"]["llm_provider"] == "9router_openai"
    assert run["metadata"]["translation_status"] == "skipped_no_provider"
    assert run["metadata"]["draft_status"] == "ready"
    assert run["metadata"]["block_count"] >= 5
    assert run["metadata"]["asset_count"] == 1
    assert run["metadata"]["asset_downloaded_count"] == 1
    assert run["metadata"]["asset_failed_count"] == 0
    assert run["metadata"]["asset_skipped_count"] == 0
    block_types = [block["block_type"] for block in run["blocks"]]
    assert block_types[:7] == ["heading", "paragraph", "image", "code", "quote", "list", "list"]
    assert run["blocks"][1]["metadata"]["links"] == [{"id": "LINK_1", "text": "tools", "href": "https://example.com/docs/tools"}]
    assert "[LINK_1:tools]" in run["blocks"][1]["source_text"]
    assert "q_bmm_quantizer" in run["blocks"][1]["source_text"]
    assert run["blocks"][2]["metadata"]["source_url"] == "https://example.com/images/architecture.png"
    assert run["blocks"][3]["source_text"] == "npm install example-package"
    assert run["blocks"][3]["language_hint"] == "bash"
    assert run["assets"][0]["source_url"] == "https://example.com/images/architecture.png"
    assert run["assets"][0]["caption"] == "System architecture"
    assert run["assets"][0]["download_status"] == "downloaded"
    assert run["assets"][0]["mime_type"] == "image/png"
    assert run["assets"][0]["checksum"] is not None
    assert Path(run["assets"][0]["local_path"]).exists()
    assert run["draft"]["content_format"] == "html"
    assert "<h2>Source Agent Tools</h2>" in run["draft"]["content"]
    assert "<figure><img" in run["draft"]["content"]
    assert "<pre><code class=\"language-bash\">npm install example-package</code></pre>" in run["draft"]["content"]
    assert '<ul><li>Read the <a href="https://example.com/docs/quantization" rel="nofollow noopener">quantization guide</a></li><li>Preserve inline API names</li></ul>' in run["draft"]["content"]
    assert "<ol><li>Calibrate model</li><li>Export checkpoint</li></ol>" in run["draft"]["content"]
    assert "Source: <a href=\"https://example.com/articles/agent-tools\"" in run["draft"]["content"]
    assert Path(run["storage"]["raw_snapshot_path"]).exists()
    assert Path(run["storage"]["extracted_json_path"]).exists()
    assert Path(run["storage"]["draft_json_path"]).exists()
    assert (Path(run["storage"]["run_dir"]) / "run.json").exists()


def test_article_import_feature_flag_disables_contract_endpoint(tmp_path: Path) -> None:
    client = build_client(tmp_path, feature_article_import=False)

    response = client.post("/api/v1/articles/import", json={"url": "https://example.com/a"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FEATURE_DISABLED"


def test_article_import_translate_endpoint_reruns_existing_run(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    run = create_import_fixture(client)

    response = client.post(f"/api/v1/articles/import/{run['id']}/translate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["run"]["metadata"]["translation_status"] == "skipped_no_provider"
    assert payload["data"]["run"]["metadata"]["draft_status"] == "ready"


def test_article_import_fetch_failure_returns_structured_error(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/missing").mock(return_value=Response(404, text="missing"))
        response = client.post("/api/v1/articles/import", json={"url": "https://example.com/missing"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "ARTICLE_FETCH_FAILED"
    assert payload["data"]["run"]["status"] == "failed"


def test_article_import_blocks_localhost_url_by_default(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.post("/api/v1/articles/import", json={"url": "http://localhost:8080/private"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "ARTICLE_URL_BLOCKED"
    assert payload["error"]["details"]["reason"] == "localhost_blocked"


def test_article_import_blocks_private_ip_url_by_default(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.post("/api/v1/articles/import", json={"url": "http://127.0.0.1:8080/private"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "ARTICLE_URL_BLOCKED"
    assert payload["error"]["details"]["reason"] == "private_ip_blocked"


def test_article_import_settings_accept_9router_env_names(monkeypatch) -> None:
    monkeypatch.setenv("APP_9ROUTER_API_KEY", "router-key")
    monkeypatch.setenv("APP_9ROUTER_BASE_URL", "https://router.example/v1")

    settings = Settings()

    assert settings.ninerouter_api_key == "router-key"
    assert settings.ninerouter_base_url == "https://router.example/v1"


def test_article_import_llm_health_reports_missing_9router_config(tmp_path: Path) -> None:
    client = build_client(tmp_path)

    response = client.post("/api/v1/articles/import/llm/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "ARTICLE_LLM_HEALTH_FAILED"
    assert payload["data"]["configured"] is False
    assert payload["data"]["status"] == "not_configured"


def test_article_import_llm_health_checks_9router_openai(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        ninerouter_base_url="https://router.example/v1",
        ninerouter_api_key="test-key",
        article_openai_model="gpt-5.5-test",
    )

    with respx.mock(assert_all_called=True) as router:
        llm_mock = router.post("https://router.example/v1/chat/completions").mock(
            return_value=Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        )
        response = client.post("/api/v1/articles/import/llm/health")

    assert llm_mock.called
    assert llm_mock.calls[0].request.headers["authorization"] == "Bearer test-key"
    llm_request = json.loads(llm_mock.calls[0].request.content)
    assert llm_request["stream"] is False
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["ok"] is True
    assert payload["data"]["configured"] is True
    assert payload["data"]["status"] == "ready"
    assert payload["data"]["model"] == "gpt-5.5-test"


def test_article_prompt_service_keeps_article_namespace_isolated() -> None:
    service = ArticlePromptService()
    prompt_keys = [prompt.prompt_key for prompt in service.active_prompts()]

    assert "article.translate" in prompt_keys
    assert "article.metadata" in prompt_keys
    assert "article.term_review" in prompt_keys
    assert "search.summary" not in prompt_keys


def test_article_block_contract_supports_code_and_image_separation() -> None:
    code_block = ArticleBlock(
        id="b1",
        order_index=0,
        block_type=ArticleBlockType.CODE,
        source_text="npm install example",
        language_hint="bash",
    )
    image_block = ArticleBlock(
        id="b2",
        order_index=1,
        block_type=ArticleBlockType.IMAGE,
        asset_id="asset_1",
        metadata={"alt_text": "Architecture diagram"},
    )

    assert code_block.block_type == ArticleBlockType.CODE
    assert code_block.language_hint == "bash"
    assert image_block.block_type == ArticleBlockType.IMAGE
    assert image_block.asset_id == "asset_1"


def test_article_extractor_preserves_structured_blocks_from_fixture() -> None:
    extractor = ArticleExtractorService()

    result = extractor.extract(ARTICLE_FIXTURE, "https://example.com/articles/agent-tools")

    assert result.source.title == "Source Agent Tools"
    assert result.source.author == "Jane Doe"
    assert result.source.published_at is not None
    assert [block.block_type for block in result.blocks] == [
        ArticleBlockType.HEADING,
        ArticleBlockType.PARAGRAPH,
        ArticleBlockType.IMAGE,
        ArticleBlockType.CODE,
        ArticleBlockType.QUOTE,
        ArticleBlockType.LIST,
        ArticleBlockType.LIST,
        ArticleBlockType.TABLE,
    ]
    assert result.blocks[2].asset_id == "asset_1"
    assert result.assets[0].source_url == "https://example.com/images/architecture.png"
    assert result.assets[0].alt_text == "Architecture diagram"
    assert result.blocks[3].source_text == "npm install example-package"
    assert result.blocks[3].language_hint == "bash"


def test_article_import_translates_with_9router_openai_when_configured(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        ninerouter_base_url="https://router.example/v1",
        ninerouter_api_key="test-key",
        article_openai_model="gpt-5.5-test",
        article_translation_max_batches_per_run=8,
    )

    llm_payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"title_vi":"Cong cu Agent",'
                        '"excerpt_vi":"Tom tat ngan ve cong cu agent.",'
                        '"slug":"cong-cu-agent",'
                        '"tags":["AI","Agent"],'
                        '"categories":["Cong nghe"],'
                        '"translated_blocks":['
                        '{"block_id":"b1","type":"heading","text_vi":"Cong cu Agent"},'
                        '{"block_id":"b2","type":"paragraph","text_vi":"Agent co the goi [LINK_1:cong cu] an toan voi q_bmm_quantizer."},'
                        '{"block_id":"b4","type":"code","text_vi":"npm install example-package"},'
                        '{"block_id":"b5","type":"quote","text_vi":"Giu cac claim bam sat nguon."},'
                        '{"block_id":"b6","type":"list","text_vi":"Doc [LINK_1:huong dan luong tu hoa]\\nGiu nguyen ten API inline"},'
                        '{"block_id":"b7","type":"list","text_vi":"Hieu chinh model\\nXuat checkpoint"},'
                        '{"block_id":"b8","type":"table","text_vi":"Model | Gemini"}'
                        '],'
                        '"warnings":[]}'
                    )
                },
                "finish_reason": "stop",
            }
        ]
    }

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/articles/agent-tools").mock(
            return_value=Response(200, html=ARTICLE_FIXTURE, headers={"content-type": "text/html; charset=utf-8"})
        )
        router.get("https://example.com/images/architecture.png").mock(
            return_value=Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
        )
        llm_mock = router.post("https://router.example/v1/chat/completions").mock(
            return_value=Response(200, json=llm_payload)
        )
        response = client.post("/api/v1/articles/import", json={"url": "https://example.com/articles/agent-tools"})

    assert llm_mock.called
    assert llm_mock.call_count == 2
    assert llm_mock.calls[0].request.headers["authorization"] == "Bearer test-key"
    llm_request = json.loads(llm_mock.calls[0].request.content)
    llm_user_payload = json.loads(llm_request["messages"][1]["content"])
    assert llm_request["stream"] is False
    assert [block["id"] for block in llm_user_payload["blocks"]] == ["b1", "b2", "b4", "b5"]
    second_llm_request = json.loads(llm_mock.calls[1].request.content)
    second_llm_user_payload = json.loads(second_llm_request["messages"][1]["content"])
    assert [block["id"] for block in second_llm_user_payload["blocks"]] == ["b6", "b7", "b8", "cap::asset_1"]
    payload = response.json()
    run = payload["data"]["run"]
    assert response.status_code == 202
    assert payload["success"] is True
    assert run["status"] == "draft_ready"
    assert run["metadata"]["translation_status"] == "translated"
    assert run["metadata"]["draft_status"] == "ready"
    assert run["draft"]["title"] == "Cong cu Agent"
    assert run["draft"]["slug"] == "cong-cu-agent"
    assert "<h2>Cong cu Agent</h2>" in run["draft"]["content"]
    assert '<p>Agent co the goi <a href="https://example.com/docs/tools" rel="nofollow noopener">cong cu</a> an toan voi q_bmm_quantizer.</p>' in run["draft"]["content"]
    assert '<ul><li>Doc <a href="https://example.com/docs/quantization" rel="nofollow noopener">huong dan luong tu hoa</a></li><li>Giu nguyen ten API inline</li></ul>' in run["draft"]["content"]
    assert "<ol><li>Hieu chinh model</li><li>Xuat checkpoint</li></ol>" in run["draft"]["content"]
    assert run["blocks"][1]["translated_text"] == "Agent co the goi [LINK_1:cong cu] an toan voi q_bmm_quantizer."
    assert run["blocks"][3]["block_type"] == "code"
    assert run["blocks"][3]["translated_text"] == "npm install example-package"
    prompt_keys = [item["prompt_key"] for item in run["prompt_usage"]]
    assert "article.translate" in prompt_keys
    assert "article.metadata" in prompt_keys


def test_article_import_translation_invalid_json_does_not_fail_import(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        ninerouter_base_url="https://router.example/v1",
        article_openai_model="gpt-5.5-test",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/articles/agent-tools").mock(
            return_value=Response(200, html=ARTICLE_FIXTURE, headers={"content-type": "text/html; charset=utf-8"})
        )
        router.get("https://example.com/images/architecture.png").mock(
            return_value=Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
        )
        router.post("https://router.example/v1/chat/completions").mock(
            return_value=Response(200, json={"choices": [{"message": {"content": "not json"}}]})
        )
        response = client.post("/api/v1/articles/import", json={"url": "https://example.com/articles/agent-tools"})

    payload = response.json()
    run = payload["data"]["run"]
    assert response.status_code == 202
    assert payload["success"] is True
    assert run["status"] == "draft_ready"
    assert run["metadata"]["translation_status"] == "partial"
    assert run["metadata"]["draft_status"] == "ready"
    assert "translation_error" in run["metadata"]
    assert "translation_failed_batches" in run["metadata"]


def test_article_import_http_500_pauses_translation_without_failing_import(tmp_path: Path) -> None:
    client = build_client(
        tmp_path,
        ninerouter_base_url="https://router.example/v1",
        article_openai_model="gpt-5.5-test",
    )

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/articles/agent-tools").mock(
            return_value=Response(200, html=ARTICLE_FIXTURE, headers={"content-type": "text/html; charset=utf-8"})
        )
        router.get("https://example.com/images/architecture.png").mock(
            return_value=Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
        )
        router.post("https://router.example/v1/chat/completions").mock(
            return_value=Response(500, json={"error": {"message": "reset after 4s"}})
        )
        response = client.post("/api/v1/articles/import", json={"url": "https://example.com/articles/agent-tools"})

    payload = response.json()
    run = payload["data"]["run"]
    assert response.status_code == 202
    assert payload["success"] is True
    assert run["status"] == "draft_ready"
    assert run["metadata"]["translation_status"] == "partial"
    assert run["metadata"]["translation_paused"] is True
    assert run["metadata"]["translation_pause_reason"] == "provider_temporarily_unavailable_retry_later"
    assert "translation_failed_batches" in run["metadata"]


def test_article_import_get_loads_persisted_run(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    run = create_import_fixture(client)

    response = client.get(f"/api/v1/articles/import/{run['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["run"]["id"] == run["id"]
    assert payload["data"]["run"]["draft"]["content_format"] == "html"


def test_wordpress_dry_run_uses_automation_service_and_updates_run(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    run = create_import_fixture(client)
    fake = FakeWordPressAutomationService(ok=True)
    client.app.state.services["wordpress_automation_service"] = fake

    response = client.post(f"/api/v1/articles/import/{run['id']}/wordpress/dry-run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    updated = payload["data"]["run"]
    assert updated["metadata"]["wordpress_dry_run_status"] == "ready"
    assert updated["metadata"]["wordpress_page_url"].endswith("post-new.php")


def test_wordpress_paste_uses_draft_and_marks_run_pasted(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    run = create_import_fixture(client)
    fake = FakeWordPressAutomationService(ok=True)
    client.app.state.services["wordpress_automation_service"] = fake

    response = client.post(f"/api/v1/articles/import/{run['id']}/wordpress/paste")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    updated = payload["data"]["run"]
    assert updated["status"] == "pasted"
    assert updated["metadata"]["wordpress_paste_status"] == "pasted"
    assert fake.pasted_title == "Source Agent Tools"
    assert "<pre><code" in fake.pasted_content


def test_wordpress_paste_failure_returns_structured_error(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    run = create_import_fixture(client)
    client.app.state.services["wordpress_automation_service"] = FakeWordPressAutomationService(ok=False)

    response = client.post(f"/api/v1/articles/import/{run['id']}/wordpress/paste")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "WORDPRESS_PASTE_FAILED"
    assert payload["data"]["run"]["status"] == "draft_ready"


def test_article_import_writes_audit_events_for_import_and_paste(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit_logs.jsonl"
    client = build_client(tmp_path, audit_log_store_path=str(audit_path))
    run = create_import_fixture(client)
    fake = FakeWordPressAutomationService(ok=True)
    client.app.state.services["wordpress_automation_service"] = fake

    response = client.post(f"/api/v1/articles/import/{run['id']}/wordpress/paste")

    assert response.status_code == 200
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any('"action": "article_import_create"' in line and '"status": "success"' in line for line in lines)
    assert any('"action": "article_import_wordpress_paste"' in line and '"status": "success"' in line for line in lines)


@pytest.mark.asyncio
async def test_article_asset_service_downloads_and_deduplicates_images(tmp_path: Path) -> None:
    settings = Settings(
        article_import_storage_path=str(tmp_path / "article_imports"),
        tavily_key_store_path=str(tmp_path / "tavily_keys.json"),
        chat_session_store_path=str(tmp_path / "chat_sessions.json"),
        llm_runtime_store_path=str(tmp_path / "llm_runtime.json"),
        audit_log_store_path=str(tmp_path / "audit_logs.jsonl"),
    )
    service = ArticleAssetService(settings=settings)
    assets = [
        ArticleAsset(id="asset_1", source_url="https://example.com/a.png"),
        ArticleAsset(id="asset_2", source_url="https://example.com/b.png"),
    ]

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/a.png").mock(
            return_value=Response(200, content=b"same-image", headers={"content-type": "image/png"})
        )
        router.get("https://example.com/b.png").mock(
            return_value=Response(200, content=b"same-image", headers={"content-type": "image/png"})
        )
        downloaded = await service.download_assets(assets=assets, assets_dir=str(tmp_path / "assets"))

    assert downloaded[0].download_status == "downloaded"
    assert downloaded[1].download_status == "downloaded"
    assert downloaded[0].checksum == downloaded[1].checksum
    assert downloaded[0].local_path == downloaded[1].local_path
    assert downloaded[1].metadata["deduplicated"] is True
    assert Path(downloaded[0].local_path).exists()


@pytest.mark.asyncio
async def test_article_asset_service_skips_non_image_and_oversized_assets(tmp_path: Path) -> None:
    settings = Settings(
        article_asset_max_bytes=4,
        article_import_storage_path=str(tmp_path / "article_imports"),
        tavily_key_store_path=str(tmp_path / "tavily_keys.json"),
        chat_session_store_path=str(tmp_path / "chat_sessions.json"),
        llm_runtime_store_path=str(tmp_path / "llm_runtime.json"),
        audit_log_store_path=str(tmp_path / "audit_logs.jsonl"),
    )
    service = ArticleAssetService(settings=settings)
    assets = [
        ArticleAsset(id="asset_1", source_url="https://example.com/page.html"),
        ArticleAsset(id="asset_2", source_url="https://example.com/large.png"),
    ]

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/page.html").mock(
            return_value=Response(200, content=b"<html></html>", headers={"content-type": "text/html"})
        )
        router.get("https://example.com/large.png").mock(
            return_value=Response(200, content=b"too-large", headers={"content-type": "image/png"})
        )
        downloaded = await service.download_assets(assets=assets, assets_dir=str(tmp_path / "assets"))

    assert downloaded[0].download_status == "skipped"
    assert downloaded[0].metadata["skip_reason"].startswith("non_image_content_type")
    assert downloaded[1].download_status == "skipped"
    assert downloaded[1].metadata["skip_reason"] == "asset_too_large"


@pytest.mark.asyncio
async def test_article_asset_service_falls_back_to_srcset_candidate_on_failure(tmp_path: Path) -> None:
    settings = Settings(
        article_import_storage_path=str(tmp_path / "article_imports"),
        tavily_key_store_path=str(tmp_path / "tavily_keys.json"),
        chat_session_store_path=str(tmp_path / "chat_sessions.json"),
        llm_runtime_store_path=str(tmp_path / "llm_runtime.json"),
        audit_log_store_path=str(tmp_path / "audit_logs.jsonl"),
    )
    service = ArticleAssetService(settings=settings)
    assets = [
        ArticleAsset(
            id="asset_1",
            source_url="https://example.com/blocked.webp",
            metadata={"srcset": "https://example.com/fallback.png 1024w, https://example.com/fallback-small.png 320w"},
        )
    ]

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/blocked.webp").mock(return_value=Response(403, text="forbidden"))
        router.get("https://example.com/fallback.png").mock(
            return_value=Response(200, content=b"fallback-image", headers={"content-type": "image/png"})
        )
        downloaded = await service.download_assets(assets=assets, assets_dir=str(tmp_path / "assets"))

    assert downloaded[0].download_status == "downloaded"
    assert downloaded[0].source_url == "https://example.com/fallback.png"
    assert downloaded[0].mime_type == "image/png"
    assert Path(downloaded[0].local_path).exists()


def test_wordpress_draft_builder_renders_translated_blocks_and_attribution() -> None:
    extractor = ArticleExtractorService()
    result = extractor.extract(ARTICLE_FIXTURE, "https://example.com/articles/agent-tools")
    result.blocks[0].translated_text = "Cong cu Agent"
    result.blocks[1].translated_text = "Agent co the goi tool an toan."
    result.blocks[3].translated_text = "npm install example-package"
    result.assets[0].local_path = "data/article_imports/air_test/assets/asset_1.png"
    builder = WordPressDraftBuilder()
    from src.models.article_schemas import ArticleImportMode, ArticleImportRun, ArticleImportStatus, ArticleStorageManifest
    from datetime import datetime, timezone

    run = ArticleImportRun(
        id="air_test",
        status=ArticleImportStatus.TRANSLATED,
        mode=ArticleImportMode.DRAFT,
        target_language="vi",
        source=result.source,
        storage=ArticleStorageManifest(
            run_dir="data/article_imports/air_test",
            raw_snapshot_path="data/article_imports/air_test/raw.html",
            extracted_json_path="data/article_imports/air_test/extracted.json",
            draft_json_path="data/article_imports/air_test/draft.json",
            assets_dir="data/article_imports/air_test/assets",
        ),
        blocks=result.blocks,
        assets=result.assets,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    draft = builder.build(run)

    assert draft.title == "Source Agent Tools"
    assert draft.slug == "source-agent-tools"
    assert "<h2>Cong cu Agent</h2>" in draft.content
    assert "<p>Agent co the goi tool an toan.</p>" in draft.content
    assert '<img src="data/article_imports/air_test/assets/asset_1.png"' in draft.content
    assert "<pre><code class=\"language-bash\">npm install example-package</code></pre>" in draft.content
    assert "rel=\"nofollow noopener\"" in draft.content
