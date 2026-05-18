# CI/CD

Dự án hiện có CI bằng GitHub Actions. CD chưa bật vì chưa có môi trường deploy chính thức.

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

Mục tiêu: đảm bảo FastAPI backend cài được dependencies và test pass.

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

Backend tests nên mock hoặc tránh phụ thuộc service ngoài như Tavily/LLM thật.

## Quy tắc trước khi mở PR

Nên chạy local:

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
```

```bash
cd frontend
npm run lint
npm run build
```

Trên Linux/macOS đổi Python path thành `../.venv/bin/python`.

## Định hướng CD sau này

Khi có staging/production, nên thêm workflow deploy riêng thay vì trộn vào CI.

Gợi ý pipeline:

1. CI pass trên pull request.
2. Merge vào `develop` deploy lên staging.
3. Merge/tag release trên `main` deploy production.
4. Dùng GitHub Environments để yêu cầu approval trước production.
5. Dùng GitHub Secrets cho token, database URL, model endpoint, Tavily key.

Secrets nên có:

- `TAVILY_API_KEY` hoặc secret store tương ứng.
- `LLM_BASE_URL` nếu deploy cần gọi model remote.
- `DATABASE_URL` cho PostgreSQL production.
- deploy credentials theo nền tảng triển khai.

## Checklist CD đề xuất

- Build Docker image backend.
- Build Docker image frontend hoặc Next.js standalone output.
- Push image lên registry.
- Run database migration bằng Alembic.
- Deploy backend.
- Deploy frontend.
- Health check `/api/v1/health`.
- Smoke test search endpoint với provider mock hoặc key staging.
