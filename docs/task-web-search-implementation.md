# Task Documentation: Web Search Aggregator (FastAPI + Next.js)

## Thoi gian
- Bat dau: 2026-05-11
- Hoan thanh phase implementation MVP: 2026-05-11

## Muc tieu da dat
- Da dung backend FastAPI voi pipeline Tavily-first, fallback SearXNG.
- Da dung frontend Next.js de search va quan ly Tavily keys.
- Da chuan hoa response schema cho endpoint thanh cong va loi.
- Da test luong hien tai voi SearXNG fallback (khong can key Tavily).

## Ket qua theo phase

### Phase 0 - Discovery va chot yeu cau
- Chot yeu cau: Tavily uu tien tuyet doi; fallback SearXNG khi can.
- Chot output: summary + sources + confidence + attempts.

### Phase 1 - Backend core FastAPI
- Tao cau truc backend theo skill:
  - src/controllers
  - src/routes
  - src/services
  - src/models
  - src/utils
  - config
  - tests
- Implement endpoint:
  - GET /api/v1/health
  - POST /api/v1/search
  - GET /api/v1/keys/tavily
  - POST /api/v1/keys/tavily
  - DELETE /api/v1/keys/tavily/{key_id}

### Phase 2 - Key rotation va fallback policy
- Implement key store file-based cho Tavily:
  - add/list/delete key
  - select key theo score (last_used + success_rate)
  - mark success/failure/rate-limit cooldown
- Orchestrator logic:
  - Thu Tavily truoc
  - Danh gia quality threshold
  - Fallback SearXNG khi khong dat

### Phase 3 - Response quality va schema
- Data model da co:
  - attempts theo provider
  - summary extractive
  - confidence score
  - citations (sources)
- Them global exception handlers de tra response schema thong nhat cho:
  - validation errors
  - HTTP errors
  - unexpected errors

### Phase 4 - Frontend Next.js
- Build UI gom:
  - Search form
  - Tavily key manager
  - Summary + sources + pipeline attempts
- Co khu vuc add key de test Tavily sau nay.
- Trong hien tai (chua key), he thong van test duoc luong SearXNG fallback.

### Phase 5 - Testing
- Backend tests: 11/11 pass.
- Frontend lint: pass.
- Frontend production build: pass.

### Phase 6 - SearXNG hardening cho fallback
- Da them cache theo query (TTL) de giam truy van lap.
- Da them throttle theo QPS cho fallback SearXNG.
- Da them circuit breaker khi fallback gap loi lien tiep.
- Da them fallback nhieu SearXNG instance khi instance chinh tra rong/that bai.
- Da them test cache hit de dam bao lan query thu 2 khong goi provider lai.
- Da chuan hoa no-results response: tra success=true, data co attempts chi tiet, khong vo schema loi.
- Da bo sung test tang cuong cho pipeline:
  - Tavily du chat luong thi khong fallback sang SearXNG.
  - Tavily duoi nguong chat luong thi bat buoc fallback sang SearXNG.
  - Tavily key invalid (401) khong retry lap vo hanh vi cham, fallback nhanh hon.

## Ket qua live-check bang request that
- Da test request that qua localhost API (khong mock provider).
- Scenario khong Tavily key:
  - Pipeline skip Tavily dung nhu thiet ke.
  - SearXNG fallback da duoc goi lan luot nhieu instance.
  - Ket qua thuc te tren may hien tai: cac instance SearXNG tra 403/429/network error nen khong lay duoc source.
- Scenario co Tavily key tam (invalid key de test thu tu pipeline):
  - Tavily duoc uu tien goi truoc.
  - Tavily tra 401 va key bi danh dau unhealthy, khong bi retry qua nhieu nhu truoc.
  - Sau do fallback sang SearXNG.

## Danh gia chat luong hien tai
- Logic pipeline va thu tu provider: dung.
- Response schema va attempts telemetry: dung.
- Do dung/noi dung cuoi khi chay live hien tai: chua dat do phu du lieu do provider fallback bi chan tren egress hien tai.
- Dieu kien de dat chat luong cao trong van hanh that:
  - Can Tavily key hop le.
  - Nen co SearXNG self-host/proxy rieng on dinh thay vi phu thuoc instance cong cong.

## Cac kho khan gap phai va cach giai quyet
1. ENOSPC khi cai package npm.
- Nguyen nhan: /home day dung luong.
- Xu ly: xoa cache npm va pip de giai phong bo nho.

2. pip trong .venv bi loi module noi bo.
- Nguyen nhan: pip state khong on dinh.
- Xu ly: chay ensurepip --upgrade roi cai lai dependencies.

3. pyproject hatch editable install bi fail.
- Nguyen nhan: chua khai bao wheel packages.
- Xu ly: them [tool.hatch.build.targets.wheel] packages = ["src"].

## Danh sach endpoint response schema
- Tat ca endpoint tra envelope:
  - success
  - data
  - error
  - meta

## Tinh trang hien tai
- Luong SearXNG fallback hoat dong va da test tu dong.
- Luong Tavily-first da san sang, can ban them key tren frontend de kich hoat va test live.
- Da bo sung CI/CD co ban: backend tests + frontend lint/build qua GitHub Actions.
- Da bo sung root .gitignore va .env.example cho backend/frontend.
- Da bao phu schema loi cho ca truong hop 404 route not found.

## Huong dan chay nhanh
1. Backend
- cd backend
- /home/ntcai/ntc-hub/web-agent/.venv/bin/python -m uvicorn src.main:app --reload --port 8000

2. Frontend
- cd frontend
- npm run dev

3. Cau hinh frontend -> backend
- NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
