# Web Search Backend

FastAPI backend cho he thong search voi luong:

1. Uu tien Tavily truoc.
2. Chi fallback SearXNG khi Tavily khong kha dung hoac quality thap.
3. Dung local LLM OpenAI-compatible de tong hop cau tra loi cuoi.

## Query Analyst Mode

`APP_QUERY_ANALYST_MODE`:

- `rule`: sub-query theo template/rule.
- `llm`: Query Analyst Agent dung LLM de sinh sub-query dong, neu loi se fallback ve rule.

## LLM Runtime Config

Backend dung endpoint OpenAI-compatible:

- `APP_LLM_BASE_URL`, vi du `http://192.168.2.74:8007/v1`
- `POST /chat/completions`

Runtime config doc qua:

- `GET /api/v1/llm/config`
- `PATCH /api/v1/llm/config`

Truong quan trong:

- `summary_system_prompt`: system prompt cho final summarizer.
- `summary_max_chars`: nen hieu la `Target Output Length`.

Output length hien tai khong uu tien cat thang sau khi sinh. Backend se prompt LLM tu viet trong ngan sach ky tu; neu LLM tra qua dai, backend goi rewrite compact de LLM tu rut gon. Hard cap chi la lop bao ve cuoi cung.

## Local SearXNG Fallback

Trong dev, nen dung SearXNG local thay vi public instance:

- Container: `websearch-searxng`
- URL backend: `APP_SEARXNG_BASE_URL=http://127.0.0.1:8080`
- Config local: `../config/searxng/settings.yml`

`setup.sh` co the tu tao/start container nay khi root `.env` bat:

```env
SEARXNG_AUTO_START=true
SEARXNG_PORT=8080
```

## Run Local

Linux/macOS/Git Bash:

```bash
cd backend
../.venv/bin/python -m pip install -e .[dev]
../.venv/bin/python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

Windows PowerShell:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pip install -e .[dev]
..\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8011
```

## Phase H Benchmark A/B

Chay benchmark so sanh `classic` va `multi_agent_balanced`:

```bash
cd backend
../.venv/Scripts/python.exe scripts/benchmark_ab.py --rounds 5
```

Tao artifact benchmark production-readiness dang JSON va Markdown:

```bash
cd backend
../.venv/Scripts/python.exe scripts/benchmark_report.py --rounds 3 --output-dir benchmark-artifacts
```

## Environment

Neu chua co file env:

```bash
cp .env.example .env
```

Danh sach bien day du xem tai `../docs/env-reference.md`.

## PostgreSQL Auth/Session Store + Alembic

Backend ho tro chuyen auth/admin state va session/search trace sang PostgreSQL cho production/staging local.

Bien env lien quan:

- `APP_DATABASE_URL`, vi du `postgresql+psycopg://postgres:postgres@localhost:5432/web_search`
- `APP_SESSION_STORE_BACKEND`:
  - `auto`: co DB URL thi dung Postgres, khong thi dung local JSON.
  - `local`: bat buoc local JSON.
  - `postgres`: bat buoc Postgres.
- `APP_SESSION_STORE_DUAL_WRITE`, mac dinh `false`.
- `APP_AUTH_STORE_BACKEND`:
  - `auto`: dung Postgres khi DB kha dung, fallback local JSON khi dev khong co DB.
  - `local`: bat buoc local JSON.
  - `postgres`: bat buoc Postgres.

Chay migration schema:

```bash
cd backend
../.venv/Scripts/python.exe -m alembic upgrade head
```

Migrate du lieu lich su cu tu JSON sang Postgres:

```bash
cd backend
../.venv/Scripts/python.exe scripts/migrate_chat_sessions_to_postgres.py
```
