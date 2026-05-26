# Web Agent Craw Blog

Web Agent Craw Blog là ứng dụng web gồm FastAPI backend và Next.js frontend cho hai luồng chính:

1. **Web search dạng chat**: Tavily-first retrieval, fallback SearXNG, tổng hợp bằng LLM OpenAI-compatible.
2. **Article Import / Craw Blog**: nhập URL bài viết, crawl nội dung, tách text/media/code/table/list/link, dịch/biên tập bằng 9Router GPT 5.5, build draft HTML và hỗ trợ paste vào WordPress qua browser CDP.

Repository: https://github.com/AnLHN/Web-agent-craw-blog.git

## Tính năng chính

- Chat UI giống trợ lý tìm kiếm: câu hỏi, câu trả lời, nguồn, confidence, session history.
- Tavily-first search pipeline, SearXNG fallback, query expansion, evidence merge và quality gate.
- LLM final summarizer dùng OpenAI-compatible API, có runtime config cho base URL/model/temperature/max tokens/prompt.
- Article Import nhận URL bài viết, crawl HTML, tải ảnh, extract heading/paragraph/list/quote/table/code/embed/image.
- Dịch bài theo batch cân bằng tối ưu qua 9Router GPT 5.5 (`cx/gpt-5.5`), có retry lỗi 429/500/502/503/504 và resume phần chưa dịch.
- Giữ link qua dịch bằng placeholder `[LINK_n:label]`, render lại anchor inline trong paragraph/quote/bullet sau dịch.
- WordPress automation qua Chrome/Brave/Edge CDP port riêng `9227`: dry-run kiểm tra tab WordPress và paste draft khi sẵn sàng.
- Settings UI cho tài khoản, search, Article Import, 9Router/WordPress status và Tavily key theo quyền.
- Ops Dashboard để kiểm tra Tavily key, LLM health/test, audit logs, system status, 9Router health.
- Script đa nền tảng: Bash cho Linux/macOS/Git Bash, PowerShell cho Windows.
- GitHub Actions CI chạy backend tests, frontend lint và frontend build.

## Kiến trúc nhanh

```text
User
  -> Next.js frontend
  -> FastAPI backend

Search flow:
  /api/v1/search/stream
  -> Context Query Rewriter
  -> Query Analyst / Planner
  -> Tavily first + SearXNG fallback
  -> Evidence Merge / Quality Gate
  -> LLM Final Summary
  -> SSE response

Article Import flow:
  /api/v1/articles/import
  -> Fetch URL
  -> Extract blocks/assets
  -> Download assets
  -> Translate missing text blocks in small batches via 9Router
  -> Build WordPress HTML draft
  -> Dry-run or paste via browser CDP
```

Chi tiết xem [docs/architecture-pipeline.md](docs/architecture-pipeline.md).

## Tech stack

- Backend: FastAPI, Pydantic Settings, HTTPX, SQLAlchemy, Alembic, psycopg, BeautifulSoup, Playwright/CDP.
- Frontend: Next.js 16, React 19, Tailwind CSS 4.
- Search providers: Tavily, SearXNG.
- LLM: OpenAI-compatible API cho search summary; 9Router GPT 5.5 cho Article Import translation.
- Local infra tùy chọn: PostgreSQL, pgAdmin, SearXNG Docker, 9Router, Brave/Chrome CDP.
- CI/CD: GitHub Actions.

## Cấu trúc thư mục

```text
web-agent/
  backend/                 FastAPI backend
  frontend/                Next.js frontend
  config/                  cấu hình local cho infra phụ trợ
  docs/                    tài liệu vận hành/phát triển
  plans/                   kế hoạch triển khai lịch sử
  scripts/                 helper scripts như start_wp_chrome
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

### Clone repo mới

```bash
git clone https://github.com/AnLHN/Web-agent-craw-blog.git
cd Web-agent-craw-blog/web-agent
```

Nếu bạn đang dùng thư mục local có sẵn và muốn đổi remote sang repo mới:

```bash
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/AnLHN/Web-agent-craw-blog.git
git remote -v
```

PowerShell:

```powershell
git remote remove origin 2>$null
git remote add origin https://github.com/AnLHN/Web-agent-craw-blog.git
git remote -v
```

### Linux/macOS/Git Bash

```bash
cp .env.example .env
./setup.sh
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env -Force
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
- 9Router dashboard: `http://localhost:20128/dashboard`
- WordPress browser CDP: `http://127.0.0.1:9227`

## Article Import / Craw Blog

