# Tham chiếu biến môi trường

Dự án có ba lớp cấu hình chính:

- Root `.env`: dùng bởi script setup/run để đồng bộ backend/frontend và local infra.
- `backend/.env`: cấu hình FastAPI backend.
- `frontend/.env.local`: cấu hình Next.js frontend.

Không commit các file env thật vào git.

## Root `.env`

Root `.env` được tạo từ `.env.example`.

### Runtime app

- `BACKEND_HOST`: host backend, mặc định `127.0.0.1`.
- `BACKEND_PORT`: port backend, mặc định `8011`.
- `FRONTEND_HOST`: host frontend dev server, mặc định `0.0.0.0`.
- `FRONTEND_PORT`: port frontend, mặc định `3005`.
- `FRONTEND_PUBLIC_HOST`: host frontend cho browser.
- `PUBLIC_BACKEND_HOST`: host backend public nếu cần reverse proxy.
- `AUTO_START_APPS`: `true|false`, tự start app sau setup.

### LLM

- `LLM_BASE_URL`: endpoint OpenAI-compatible, ví dụ `http://127.0.0.1:8007/v1`.
- `LLM_MODEL`: model ID.

Máy chạy backend phải truy cập được `LLM_BASE_URL`. Kiểm tra nhanh:

```bash
curl http://127.0.0.1:8007/v1/models
```

### Feature flags

- `FEATURE_SESSION_HISTORY`: bật/tắt session history.
- `FEATURE_OPS_DASHBOARD`: bật/tắt Ops Dashboard.
- `FEATURE_LLM_RUNTIME_CONFIG`: bật/tắt Prompt Manager và LLM runtime config.

### RBAC/Ops

- `RBAC_ENABLED`: bật/tắt RBAC guard cho endpoint nhạy cảm.
- `RBAC_ADMIN_TOKEN`: token admin backend.
- `OPS_ROLE`: role frontend gửi lên backend, ví dụ `viewer`, `operator`, `admin`.
- `OPS_ADMIN_TOKEN`: admin token frontend gửi lên backend.

### PostgreSQL Docker

- `POSTGRES_AUTO_START`: tự start PostgreSQL khi setup.
- `POSTGRES_CONTAINER_NAME`: tên container, mặc định `websearch-pg`.
- `POSTGRES_IMAGE`: image, mặc định `postgres:16`.
- `POSTGRES_FORCE_RECREATE`: xoá container cũ và tạo lại.
- `POSTGRES_PORT`: port public, mặc định `5432`.
- `POSTGRES_DB`: database, mặc định `web_search`.
- `POSTGRES_USER`: user, mặc định `postgres`.
- `POSTGRES_PASSWORD`: password, mặc định `postgres`.

### pgAdmin Docker

- `PGADMIN_AUTO_START`: tự start pgAdmin khi setup.
- `PGADMIN_CONTAINER_NAME`: tên container, mặc định `websearch-pgadmin`.
- `PGADMIN_IMAGE`: image, mặc định `dpage/pgadmin4:8`.
- `PGADMIN_PORT`: port public, mặc định `5050`.
- `PGADMIN_DEFAULT_EMAIL`: email đăng nhập.
- `PGADMIN_DEFAULT_PASSWORD`: password đăng nhập.

### SearXNG Docker

- `SEARXNG_AUTO_START`: tự start SearXNG local.
- `SEARXNG_CONTAINER_NAME`: tên container, mặc định `websearch-searxng`.
- `SEARXNG_IMAGE`: image, mặc định `searxng/searxng:latest`.
- `SEARXNG_FORCE_RECREATE`: xoá container cũ và tạo lại.
- `SEARXNG_PORT`: port public, mặc định `8080`.

### 9Router và WordPress browser CDP

- `NINEROUTER_INSTALL`: tự cài `9router` global bằng npm khi setup.
- `NINEROUTER_AUTO_START`: tự start 9Router khi setup.
- `NINEROUTER_START_MODE`: `terminal` hoặc background.
- `NINEROUTER_BASE_URL`: mặc định `http://127.0.0.1:20128/v1`.
- `NINEROUTER_DASHBOARD_URL`: mặc định `http://localhost:20128/dashboard`.
- `WP_CHROME_AUTO_START`: tự mở Chrome/Brave/Edge với CDP port riêng cho WordPress automation.
- `WP_CHROME_PORT`: mặc định `9227`.
- `WP_CHROME_URL`: URL mở sẵn, ví dụ trang tạo bài WordPress.

## `backend/.env`

Các biến backend dùng prefix `APP_`.

### App/API

- `APP_APP_NAME`
- `APP_ENVIRONMENT`
- `APP_API_PREFIX`
- `APP_CORS_ORIGINS`
- `APP_REQUEST_TIMEOUT_SECONDS`

### Quality/search

- `APP_QUALITY_MIN_RESULTS`
- `APP_QUALITY_MIN_UNIQUE_DOMAINS`
- `APP_RESULT_CACHE_TTL_SECONDS`
- `APP_TAVILY_SEARCH_DEPTH`
- `APP_TAVILY_MAX_COOLDOWN_SECONDS`
- `APP_FORCE_SEARXNG_TEST_MODE`

## Tavily API key

Tavily key không nằm trong `.env.example`. Người dùng lấy key từ Tavily dashboard rồi thêm qua UI hoặc API để tránh commit secret vào repo.

Nguồn lấy key:

- Tavily dashboard: `https://tavily.com/`
- Tavily API keys: `https://tavily.com/api-keys`
- Tavily docs: `https://docs.tavily.com/documentation/api-reference/introduction`

Thêm key qua UI:

