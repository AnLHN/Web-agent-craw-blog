# Web Search Frontend

Next.js app cho giao dien search, session history, Tavily keys, Ops Dashboard va Prompt Manager.

## Setup

Neu chua co env local:

```bash
cp .env.example .env.local
```

Sau do cai dependency:

```bash
npm install
```

## Run dev

```bash
npm run dev -- --hostname 0.0.0.0 --port 3005
```

Frontend se goi API qua rewrite `/api/v1/*` -> backend host/port theo env:
- `API_PROXY_HOST`
- `API_PROXY_PORT`
- `NEXT_PUBLIC_API_BASE`

## UI hien tai

- Search workspace: nhap query, xem summary, sources, attempts/debug trace.
- Tavily Key Manager: them/xoa/disable key.
- Ops Dashboard: runtime LLM config, health/test, audit/ops controls.
- Prompt Manager: chinh `summary_system_prompt` va `Target Output Length`.

## Roadmap gan nhat

Can tach cac khu vuc quan tri thanh sidebar tabs ben trai de tranh moi thu nam chung tren mot trang:

- `Search`
- `Tavily Keys`
- `Ops Dashboard`
- `Prompt Manager`

Chi tiet xem `../plans/plan-web-search-tavily-searxng-fastapi-nextjs.md`, muc `Update 2026-05-15`.

## Build checks

```bash
npm run lint
npm run build
```

## Note

Gia tri env mac dinh cho local da duoc dinh nghia trong `.env.example`.
