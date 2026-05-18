# Setup đa nền tảng

Tài liệu này hướng dẫn chạy Web Agent trên Linux, macOS, Git Bash và Windows PowerShell.

## Yêu cầu

- Python 3.12 trở lên.
- Node.js 20 trở lên, khuyến nghị Node 24 để khớp CI.
- npm.
- Docker Desktop nếu muốn chạy PostgreSQL, pgAdmin hoặc SearXNG local.
- Git Bash nếu chạy `.sh` trên Windows.

## Script hiện có

| Mục đích | Linux/macOS/Git Bash | Windows PowerShell |
| --- | --- | --- |
| Setup lần đầu | `./setup.sh` | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1` |
| Chạy app | `./run.sh` | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1` |
| Dừng app | `./stop.sh` | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1` |
| Xoá container/image Docker | `./delete.sh` | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1` |
| Xoá container, giữ image | `./delete.sh --keep-images` | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1 -KeepImages` |

File `.ps1` là script PowerShell cho Windows. Nếu muốn gọi ngắn dạng `.\run.ps1`, mở PowerShell trong thư mục `web-agent` và chạy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Lệnh này chỉ áp dụng cho cửa sổ PowerShell hiện tại.

## Setup lần đầu

Linux/macOS/Git Bash:

```bash
cd web-agent
cp .env.example .env
./setup.sh
```

Windows PowerShell:

```powershell
cd web-agent
Copy-Item .env.example .env -Force
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup` sẽ:

- tạo `.venv` nếu chưa có;
- cài dependencies backend;
- cài dependencies frontend;
- tạo `backend/.env` từ `backend/.env.example` nếu chưa có;
- tạo `frontend/.env.local` nếu chưa có;
- đồng bộ CORS, API proxy và feature flags;
- tạo local config files trong `backend/config`;
- tự start PostgreSQL, pgAdmin, SearXNG nếu bật trong root `.env`;
- tự start backend/frontend nếu `AUTO_START_APPS=true`.

## Chạy app

Linux/macOS/Git Bash:

```bash
./run.sh
```

Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

Mặc định:

- Backend: `http://127.0.0.1:8011`
- Frontend: `http://localhost:3005`

## Thêm Tavily API key

Tavily là provider tìm kiếm chính của Web Agent. Người dùng cần tự tạo Tavily API key trước khi search bằng Tavily.

Cách lấy key:

1. Vào Tavily dashboard: `https://tavily.com/`.
2. Mở trang API keys: `https://tavily.com/api-keys`.
3. Tạo hoặc copy key. Theo Tavily docs, key được dùng với header `Authorization: Bearer tvly-YOUR_API_KEY`.

Cách thêm key vào app:

1. Mở frontend `http://localhost:3005`.
2. Bấm `Cài đặt`.
3. Vào `Tavily Keys`.
4. Dán key và lưu.

Key được lưu tại:

```text
backend/config/tavily_keys.json
```

Không commit file này nếu chứa key thật.

Thêm key bằng API nếu cần:

```bash
curl -X POST http://127.0.0.1:8011/api/v1/keys/tavily \
  -H "Content-Type: application/json" \
  -d '{"api_key":"tvly-YOUR_API_KEY","label":"Default key"}'
```

## Dừng app

Linux/macOS/Git Bash:

```bash
./stop.sh
```

Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

Script dừng bằng PID file và dọn thêm process đang listen trên port backend/frontend.

## Dọn Docker

Linux/macOS/Git Bash:

```bash
./delete.sh
```

Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1
```

Mặc định `delete` xoá các container và image khai báo trong `.env`:

- `POSTGRES_CONTAINER_NAME`, `POSTGRES_IMAGE`
- `PGADMIN_CONTAINER_NAME`, `PGADMIN_IMAGE`
- `SEARXNG_CONTAINER_NAME`, `SEARXNG_IMAGE`

Giữ image, chỉ xoá container:

```bash
./delete.sh --keep-images
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\delete.ps1 -KeepImages
```

## Chạy thủ công khi cần debug

Backend trên Windows:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

Backend trên Linux/macOS:

```bash
cd backend
../.venv/bin/python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

Frontend:

```bash
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3005
```

## Lỗi thường gặp

### PowerShell không cho chạy `.ps1`

Dùng lệnh đầy đủ:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

### Không tìm thấy npm trên Windows

Cài Node.js LTS hoặc đảm bảo npm nằm trong `PATH`. Script PowerShell cũng tự tìm npm trong các thư mục phổ biến của Node.js và nvm.

### Port 8011 hoặc 3005 bị chiếm

Chạy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

Nếu vẫn kẹt port do WinNAT/WSL bridge, mở PowerShell Admin:

```powershell
Restart-Service WinNat -Force
```

### Public SearXNG bị 403/429

Nên bật SearXNG local trong `.env`:

```env
SEARXNG_AUTO_START=true
SEARXNG_CONTAINER_NAME=websearch-searxng
SEARXNG_PORT=8080
```

Sau đó chạy lại setup.
