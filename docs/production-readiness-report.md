# Production readiness report

Ngày cập nhật: 2026-05-25

## Scope đã hoàn thành

### Auth/RBAC

- Register, login, current user, logout.
- User đầu tiên tự nhận role `admin`, user sau nhận role `user`.
- Bearer session token chỉ lưu dạng hash trong auth store.
- Production auth/admin state dùng `PostgresAuthService` khi `APP_AUTH_STORE_BACKEND=postgres`.
- Local/dev vẫn có file-backed `AuthService` fallback qua `APP_AUTH_STORE_BACKEND=local|auto`.
- Rate limit login/register bằng `APP_AUTH_RATE_LIMIT_WINDOW_SECONDS` và `APP_AUTH_RATE_LIMIT_MAX_ATTEMPTS`.
- Admin UI tách `Cài đặt` thường và `Quản trị`.
- Admin users list, audit monitoring, system status, enable/disable user, make/remove admin.
- Bearer permission enforcement cho:
  - Tavily key mutation: `keys:tavily_manage`.
  - LLM config/test mutation: `llm:config_manage`.
  - Article Import import/translate/dry-run/paste: `article:*` permissions tương ứng.

### Production/deploy readiness

- `GET /api/v1/ready` readiness endpoint.
- Backend structured JSON access logs và `X-Request-Id` response header.
- Backend and frontend Dockerfiles.
- `.dockerignore` cho backend/frontend.
- `docker-compose.production.yml` cho Postgres, backend, frontend.
- `.env.production.example` với placeholder secret an toàn.
- Benchmark report script xuất JSON/Markdown: `backend/scripts/benchmark_report.py`.
- Pipeline diagrams đã cập nhật trong `docs/architecture-pipeline.md`.

## Verification gần nhất

Các lệnh đã chạy:

```bash
python -m pytest web-agent/backend/tests/test_auth_api.py web-agent/backend/tests/test_postgres_auth_service.py web-agent/backend/tests/test_api.py -q
python -m pytest web-agent/backend/tests/test_auth_migration_contract.py -q
npm --prefix web-agent/frontend run build
docker compose --env-file web-agent/.env.production.example -f web-agent/docker-compose.production.yml config
```

Kết quả gần nhất:

- Broader backend Phase 8 subset: `73 passed` (`test_api.py`, `test_auth_api.py`, `test_postgres_auth_service.py`, `test_auth_migration_contract.py`, `test_article_import_contract.py`).
- Benchmark report script: pass, tạo `benchmark-report.json` và `benchmark-report.md`.
- Frontend production build: pass.
- Production compose config validation: pass.

Các checks khác đã chạy trong các slice trước:

- Full backend Article Import/API/auth subset: `64 passed`.
- Docker build backend image: `web-agent-backend:test` pass.
- Docker build frontend image: `web-agent-frontend:test` pass.
- Benchmark report script chạy thử và tạo `benchmark-report.json` / `benchmark-report.md` thành công.

## Benchmark

Tạo artifacts benchmark:

```bash
cd backend
python scripts/benchmark_report.py --rounds 3 --output-dir benchmark-artifacts
```

Artifacts:

- `benchmark-artifacts/benchmark-report.json`
- `benchmark-artifacts/benchmark-report.md`

Script hiện benchmark các endpoint:

- `/api/v1/health`
- `/api/v1/ready`
- `/api/v1/auth/register`
- `/api/v1/auth/login`
- `/api/v1/admin/users`
- `/api/v1/admin/audit-events`
- `/api/v1/admin/system-status`
- `/api/v1/search` với Tavily mock

Article Import live fetch/translate/WordPress timings không chạy mặc định trong benchmark deterministic để tránh phụ thuộc mạng ngoài, quota LLM và Chrome CDP.

## Security checklist

- [x] Không commit env thật hoặc secret thật.
- [x] Production env template dùng placeholder.
- [x] `APP_AUTH_TOKEN_SECRET` bắt buộc đổi khi deploy.
- [x] `POSTGRES_PASSWORD` bắt buộc đổi khi deploy.
- [x] Bearer token lưu hash, không lưu plaintext trong auth store.
- [x] Sensitive admin mutations yêu cầu bearer permission khi RBAC bật.
- [x] Auth login/register có rate limit in-memory.
- [x] Audit log cho thao tác admin nhạy cảm.
- [x] Admin system status không trả secret plaintext.
- [x] Request id trả về qua `X-Request-Id`.

## Phase 8 acceptance status

- [x] Auth/RBAC hoạt động end-to-end với local fallback và Postgres production backend.
- [x] Admin page giám sát users, audit, system status, Tavily keys và LLM runtime config.
- [x] DB migration contract cho auth/admin schema có test.
- [x] Backend tests và frontend production build pass trên subset nghiệm thu gần nhất.
- [x] Benchmark report JSON/Markdown được tạo.
- [x] Pipeline diagrams đã cập nhật.
- [x] Secrets thật không nằm trong repo; production env chỉ có placeholder.
- [x] Không còn blocker high/critical được biết trong phạm vi local production-readiness review.

## Known limitations

- Rate limiter hiện là in-memory; khi chạy nhiều backend replicas cần Redis/shared limiter.
- Compose stack là production/staging baseline local; chưa có cloud-specific manifest hoặc managed secret integration.
- Frontend route model hiện là app shell single page, chưa tách `/login`, `/account`, `/admin/users` thành route riêng.
- WordPress automation phụ thuộc Chrome CDP reachable từ backend container qua `host.docker.internal` hoặc endpoint tương đương.
- Benchmark report dùng mock cho search provider để ổn định CI/local, không thay thế benchmark against live Tavily/SearXNG/LLM.

## Rollback notes

- Docker compose rollback: deploy lại image tag trước đó và giữ nguyên volume `postgres_data`.
- Nếu auth/RBAC gây chặn thao tác trong staging, kiểm tra token đăng nhập và user permission trước; chỉ dùng `APP_RBAC_ENABLED=false` như emergency local/staging bypass, không dùng làm trạng thái production lâu dài.
- Nếu backend không ready, kiểm tra `GET /api/v1/ready`, Postgres healthcheck, `APP_DATABASE_URL`, `APP_AUTH_TOKEN_SECRET`, và volume `backend_config`.
- Nếu Article Import WordPress paste lỗi, kiểm tra `APP_WORDPRESS_CHROME_CDP_URL` và dùng dry-run trước khi paste.

## Next recommended work

1. Thêm Redis/shared rate limiter cho multi-replica production.
2. Tạo cloud deployment manifest hoặc CI deploy workflow theo môi trường thật.
3. Tích hợp managed secret store theo nền tảng deploy thật.
4. Tách frontend protected routes nếu cần UX route-level guard đầy đủ.