1. Chạy `setup` hoặc `run` để bật backend/frontend.
2. Đảm bảo 9Router đang chạy và có model `cx/gpt-5.5`.
3. Cấu hình `backend/.env`:

```env
APP_ARTICLE_LLM_PROVIDER=9router_openai
APP_9ROUTER_BASE_URL=http://127.0.0.1:20128/v1
APP_9ROUTER_API_KEY=YOUR_9ROUTER_KEY
APP_ARTICLE_OPENAI_MODEL=cx/gpt-5.5
APP_ARTICLE_TRANSLATION_MAX_OUTPUT_TOKENS=8000
APP_ARTICLE_TRANSLATION_MAX_BATCHES_PER_RUN=6
APP_ARTICLE_TRANSLATION_BATCH_SIZE=3
APP_ARTICLE_TRANSLATION_MAX_BATCH_CHARS=8000
```

4. Mở frontend, dùng Article Import để nhập URL bài viết.
5. Bấm **Check 9router** để kiểm tra model/API key.
6. Bấm import để crawl + dịch + build draft.
7. Nếu translation bị `partial`, bấm **Translate** để dịch tiếp phần còn thiếu. Backend chỉ dịch block chưa có `translated_text`.
8. Bấm **Dry Run** để kiểm tra kết nối WordPress tab. Dry Run không paste nội dung.
9. Bấm **Paste Draft** để paste title/content vào WordPress editor.

### WordPress browser automation

Root `.env` hỗ trợ tự mở browser CDP khi setup:

```env
WP_CHROME_AUTO_START=true
WP_CHROME_PORT=9227
WP_CHROME_URL=https://your-site.com/wp-admin/post-new.php
```

Script sẽ ưu tiên Chrome/Brave/Edge. Trên Windows có thể chạy riêng:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_wp_chrome.ps1 -Port 9227 -Url "https://your-site.com/wp-admin/post-new.php"
```

## Cấu hình Tavily key

Tavily là provider search chính. Thêm key qua UI:

1. Mở `http://localhost:3005`.
2. Vào `Cài đặt`.
3. Mở `Tavily Keys`.
4. Dán key và lưu.

Key lưu local ở `backend/config/tavily_keys.json`. Không commit file này nếu chứa key thật.

## Kiểm thử local

Backend:

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
```

Linux/macOS:

```bash
cd backend
../.venv/bin/python -m pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## CI/CD

Workflow hiện tại nằm tại [.github/workflows/ci.yml](.github/workflows/ci.yml).

CI chạy khi `push`, `pull_request` hoặc `workflow_dispatch`:

- Backend job: Python 3.12, install `backend[dev]`, chạy `pytest`.
- Frontend job: Node 24, `npm ci`, `npm run lint`, `npm run build`.

Chuẩn trước khi mở PR:

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest -q
cd ../frontend && npm run lint && npm run build
```

Production/staging local dùng `docker-compose.production.yml`; CD cloud chưa bật vì chưa có target deploy chính thức. Khi có staging/production thật, thêm workflow deploy riêng với GitHub Environments, Secrets và approval production.
Chi tiết xem [docs/ci-cd.md](docs/ci-cd.md).

## Dọn Docker local

```bash
./delete.sh --keep-images
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1 -KeepImages
```

## Tài liệu thêm

- [docs/README.md](docs/README.md): mục lục tài liệu.
- [docs/setup-cross-platform.md](docs/setup-cross-platform.md): setup đa nền tảng.
- [docs/architecture-pipeline.md](docs/architecture-pipeline.md): kiến trúc và pipeline.
- [docs/env-reference.md](docs/env-reference.md): biến môi trường.
- [docs/ci-cd.md](docs/ci-cd.md): CI/CD.

## Ghi chú bảo mật/vận hành

- Không commit `.env`, `backend/.env`, `frontend/.env.local`, logs, API keys, browser profile hoặc dữ liệu import nhạy cảm.
- Rotate key nếu key từng bị paste vào chat/log.
- Không commit `backend/config/tavily_keys.json`, `backend/config/llm_runtime.json` nếu chứa endpoint/key nội bộ.
- Nếu model chạy trên máy khác, backend phải truy cập được `LLM_BASE_URL` hoặc `APP_9ROUTER_BASE_URL`.
- Nếu public SearXNG bị `403/429`, bật SearXNG local bằng Docker.
- Sau khi sửa backend extractor/translation, restart backend và crawl lại URL mới; run cũ vẫn giữ dữ liệu đã extract trước đó.
