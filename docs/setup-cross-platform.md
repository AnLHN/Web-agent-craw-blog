# Setup Cross-platform

Tai lieu nay mo ta cach khoi tao project tren Linux, macOS, va Windows.

## 1) Yeu cau

- Python >= 3.12
- Node.js >= 20
- npm
- Bash shell

## 2) Khoi tao env tu file mau

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Neu da co file env thi bo qua buoc nay.

## 3) Chay setup script

### Linux/macOS/Git Bash

```bash
./setup.sh
```

### Windows PowerShell

```powershell
& "D:\Git\bin\bash.exe" -lc "cd /d/NTC_AI/Code/WebSearch_Tavily/web-agent && ./setup.sh"
```

`setup.sh` se:
- setup `.venv`
- cai dependency backend/frontend
- cap nhat CORS/API proxy theo root `.env`
- cap nhat feature flags + RBAC + ops env cho backend/frontend
- tao cac file local state trong `backend/config` neu chua co
- auto-start PostgreSQL, pgAdmin, SearXNG local neu bat trong root `.env`
- co the auto-start app neu `AUTO_START_APPS=true`

Luu y Windows:
- Neu chay trong Git Bash `MINGW64`, chi can `./setup.sh`.
- Neu chay tu PowerShell, dung dung Git Bash binary. Lenh `bash` mac dinh co the tro toi WSL va gay khac moi truong/port bridge.

## 4) Chay thu cong neu can

### Backend

Linux/macOS/Git Bash:
```bash
cd backend
../.venv/bin/python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

Windows PowerShell:
```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

### Frontend

```bash
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3005
```

## 5) Xu ly loi thuong gap

### A) body parse error khi goi API bang Git Bash curl voi tieng Viet

Dung PowerShell `Invoke-RestMethod` hoac dung `jq` + `--data-binary` de dam bao UTF-8.

### B) Khong co `frontend/.env.local`

Chay:
```bash
cp frontend/.env.example frontend/.env.local
```

### C) nvm khong ton tai

Neu Node da cai san va dat yeu cau thi setup van tiep tuc.
Neu chua co Node, cai Node.js LTS truoc roi chay lai `./setup.sh`.

### D) Port 8011 van LISTEN nhung PID khong kill duoc

Tren Windows, doi khi WinNAT/WSL bridge giu socket ao. Chay PowerShell Admin:

```powershell
Restart-Service WinNat -Force
```

Sau do kiem tra:

```powershell
Get-NetTCPConnection -LocalPort 8011 -State Listen |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
```

### E) Public SearXNG bi 403/429

Khong nen phu thuoc public SearXNG instance de dev. Bat local SearXNG trong root `.env`:

```env
SEARXNG_AUTO_START=true
SEARXNG_CONTAINER_NAME=websearch-searxng
SEARXNG_FORCE_RECREATE=true
SEARXNG_PORT=8080
```

Sau do chay lai:

```bash
./setup.sh
```
