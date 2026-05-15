# Environment Reference

## Root `.env`

Duoc dung boi `setup.sh` de dong bo backend/frontend.

- `BACKEND_HOST`: host backend runtime, vd `127.0.0.1`
- `BACKEND_PORT`: port backend, vd `8011`
- `FRONTEND_HOST`: host frontend dev server, vd `0.0.0.0`
- `FRONTEND_PORT`: port frontend, vd `3005`
- `FRONTEND_PUBLIC_HOST`: host de access frontend tu browser
- `PUBLIC_BACKEND_HOST`: host backend de frontend/reverse-proxy su dung
- `AUTO_START_APPS`: `true|false` auto start app sau setup
- `LLM_MODEL`: model id cho backend
- `LLM_BASE_URL`: optional override cho endpoint OpenAI-compatible
	- Day la cho chinh de doi IP/host model khi model nam o may khac.
	- Vi du: `http://192.168.2.74:8007/v1`
- `FEATURE_SESSION_HISTORY`: bat/tat UI + API session/history
- `FEATURE_OPS_DASHBOARD`: bat/tat UI + API ops dashboard
- `FEATURE_LLM_RUNTIME_CONFIG`: bat/tat API llm runtime config/health/test
- `RBAC_ENABLED`: bat/tat RBAC guard cho endpoint nhay cam
- `RBAC_ADMIN_TOKEN`: token cho role `admin` khi `RBAC_ENABLED=true`
- `OPS_ROLE`: role frontend gui len backend (`viewer|operator|admin`)
- `OPS_ADMIN_TOKEN`: admin token frontend gui len backend
- `POSTGRES_AUTO_START`: `true|false`, auto-start PostgreSQL Docker container khi chay `setup.sh`
- `POSTGRES_CONTAINER_NAME`: mac dinh `websearch-pg`
- `POSTGRES_FORCE_RECREATE`: `true|false`, xoa container PostgreSQL cu va tao lai
- `POSTGRES_PORT`: port public cua PostgreSQL, mac dinh `5432`
- `POSTGRES_DB`: database name, mac dinh `web_search`
- `POSTGRES_USER`: user PostgreSQL, mac dinh `postgres`
- `POSTGRES_PASSWORD`: password PostgreSQL, mac dinh `postgres`
- `PGADMIN_AUTO_START`: `true|false`, auto-start pgAdmin Docker container
- `PGADMIN_CONTAINER_NAME`: mac dinh `websearch-pgadmin`
- `PGADMIN_PORT`: port pgAdmin, mac dinh `5050`
- `PGADMIN_DEFAULT_EMAIL`: email dang nhap pgAdmin
- `PGADMIN_DEFAULT_PASSWORD`: password dang nhap pgAdmin
- `SEARXNG_AUTO_START`: `true|false`, auto-start local SearXNG Docker container
- `SEARXNG_CONTAINER_NAME`: mac dinh `websearch-searxng`
- `SEARXNG_FORCE_RECREATE`: `true|false`, xoa container SearXNG cu va tao lai de nhan config moi
- `SEARXNG_PORT`: port local SearXNG, mac dinh `8080`

## `backend/.env`

Tien to `APP_`.

- `APP_APP_NAME`
- `APP_ENVIRONMENT`
- `APP_API_PREFIX`
- `APP_CORS_ORIGINS`
- `APP_REQUEST_TIMEOUT_SECONDS`
- `APP_QUALITY_MIN_RESULTS`
- `APP_QUALITY_MIN_UNIQUE_DOMAINS`
- `APP_RESULT_CACHE_TTL_SECONDS`
- `APP_TAVILY_SEARCH_DEPTH`
- `APP_TAVILY_MAX_COOLDOWN_SECONDS`
- `APP_TAVILY_KEY_STORE_PATH`
- `APP_CHAT_SESSION_STORE_PATH`
- `APP_CHAT_SESSION_RETENTION_DAYS`
- `APP_LLM_RUNTIME_STORE_PATH`: file luu runtime config cho dashboard LLM
- `APP_AUDIT_LOG_STORE_PATH`: file log audit thao tac nhay cam
- `APP_DATABASE_URL`: chuoi ket noi PostgreSQL (vd `postgresql+psycopg://postgres:postgres@localhost:5432/web_search?connect_timeout=5`)
- `APP_SESSION_STORE_BACKEND`: `auto|local|postgres`
- `APP_SESSION_STORE_DUAL_WRITE`: `true|false`, ghi ca Postgres + JSON trong giai doan chuyen doi
- `APP_RBAC_ENABLED`: `true|false` bat guard role cho API nhay cam
- `APP_RBAC_ADMIN_TOKEN`: token bo sung cho role admin
- `APP_FEATURE_SESSION_HISTORY`
- `APP_FEATURE_OPS_DASHBOARD`
- `APP_FEATURE_LLM_RUNTIME_CONFIG`
- `APP_LLM_ENABLED`
- `APP_LLM_BASE_URL`
	- Backend doc bien nay tu `backend/.env`.
	- Neu model host remote, sua gia tri nay hoac sua root `LLM_BASE_URL` roi chay lai setup.
- `APP_LLM_MODEL`
- `APP_LLM_TEMPERATURE`
- `APP_LLM_MAX_TOKENS` (optional)
- `APP_LLM_SUMMARY_MAX_CHARS`: fallback default cho target output length neu runtime config chua co
- `APP_LLM_SUMMARY_SYSTEM_PROMPT`: fallback default system prompt neu runtime config chua co
- `APP_QUERY_ANALYST_MODE`: `rule` hoac `llm`
- `APP_SEARXNG_BASE_URL`
- `APP_SEARXNG_BACKUP_BASE_URLS`
- `APP_SEARXNG_CATEGORIES`
- `APP_SEARXNG_MAX_QPS`
- `APP_SEARXNG_CIRCUIT_FAIL_THRESHOLD`
- `APP_SEARXNG_CIRCUIT_OPEN_SECONDS`
- `APP_FORCE_SEARXNG_TEST_MODE`: `true|false`, khi Tavily key khong usable thi bo qua circuit de test SearXNG fallback

## Runtime LLM config

Endpoint:
- `GET /api/v1/llm/config`
- `PATCH /api/v1/llm/config`

File store mac dinh:
- `backend/config/llm_runtime.json`

Truong quan trong:
- `summary_system_prompt`: system prompt cho final summarizer.
- `summary_max_chars`: target output length. Hien tai backend uu tien prompt/rewrite de LLM tu viet gon trong ngan sach nay, khong uu tien cat thang output sau khi sinh.

## `frontend/.env.local`

- `NEXT_PUBLIC_API_BASE`: mac dinh `/api/v1`
- `API_PROXY_HOST`: backend host cho rewrite
- `API_PROXY_PORT`: backend port cho rewrite
- `NEXT_PUBLIC_FEATURE_SESSION_HISTORY`
- `NEXT_PUBLIC_FEATURE_OPS_DASHBOARD`
- `NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG`
- `NEXT_PUBLIC_OPS_ROLE`
- `NEXT_PUBLIC_OPS_ADMIN_TOKEN`
