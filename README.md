# Web Agent

Web Agent là ứng dụng tìm kiếm web dạng chat. Hệ thống ưu tiên Tavily để lấy dữ liệu web, có thể fallback sang SearXNG khi Tavily không khả dụng hoặc chất lượng nguồn chưa đủ tốt. Câu trả lời cuối cùng được tổng hợp bằng LLM OpenAI-compatible và hiển thị trong giao diện Next.js.

Repository: https://github.com/baolnq-ai/web-agent

## Tính năng chính

- Chat UI giống trợ lý tìm kiếm: nhập câu hỏi, xem câu trả lời, nguồn, confidence và lịch sử phiên.
- Tavily-first retrieval, fallback SearXNG, query expansion, evidence merge và quality gate.
- LLM final summarizer hỗ trợ runtime config: base URL, model, temperature, max tokens, prompt và target output length theo token.
- Prompt Manager cho phép cấu hình prompt tổng hợp cuối cùng mà không cần sửa code.
- Session history theo từng phiên chat, hỗ trợ local JSON hoặc PostgreSQL.
- Streaming qua SSE để frontend nhận trạng thái pipeline và nội dung trả lời.
- Ops Dashboard để kiểm tra Tavily key, LLM health/test, audit logs và trạng thái vận hành.
- Script chạy đa nền tảng: Bash cho Linux/macOS/Git Bash, PowerShell cho Windows.
- CI GitHub Actions chạy backend tests, frontend lint và frontend build.

## Kiến trúc nhanh

```text
User
  -> Next.js Chat UI
  -> FastAPI /api/v1/search/stream
  -> Context Query Rewriter
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

Chi tiết xem [docs/architecture-pipeline.md](docs/architecture-pipeline.md).

## Tech stack

- Backend: FastAPI, Pydantic Settings, HTTPX, SQLAlchemy, Alembic, psycopg.
- Frontend: Next.js 16, React 19, Tailwind CSS 4.
- Search providers: Tavily, SearXNG.
- LLM: API OpenAI-compatible, ví dụ vLLM/local model server.
- Local infra tùy chọn: PostgreSQL, pgAdmin, SearXNG Docker.
- CI/CD: GitHub Actions.

## Cấu trúc thư mục

```text
web-agent/
  backend/                 FastAPI backend
  frontend/                Next.js frontend
  config/                  cấu hình local cho infra phụ trợ
  docs/                    tài liệu dự án
  .github/workflows/       GitHub Actions CI
  setup.sh                 setup Linux/macOS/Git Bash
  run.sh                   chạy app Linux/macOS/Git Bash
  stop.sh                  dừng app Linux/macOS/Git Bash
  delete.sh                xoá container/image Docker local
  setup.ps1                setup Windows PowerShell
  run.ps1                  chạy app Windows PowerShell
  stop.ps1                 dừng app Windows PowerShell
  delete.ps1               xoá container/image Docker local trên Windows
```

## Setup nhanh

### Linux/macOS/Git Bash

```bash
cd web-agent
cp .env.example .env
./setup.sh
```

### Windows PowerShell

```powershell
cd web-agent
Copy-Item .env.example .env -Force
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

Nếu không muốn đổi execution policy trong phiên PowerShell hiện tại, có thể gọi trực tiếp:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

## Chạy và dừng app

Linux/macOS/Git Bash:

```bash
./run.sh
./stop.sh
```

Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

URL mặc định:

- Frontend: `http://localhost:3005`
- Backend: `http://127.0.0.1:8011`
- API prefix: `/api/v1`

## Dọn Docker local

Nếu bật PostgreSQL, pgAdmin hoặc SearXNG bằng Docker, có thể dọn container/image bằng:

```bash
./delete.sh
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1
```

Giữ lại image, chỉ xoá container:

```bash
./delete.sh --keep-images
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1 -KeepImages
```

## Cấu hình quan trọng

Root `.env` dùng cho script setup/run:

- `BACKEND_HOST`, `BACKEND_PORT`: host/port backend.
- `FRONTEND_HOST`, `FRONTEND_PORT`: host/port frontend.
- `LLM_BASE_URL`: endpoint OpenAI-compatible, ví dụ `http://127.0.0.1:8007/v1`.
- `LLM_MODEL`: model ID.
- `FEATURE_SESSION_HISTORY`: bật/tắt lịch sử chat.
- `FEATURE_OPS_DASHBOARD`: bật/tắt Ops Dashboard.
- `FEATURE_LLM_RUNTIME_CONFIG`: bật/tắt Prompt Manager/LLM runtime config.
- `POSTGRES_AUTO_START`, `PGADMIN_AUTO_START`, `SEARXNG_AUTO_START`: tự start infra Docker khi setup.

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
- `GET /api/v1/llm/config`
- `PATCH /api/v1/llm/config`
- `GET /api/v1/llm/health`
- `POST /api/v1/llm/test`
- `GET /api/v1/ops/audit/logs`

## Kiểm thử local

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

Trên Linux/macOS thay `../.venv/Scripts/python.exe` bằng `../.venv/bin/python`.

## CI/CD

Workflow hiện tại nằm tại [.github/workflows/ci.yml](.github/workflows/ci.yml).

CI chạy khi `push`, `pull_request` hoặc `workflow_dispatch`:

- Backend job: setup Python 3.12, install `backend[dev]`, chạy `pytest`.
- Frontend job: setup Node 24, `npm ci`, `npm run lint`, `npm run build`.

CD chưa bật vì chưa có target deploy chính thức. Khi có staging/production, nên thêm workflow deploy riêng, dùng GitHub Environments và Secrets cho endpoint/key.

Chi tiết xem [docs/ci-cd.md](docs/ci-cd.md).

## Tài liệu thêm

- [docs/README.md](docs/README.md): mục lục tài liệu.
- [docs/setup-cross-platform.md](docs/setup-cross-platform.md): setup đa nền tảng.
- [docs/architecture-pipeline.md](docs/architecture-pipeline.md): kiến trúc và pipeline.
- [docs/env-reference.md](docs/env-reference.md): biến môi trường.
- [docs/ci-cd.md](docs/ci-cd.md): CI/CD.

## Ghi chú vận hành

- Không commit `.env`, `backend/.env`, `frontend/.env.local`, logs hoặc key thật.
- Nếu model chạy trên máy khác, máy chạy backend phải truy cập được `LLM_BASE_URL`.
- Nếu public SearXNG bị `403/429`, nên bật SearXNG local bằng Docker.
- Nếu chạy PowerShell bị chặn script, dùng `-ExecutionPolicy Bypass` như ví dụ phía trên.
