# Implementation notes

Tài liệu này ghi lại các điểm triển khai đáng chú ý của Web Agent Craw Blog.

Repository hiện tại: https://github.com/AnLHN/Web-agent-craw-blog.git

## Search Chat

- Tavily là provider ưu tiên.
- SearXNG là fallback khi Tavily lỗi/rate limit hoặc không đạt quality gate.
- Backend stream tiến trình qua SSE ở `POST /api/v1/search/stream`.
- LLM final summary dùng OpenAI-compatible API và runtime config từ Prompt Manager.

## Article Import / Craw Blog

Pipeline hiện tại:

```text
URL
  -> fetch HTML
  -> extract blocks/assets
  -> download assets
  -> translate missing text blocks via 9Router GPT 5.5
  -> build WordPress HTML draft
  -> dry-run/paste through browser CDP
```

Extractor coverage:

- heading: `h1`-`h6`
- paragraph: `p`
- quote: `blockquote`
- list: `ul`, `ol`, fallback `li`
- code block thật: `pre`
- inline code: `code` giữ trong text, không tách thành code block
- image: `img`, lazy attrs, `figure`, `figcaption`
- embed: `iframe`, `video`
- table: `table`
- link: `a` được thay bằng placeholder `[LINK_n:label]`

## Link placeholder contract

Extractor đưa link vào text dạng:

```text
Read the [LINK_1:quantization guide].
```

Metadata lưu URL:

```json
{"id":"LINK_1","text":"quantization guide","href":"https://example.com/docs/quantization"}
```

Model phải giữ nguyên `LINK_1` và có thể dịch label:

```text
Đọc [LINK_1:hướng dẫn lượng tử hóa].
```

Draft builder render lại:

```html
Đọc <a href="https://example.com/docs/quantization" rel="nofollow noopener">hướng dẫn lượng tử hóa</a>.
```

Áp dụng cho paragraph, quote và list/bullet.

## Translation stability

- Provider: `9router_openai`.
- Model mặc định: `cx/gpt-5.5`.
- Batch nhỏ theo số block và tổng ký tự.
- Chỉ dịch block chưa có `translated_text`, nên retry/resume không dịch lại từ đầu.
- Retry transient status: `429`, `500`, `502`, `503`, `504`, timeout/reset.
- Nếu vẫn lỗi, run chuyển `partial`; người dùng bấm Translate để tiếp tục.

## WordPress automation

- Browser CDP mặc định: `http://127.0.0.1:9227`.
- `Dry Run`: kiểm tra kết nối CDP và tab WordPress, không paste.
- `Paste Draft`: paste title/content vào editor.
- Setup có thể tự mở Chrome/Brave/Edge bằng `WP_CHROME_AUTO_START=true`.

## Auth/Admin phase 1

Đã bắt đầu phase Auth/User/Admin bằng migration DB schema nền:

- `users`
- `roles`
- `user_roles`
- `permissions`
- `role_permissions`
- `user_sessions`
- `admin_profiles`
- `admin_audit_events`

Migration seed role mặc định `user`, `admin` và permission codes đã chốt trong plan. Bảng `admin_profiles` tách riêng metadata quản trị khỏi bảng `users`.

## Auth/Admin phase 2

Đã thêm auth API nền tảng:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

Phase này dùng file-backed auth store cho local/dev để frontend có thể tích hợp sớm. Password được hash bằng PBKDF2-HMAC-SHA256; bearer token chỉ lưu dạng hash trong auth store. User đầu tiên đăng ký tự nhận role `admin`, user sau nhận role `user`.

Docs pipeline đã có Mermaid cho:

- Search pipeline.
- Article Import pipeline.
- Auth/RBAC pipeline.
- Deployment pipeline target.

## CI/CD

- CI ở `.github/workflows/ci.yml`.
- Backend: Python 3.12, install `backend[dev]`, `pytest -q`.
- Frontend: Node 24, `npm ci`, lint, build.
- CD chưa bật; khi có staging/production, thêm workflow deploy riêng với GitHub Environments và Secrets.
