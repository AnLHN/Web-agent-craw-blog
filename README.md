# Web Agent: Tavily-first Search + SearXNG Fallback

Du an gom 2 phan:
- backend: FastAPI search pipeline
- frontend: Next.js UI + Tavily key manager + Ops Dashboard + Prompt Manager

## 1) Khoi tao moi truong (khuyen nghi)

### Linux/macOS/Git Bash
```bash
cp .env.example .env
./setup.sh
```

### Windows PowerShell
```powershell
Copy-Item .env.example .env -Force
& "D:\Git\bin\bash.exe" -lc "cd /d/NTC_AI/Code/WebSearch_Tavily/web-agent && ./setup.sh"
```

`setup.sh` se:
- tao `.venv`
- cai dependencies backend/frontend
- dong bo `backend/.env` va `frontend/.env.local` neu chua co
- cap nhat API proxy va CORS theo root `.env`
- auto-start PostgreSQL/pgAdmin/SearXNG local neu bat trong root `.env`
- auto-start backend/frontend neu `AUTO_START_APPS=true`

Luu y Windows:
- Trong PowerShell, lenh `bash` co the tro toi WSL (`C:\Windows\system32\bash.exe`), khac Git Bash.
- Nen chay truc tiep trong cua so Git Bash `MINGW64`, hoac goi dung `D:\Git\bin\bash.exe` nhu vi du tren.

## 2) Quy uoc env de dung lai o may moi

Chi commit file `*.env.example`, khong commit file env thuc te.

Khi clone tren may moi:
1. tao root env: `cp .env.example .env`
2. tao backend env: `cp backend/.env.example backend/.env`
3. tao frontend env: `cp frontend/.env.example frontend/.env.local`
4. chay `./setup.sh`

Chi tiet bien moi truong: xem `docs/env-reference.md`.

## 3) Chay thu cong (neu khong dung auto-start)

### Backend
Linux/macOS/Git Bash:
```bash
cd backend
../.venv/bin/python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8011
```

Windows PowerShell:
```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8011
```

### Frontend
```bash
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3005
```

## 4) Endpoint chinh
- `GET /api/v1/health`
- `POST /api/v1/search`
- `GET /api/v1/keys/tavily`
- `POST /api/v1/keys/tavily`
- `DELETE /api/v1/keys/tavily/{key_id}`
- `GET /api/v1/llm/config`
- `PATCH /api/v1/llm/config`
- `POST /api/v1/ops/searxng/circuit/reset`

## 5) Hanh vi pipeline
1. Tavily-first retrieval.
2. Fallback sang SearXNG khi Tavily fail/quality thap.
3. Query Analyst co 2 mode:
   - `rule` (mau co dinh)
   - `llm` (agent phan tich dong, co fallback ve rule khi LLM loi)
4. LLM tong hop cau tra loi cuoi.
5. Prompt Manager dieu khien system prompt va `Target Output Length`.
6. Output length hien tai uu tien LLM tu viet/rewrite trong ngan sach ky tu, khong uu tien cat thang sau khi sinh.

## 6) Local infra hien tai

Neu root `.env` bat cac bien tuong ung, `setup.sh` se auto-start:

- PostgreSQL: `websearch-pg`, port `5432`
- pgAdmin: `websearch-pgadmin`, URL `http://localhost:5050`
- SearXNG local: `websearch-searxng`, URL `http://127.0.0.1:8080`

SearXNG local duoc dung de fallback khi Tavily disabled/het quota/loi/quality thap. Ly do: public SearXNG instances co the tra `403`, `429`, hoac loi DNS.

## 7) UI roadmap gan nhat

Trang hien tai dang co nhieu khu vuc quan tri nam chung voi search. Viec tiep theo trong plan la tach thanh sidebar tabs ben trai:

- `Search`
- `Tavily Keys`
- `Ops Dashboard`
- `Prompt Manager`

Chi tiet xem `plans/plan-web-search-tavily-searxng-fastapi-nextjs.md`, muc `Update 2026-05-15`.

## 8) Test va verify

### Backend
Linux/macOS/Git Bash:
```bash
../.venv/bin/python -m pytest backend/tests/test_api.py -q
```

Windows PowerShell:
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q
```

### Frontend
```bash
cd frontend
npm run lint
npm run build
```

## 9) Tai lieu bo sung
- Huong dan cross-platform: `docs/setup-cross-platform.md`
- Bang bien moi truong: `docs/env-reference.md`

## 10) PostgreSQL (session/search history)

He thong ho tro luu lich su chat va search trace vao PostgreSQL.

Bien env can thiet (file `backend/.env`):
- `APP_SESSION_STORE_BACKEND=postgres`
- `APP_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/web_search?connect_timeout=5`

Tao schema bang Alembic:

```bash
cd backend
../.venv/Scripts/python.exe -m alembic upgrade head
```

Kiem tra backend dang chay mode Postgres:
- Xem `logs/backend.dev.log` co dong:
  - `session_store_backend= postgres`
  - `store_type= PostgresChatSessionStore`

Luu y:
- Neu `APP_SESSION_STORE_BACKEND=postgres` thi PostgreSQL phai dang chay, neu khong backend se loi ket noi.

## 11) Quy trinh push GitHub "clean"

Truoc khi push:
1. Chay test backend:
```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
```
2. Chay lint/build frontend:
```bash
cd frontend
npm run lint
npm run build
```
3. Kiem tra env khong bi commit:
```bash
git status
```
Dam bao khong co `backend/.env`, `frontend/.env.local` trong staged files.

## 12) CI/CD roadmap (de push production sau)

Trang thai hien tai:
- Chua them workflow CI/CD chinh thuc trong `.github/workflows`.

De xuat tiep theo:
1. CI workflow (`ci.yml`):
   - Trigger: `pull_request`, `push` vao `main`.
   - Jobs:
     - backend test (`pytest`)
     - frontend lint + build (`npm run lint && npm run build`)
2. Optional quality gates:
   - coverage threshold backend.
   - type-check frontend.
3. CD workflow (`deploy.yml`) (phase sau):
   - Trigger sau khi CI pass tren `main`.
   - Deploy staging truoc production.
4. Secret management:
   - Su dung GitHub Secrets cho key/endpoint.
   - Tuyet doi khong commit key that vao repo.
