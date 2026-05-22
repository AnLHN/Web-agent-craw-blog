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

## CI/CD

- CI ở `.github/workflows/ci.yml`.
- Backend: Python 3.12, install `backend[dev]`, `pytest -q`.
- Frontend: Node 24, `npm ci`, lint, build.
- CD chưa bật; khi có staging/production, thêm workflow deploy riêng với GitHub Environments và Secrets.
