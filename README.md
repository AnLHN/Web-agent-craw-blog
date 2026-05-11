# Web Agent: Tavily-first Search + SearXNG Fallback

Du an gom:
- backend: FastAPI pipeline search
- frontend: Next.js UI search + Tavily key manager

## 0) Setup nhanh (tu dong)

```bash
cp .env.example .env
./setup.sh
```

- `setup.sh` se setup Python/Node/venv/dependencies.
- Port backend/frontend duoc doc tu file `.env` o root.
- Mac dinh script se tu bat backend + frontend (2 terminal neu co GUI).

## 1) Chay backend

```bash
cd backend
cp .env.example .env
/home/ntcai/ntc-hub/web-agent/.venv/bin/python -m uvicorn src.main:app --reload --port 8000
```

## 2) Chay frontend

```bash
cd frontend
cp .env.example .env.local
npm run dev
```

## 3) Endpoint chinh
- GET /api/v1/health
- POST /api/v1/search
- GET /api/v1/keys/tavily
- POST /api/v1/keys/tavily
- DELETE /api/v1/keys/tavily/{key_id}

## 4) Hanh vi pipeline
1. Luon thu Tavily truoc.
2. Neu Tavily khong co key, rate-limit, hoac ket qua duoi nguong -> fallback SearXNG.
3. Co cache + limiter + circuit breaker cho nhanh va giam rui ro bi chan o nhanh fallback.

## 5) Test va verify
- Backend tests:
  ```bash
  cd backend
  /home/ntcai/ntc-hub/web-agent/.venv/bin/python -m pytest -q
  ```
- Frontend lint/build:
  ```bash
  cd frontend
  npm run lint
  npm run build
  ```
