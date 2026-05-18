# Tài liệu Web Agent

Thư mục này chứa tài liệu vận hành và phát triển cho Web Agent. Nếu bạn mới vào dự án, nên đọc theo thứ tự bên dưới.

## Đường đọc khuyến nghị

1. [Setup đa nền tảng](setup-cross-platform.md): cài dependencies, chạy app, dừng app và dọn Docker.
2. [Kiến trúc và pipeline](architecture-pipeline.md): hiểu luồng xử lý từ câu hỏi người dùng tới câu trả lời cuối.
3. [Biến môi trường](env-reference.md): hiểu `.env`, `backend/.env`, `frontend/.env.local`.
4. [CI/CD](ci-cd.md): hiểu workflow kiểm thử/build trên GitHub Actions.
5. [Task implementation note](task-web-search-implementation.md): ghi chú triển khai lịch sử.
6. [Blog brief](blog-brief.md): bản mô tả ngắn để truyền thông/kể chuyện dự án.

## Thành phần chính

- `frontend/`: giao diện chat Next.js.
- `backend/`: API FastAPI, pipeline search và LLM summary.
- `backend/config/`: local state như Tavily keys, sessions, runtime LLM config, audit logs.
- `.github/workflows/ci.yml`: workflow CI.

## Tavily key

Sau khi setup xong, người dùng cần thêm Tavily API key để dùng provider web search chính.

- Lấy key tại `https://tavily.com/api-keys`.
- Thêm key trong UI: `Cài đặt -> Tavily Keys`.
- Không commit `backend/config/tavily_keys.json` nếu chứa key thật.

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

## Quy ước tài liệu

- Tài liệu dùng tiếng Việt có dấu và UTF-8.
- Các biến môi trường được ghi bằng `UPPER_SNAKE_CASE`.
- Đường dẫn file đặt trong backtick, ví dụ `backend/src/main.py`.
- Các tài liệu hướng dẫn vận hành phải có lệnh cho cả Bash và PowerShell khi phù hợp.
