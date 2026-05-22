# CI/CD

Dự án dùng GitHub Actions cho CI. Repository mục tiêu:

```text
https://github.com/AnLHN/Web-agent-craw-blog.git
```

CD chưa bật vì chưa có môi trường deploy chính thức. Khi có staging/production, nên thêm workflow deploy riêng thay vì trộn vào CI.

## Workflow hiện tại

File: `.github/workflows/ci.yml`

Trigger:

- `push` vào `main`, `develop`, `feature/**`.
- `pull_request`.
- `workflow_dispatch` để chạy thủ công.

Concurrency:

- Mỗi branch/ref chỉ giữ một pipeline mới nhất.
- Run cũ bị huỷ khi có run mới cùng ref.

## Backend job

Mục tiêu: đảm bảo FastAPI backend cài được dependencies và toàn bộ test backend pass.

Các bước:

1. Checkout source.
2. Setup Python 3.12.
3. Cache pip theo `backend/pyproject.toml`.
4. Install backend:

```bash
python -m pip install --upgrade pip
pip install -e "./backend[dev]"
```

5. Chạy tests:

```bash
cd backend
pytest -q
```

Backend tests phải mock external services hoặc dùng fixture local. Không gọi Tavily, 9Router, LLM thật, WordPress thật trong CI.

## Frontend job

Mục tiêu: đảm bảo Next.js frontend lint và build được.

Các bước:

1. Checkout source.
2. Setup Node 24.
3. Cache npm theo `frontend/package-lock.json`.
4. Install dependencies:

```bash
cd frontend
npm ci
```

5. Lint:

```bash
npm run lint
```

6. Build:

```bash
npm run build
```

## Biến môi trường trong CI

Frontend job set các biến tối thiểu:

- `NEXT_PUBLIC_API_BASE=/api/v1`
- `API_PROXY_HOST=127.0.0.1`
- `API_PROXY_PORT=8011`
- `NEXT_PUBLIC_FEATURE_SESSION_HISTORY=true`
- `NEXT_PUBLIC_FEATURE_OPS_DASHBOARD=true`
- `NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG=true`

Backend tests nên dùng default/test settings và không phụ thuộc service ngoài.

Không đưa secret thật vào workflow YAML. Nếu sau này cần integration/smoke test có secret, dùng GitHub Secrets và Environment protection.

## Quy tắc trước khi mở PR

Chạy local backend:

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
```

Linux/macOS:

```bash
cd backend
../.venv/bin/python -m pytest -q
```

Chạy local frontend:

```bash
cd frontend
npm run lint
npm run build
```

Nếu sửa Article Import/crawl blog, nên kiểm tra thêm:

- Import URL mới sau khi restart backend.
- List/bullet được extract thành `<ul>/<ol>`.
- Link trong paragraph/quote/list được giữ qua placeholder `[LINK_n:label]` và render lại thành `<a>`.
- Inline code không bị tách thành `<pre><code>`.
- Code block thật vẫn giữ nguyên.
- Translation partial có thể bấm Translate để resume phần còn thiếu.
- Dry Run WordPress không paste nội dung; Paste Draft mới paste thật.

Nếu sửa Auth/Admin/RBAC sau này, CI nên có thêm:

- migration test cho bảng `users`, `roles`, `user_roles`, `permissions`, `role_permissions`, `user_sessions`, `admin_profiles`, `admin_audit_events`;
- API tests cho register/login/logout/me;
- permission tests cho user/admin;
- frontend route-guard smoke tests cho `/login`, `/register`, `/admin/users`.

## Chuẩn branch/PR đề xuất

- `main`: nhánh ổn định, release-ready.
- `develop`: tích hợp tính năng trước khi lên `main` nếu cần.
- `feature/<short-name>`: tính năng/sửa lỗi.
- Pull request phải pass CI trước khi merge.
- Không commit `.env`, `backend/.env`, `frontend/.env.local`, logs, browser profile, API key, dữ liệu import nhạy cảm.

## Production deliverables theo yêu cầu cấp trên

Khi chuyển sang production, CI/CD nên tạo hoặc kiểm tra các artifact sau:

- **Completion report**: Markdown tổng hợp scope, test result, benchmark, security checklist, known limitations, rollback.
- **Benchmark report**: Markdown + JSON cho backend latency, search quality/latency, Article Import timings, retry/partial rate.
- **Pipeline diagrams**: Search pipeline, Article Import pipeline, Auth/RBAC pipeline, Deployment pipeline.
- **Usage model**: mô tả user thường, admin/operator, system/CI và failure model.
- **Admin monitoring checklist**: users/roles, audit events, health checks, key/LLM config, Article Import status.

Production gate không pass nếu thiếu auth/RBAC thật, admin monitoring page, migrations, CI green, benchmark report, pipeline diagrams, secret hygiene và security review.

## Định hướng CD sau này

Khi có staging/production, thêm workflow deploy riêng, ví dụ:

1. CI pass trên pull request.
2. Merge vào `develop` deploy staging.
3. Merge/tag release trên `main` deploy production.
4. Dùng GitHub Environments để yêu cầu approval trước production.
5. Dùng GitHub Secrets cho token, database URL, model endpoint, 9Router/Tavily key nếu cần.

Secrets thường cần:

- `DATABASE_URL` cho PostgreSQL production.
- `LLM_BASE_URL` hoặc endpoint model production.
- `TAVILY_API_KEY` hoặc secret store tương ứng.
- `NINEROUTER_API_KEY` / provider key nếu chạy Article Import trên server.
- Deploy credentials theo nền tảng triển khai.

## Checklist CD đề xuất

- Build Docker image backend.
- Build Docker image frontend hoặc Next.js standalone output.
- Push image lên registry.
- Run database migration bằng Alembic.
- Deploy backend.
- Deploy frontend.
- Health check `/api/v1/health`.
- Smoke test search endpoint bằng provider mock/staging key.
- Smoke test Article Import với trang fixture hoặc URL staging.
- Kiểm tra WordPress automation chỉ chạy trong môi trường có browser CDP được cấu hình rõ ràng.
