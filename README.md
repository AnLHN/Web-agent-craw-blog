# Web Agent

Web Agent là ứng dụng tìm kiếm web kiểu chat, ưu tiên Tavily để lấy dữ liệu nhanh và chất lượng, fallback sang SearXNG khi Tavily không khả dụng hoặc kết quả chưa đủ tốt. Backend dùng FastAPI, frontend dùng Next.js, và câu trả lời cuối được tổng hợp bằng LLM OpenAI-compatible.

Repository: https://github.com/baolnq-ai/web-agent

## Điểm nổi bật

- Giao diện chat giống ChatGPT: lịch sử phiên ở sidebar trái, khung chat ở giữa, thanh nhập cố định phía dưới.
- Popup `Cài đặt` gom các manager: Tavily Keys, Ops Dashboard, Prompt Manager.
- Tavily-first retrieval, SearXNG fallback, query expansion, evidence merge, quality gate.
- Stream trạng thái pipeline qua `POST /api/v1/search/stream` để UI hiển thị tiến trình xử lý.
- Runtime LLM config: đổi base URL, model, temperature, max tokens, system prompt và target output length không cần restart.
- Session/search history hỗ trợ local JSON hoặc PostgreSQL.
- CI GitHub Actions chạy backend tests, frontend lint và frontend build.

## Kiến trúc nhanh

```text
User
  -> Next.js Chat UI
  -> FastAPI /api/v1/search/stream
  -> Query Analyst
  -> Query Planner
  -> Multi-query Retrieval
       -> Tavily first
       -> SearXNG fallback
  -> Evidence Merge
  -> Quality Gate
  -> LLM Final Summary
  -> SSE status/token/done
  -> Session/Search Trace Store
```

Chi tiết hơn nằm ở [docs/architecture-pipeline.md](docs/architecture-pipeline.md).

## Tech stack

- Backend: FastAPI, Pydantic Settings, HTTPX, SQLAlchemy, Alembic, psycopg.
- Frontend: Next.js 16, React 19, Tailwind CSS 4.
- Search providers: Tavily, SearXNG.
- LLM: endpoint OpenAI-compatible, ví dụ vLLM local/remote.
- Local infra tùy chọn: PostgreSQL, pgAdmin, SearXNG Docker.
- CI: GitHub Actions.

## Setup nhanh

### Git Bash/Linux/macOS

```bash
cp .env.example .env
./setup.sh
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env -Force
& "D:\Git\bin\bash.exe" -lc "cd /e/CODE/NTC_AI/Web_search_/web-agent && ./setup.sh"
```

`setup.sh` sẽ:

- tạo `.venv`;
- cài dependencies backend/frontend;
- tạo hoặc đồng bộ `backend/.env` và `frontend/.env.local`;
- cập nhật CORS, proxy, feature flags, RBAC;
- tự tạo/start PostgreSQL, pgAdmin, SearXNG nếu bật trong root `.env`;
- tự start backend/frontend nếu `AUTO_START_APPS=true`.

## Chạy thủ công

Backend:

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

Frontend:

```bash
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3005
```

URL mặc định:

- Frontend: `http://localhost:3005`
- Backend: `http://127.0.0.1:8011`
- API prefix: `/api/v1`

## Cấu hình quan trọng

Root `.env`:

- `BACKEND_HOST`, `BACKEND_PORT`: địa chỉ backend.
- `FRONTEND_HOST`, `FRONTEND_PORT`: địa chỉ frontend.
- `LLM_BASE_URL`: endpoint model OpenAI-compatible, ví dụ `http://192.168.1.x:8007/v1`.
- `LLM_MODEL`: model ID.
- `FEATURE_SESSION_HISTORY`: bật/tắt lịch sử chat.
- `FEATURE_OPS_DASHBOARD`: bật/tắt Ops Dashboard.
- `FEATURE_LLM_RUNTIME_CONFIG`: bật/tắt LLM runtime config.
- `POSTGRES_AUTO_START`, `PGADMIN_AUTO_START`, `SEARXNG_AUTO_START`: tự start local infra bằng Docker.

Backend `.env`:

- `APP_LLM_BASE_URL`, `APP_LLM_MODEL`, `APP_LLM_TEMPERATURE`, `APP_LLM_MAX_TOKENS`.
- `APP_SESSION_STORE_BACKEND=auto|local|postgres`.
- `APP_DATABASE_URL`: PostgreSQL URL.
- `APP_SEARXNG_BASE_URL`: SearXNG fallback URL.
- `APP_QUERY_ANALYST_MODE=rule|llm`.

Xem đầy đủ tại [docs/env-reference.md](docs/env-reference.md).

## API chính

- `GET /api/v1/health`
- `POST /api/v1/search`
- `POST /api/v1/search/stream`
- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `DELETE /api/v1/chat/sessions/{session_id}`
- `GET /api/v1/keys/tavily`
- `POST /api/v1/keys/tavily`
- `DELETE /api/v1/keys/tavily/{key_id}`
- `GET /api/v1/keys/tavily/metrics`
- `GET /api/v1/llm/config`
- `PATCH /api/v1/llm/config`
- `GET /api/v1/llm/health`
- `POST /api/v1/llm/test`
- `GET /api/v1/ops/audit/logs`
- `POST /api/v1/ops/searxng/circuit/reset`

## Frontend hiện tại

- Sidebar trái: lịch sử chat/session, chat mới, cài đặt.
- Main workspace: hội thoại tìm kiếm web, composer nhập câu hỏi, số `Nguồn` để chọn số nguồn web tối đa.
- Popup `Cài đặt`: Tavily Keys, Ops Dashboard, Prompt Manager.
- Màu giao diện: xanh + cam, theo hướng gọn và tươi.
- UI dùng `/api/v1/search/stream` để hiển thị trạng thái xử lý và câu trả lời đang tạo.

## Testing

Backend:

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## CI/CD

Workflow hiện tại: [.github/workflows/ci.yml](.github/workflows/ci.yml)

CI chạy khi `push` hoặc `pull_request`:

- Backend job:
  - setup Python 3.12;
  - install `backend[dev]`;
  - chạy `pytest`.
- Frontend job:
  - setup Node;
  - `npm ci`;
  - `npm run lint`;
  - `npm run build`.

CD chưa bật vì chưa có target deploy chính thức. Khi có staging/production, nên thêm workflow deploy riêng, dùng GitHub Environments và GitHub Secrets cho endpoint/key.

## Ghi chú vận hành

- Không commit `.env`, `backend/.env`, `frontend/.env.local`.
- Không commit key thật, logs runtime, hoặc dữ liệu session local.
- Nếu model host ở máy khác, máy chạy backend phải ping/curl được `APP_LLM_BASE_URL`.
- Nếu public SearXNG bị `403/429`, nên bật SearXNG local bằng Docker.
- Nếu backend không start vì `APP_LLM_MAX_TOKENS=` rỗng, code hiện đã xử lý chuỗi rỗng thành `None`.

## Tài liệu thêm

- [docs/architecture-pipeline.md](docs/architecture-pipeline.md)
- [docs/blog-brief.md](docs/blog-brief.md)
- [docs/env-reference.md](docs/env-reference.md)
- [docs/setup-cross-platform.md](docs/setup-cross-platform.md)
- [docs/task-web-search-implementation.md](docs/task-web-search-implementation.md)
