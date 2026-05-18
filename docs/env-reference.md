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

### Local stores

- `APP_TAVILY_KEY_STORE_PATH`
- `APP_CHAT_SESSION_STORE_PATH`
- `APP_CHAT_SESSION_RETENTION_DAYS`
- `APP_LLM_RUNTIME_STORE_PATH`
- `APP_AUDIT_LOG_STORE_PATH`

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