1. Mở `http://localhost:3005`.
2. Vào `Cài đặt`.
3. Mở `Tavily Keys`.
4. Dán key và lưu.

Thêm key qua API:

```bash
curl -X POST http://127.0.0.1:8011/api/v1/keys/tavily \
  -H "Content-Type: application/json" \
  -d '{"api_key":"tvly-YOUR_API_KEY","label":"Default key"}'
```

Key được lưu local tại:

```text
backend/config/tavily_keys.json
```

Không commit file này nếu chứa key thật.

### Local stores

- `APP_TAVILY_KEY_STORE_PATH`
- `APP_CHAT_SESSION_STORE_PATH`
- `APP_CHAT_SESSION_RETENTION_DAYS`
- `APP_LLM_RUNTIME_STORE_PATH`
- `APP_AUDIT_LOG_STORE_PATH`
- `APP_AUTH_STORE_PATH`: file-backed auth store cho phase local/dev.
- `APP_AUTH_TOKEN_SECRET`: secret dùng hash bearer session token; production phải đổi giá trị này.

### Database/session

- `APP_DATABASE_URL`: PostgreSQL connection string.
- `APP_SESSION_STORE_BACKEND`: `auto|local|postgres`.
- `APP_SESSION_STORE_DUAL_WRITE`: ghi cả Postgres và JSON trong giai đoạn chuyển đổi.

### LLM

- `APP_LLM_ENABLED`
- `APP_LLM_BASE_URL`
- `APP_LLM_MODEL`
- `APP_LLM_TEMPERATURE`
- `APP_LLM_MAX_TOKENS`
- `APP_LLM_SUMMARY_MAX_TOKENS`
- `APP_LLM_SUMMARY_SYSTEM_PROMPT`

Lưu ý:

- `APP_LLM_MAX_TOKENS` là token budget gửi xuống OpenAI-compatible API.
- `APP_LLM_SUMMARY_MAX_TOKENS` là target output length cho final summary.
- Nếu để `APP_LLM_MAX_TOKENS=` rỗng, backend nên hiểu là `None`.

### Query/Provider

- `APP_QUERY_ANALYST_MODE`: `rule` hoặc `llm`.
- `APP_SEARXNG_BASE_URL`
- `APP_SEARXNG_BACKUP_BASE_URLS`
- `APP_SEARXNG_CATEGORIES`
- `APP_SEARXNG_MAX_QPS`
- `APP_SEARXNG_CIRCUIT_FAIL_THRESHOLD`
- `APP_SEARXNG_CIRCUIT_OPEN_SECONDS`

### Article Import / Craw Blog

- `APP_ARTICLE_LLM_PROVIDER`: provider metadata, mặc định `9router_openai`.
- `APP_9ROUTER_BASE_URL`: OpenAI-compatible base URL của 9Router, mặc định `http://127.0.0.1:20128/v1`.
- `APP_9ROUTER_API_KEY`: key gửi tới 9Router nếu router yêu cầu auth. Không commit key thật.
- `APP_ARTICLE_OPENAI_MODEL`: model ID trong 9Router, mặc định `cx/gpt-5.5`.
- `APP_ARTICLE_TRANSLATION_MAX_OUTPUT_TOKENS`: output token budget mỗi request dịch, mặc định `8000`.
- `APP_ARTICLE_TRANSLATION_MAX_BATCHES_PER_RUN`: số batch tối đa mỗi lần import/translate trước khi pause.
- `APP_ARTICLE_TRANSLATION_BATCH_SIZE`: số block tối đa mỗi batch, mặc định `3`.
- `APP_ARTICLE_TRANSLATION_MAX_BATCH_CHARS`: tổng ký tự source tối đa mỗi batch, mặc định `8000`.
- `APP_ARTICLE_IMPORT_STORAGE_PATH`: nơi lưu raw/extracted/draft artifacts.
- `APP_WORDPRESS_CHROME_CDP_URL`: CDP endpoint browser WordPress, mặc định `http://127.0.0.1:9227`.

Extractor hiện giữ link bằng placeholder `[LINK_n:label]` trong `source_text`. Model phải giữ `LINK_n`, được phép dịch label; draft builder render lại thành anchor HTML.

## Runtime LLM config

Endpoint:

- `GET /api/v1/llm/config`
- `PATCH /api/v1/llm/config`

File store mặc định:

- `backend/config/llm_runtime.json`

Trường quan trọng:

- `base_url`: LLM base URL.
- `model`: model ID.
- `temperature`: nhiệt độ sinh câu trả lời.
- `max_tokens`: token budget API.
- `summary_system_prompt`: system prompt cho final summarizer.
- `summary_max_tokens`: target output length theo token.

Prompt Manager trên UI quản lý runtime config này. Đây là prompt dùng cho LLM final summary, không phải prompt riêng rời rạc khác.

## `frontend/.env.local`

- `NEXT_PUBLIC_API_BASE`: mặc định `/api/v1`.
- `API_PROXY_HOST`: backend host cho Next.js rewrite.
- `API_PROXY_PORT`: backend port cho Next.js rewrite.
- `NEXT_PUBLIC_FEATURE_SESSION_HISTORY`
- `NEXT_PUBLIC_FEATURE_OPS_DASHBOARD`
- `NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG`
- `NEXT_PUBLIC_OPS_ROLE`
- `NEXT_PUBLIC_OPS_ADMIN_TOKEN`

## Endpoint streaming

Frontend dùng `POST /api/v1/search/stream`.

Event SSE:

- `status`: trạng thái pipeline.
- `token`: chunk câu trả lời.
- `done`: final result.
- `error`: lỗi.
