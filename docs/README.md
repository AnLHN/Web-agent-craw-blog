# Tài liệu Web Agent Craw Blog

Thư mục này chứa tài liệu vận hành và phát triển cho Web Agent Craw Blog.

Repository: https://github.com/AnLHN/Web-agent-craw-blog.git

## Đường đọc khuyến nghị

1. [Setup đa nền tảng](setup-cross-platform.md): cài dependencies, chạy app, dừng app, WordPress browser CDP và dọn Docker.
2. [Kiến trúc và pipeline](architecture-pipeline.md): luồng search và Article Import/Craw Blog.
3. [Biến môi trường](env-reference.md): root `.env`, `backend/.env`, `frontend/.env.local`.
4. [CI/CD](ci-cd.md): GitHub Actions, checklist PR và định hướng deploy.
5. [Task implementation note](task-web-search-implementation.md): ghi chú triển khai lịch sử.
6. [Blog brief](blog-brief.md): mô tả ngắn để truyền thông/kể chuyện dự án.

## Thành phần chính

- `frontend/`: giao diện Next.js cho chat search, Article Import, Ops Dashboard.
- `backend/`: FastAPI API, search pipeline, Article Import extractor/translation/WordPress automation.
- `backend/config/`: local state như Tavily keys, sessions, runtime LLM config, audit logs.
- `scripts/start_wp_chrome.*`: mở Chrome/Brave/Edge với CDP port riêng cho WordPress automation.
- `.github/workflows/ci.yml`: workflow CI.

## Article Import/Craw Blog hiện hỗ trợ

- Crawl URL bài viết và lưu raw/extracted/draft artifacts.
- Extract heading, paragraph, quote, list/bullet, table, code block, image, embed, caption.
- Giữ inline code/API names trong câu, không tách thành code block riêng.
- Giữ link qua dịch bằng placeholder `[LINK_n:label]`, render lại anchor inline sau dịch.
- Dịch theo batch nhỏ qua 9Router GPT 5.5 (`cx/gpt-5.5`) với retry/resume partial.
- Dry-run WordPress để kiểm tra browser CDP/tab editor trước khi paste.
- Paste draft vào WordPress editor qua browser CDP.

## Các lệnh hay dùng

Linux/macOS/Git Bash:

```bash
./setup.sh
./run.sh
./stop.sh
./delete.sh --keep-images
```

Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1 -KeepImages
```

## Tavily key

Sau khi setup xong, thêm Tavily API key để dùng provider web search chính.

- Lấy key tại `https://tavily.com/api-keys`.
- Thêm key trong UI: `Cài đặt -> Tavily Keys`.
- Không commit `backend/config/tavily_keys.json` nếu chứa key thật.

## 9Router / Article translation

Cấu hình chính trong `backend/.env`:

```env
APP_ARTICLE_LLM_PROVIDER=9router_openai
APP_9ROUTER_BASE_URL=http://127.0.0.1:20128/v1
APP_9ROUTER_API_KEY=YOUR_9ROUTER_KEY
APP_ARTICLE_OPENAI_MODEL=cx/gpt-5.5
```

Không commit key thật. Nếu key từng lộ trong chat/log, rotate key.

## Quy ước tài liệu

- Tài liệu dùng tiếng Việt có dấu và UTF-8.
- Biến môi trường ghi bằng `UPPER_SNAKE_CASE`.
- Đường dẫn file đặt trong backtick, ví dụ `backend/src/main.py`.
- Hướng dẫn vận hành nên có lệnh cho cả Bash và PowerShell khi phù hợp.
