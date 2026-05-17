# Kiến trúc và pipeline Web Agent

Tài liệu này mô tả Web Agent đang làm gì, các thành phần chính và luồng xử lý end-to-end.

## 1. Mục tiêu dự án

Web Agent là hệ thống web search dạng chat:

1. Người dùng nhập câu hỏi.
2. Hệ thống phân tích và mở rộng truy vấn.
3. Tavily được ưu tiên để lấy kết quả web.
4. Nếu Tavily không có key, lỗi, rate limit hoặc kết quả chưa đạt chất lượng, hệ thống fallback sang SearXNG.
5. Các nguồn được hợp nhất, lọc trùng và chấm chất lượng.
6. LLM OpenAI-compatible tổng hợp câu trả lời cuối.
7. UI hiển thị tiến trình qua SSE và lưu lịch sử chat/session.

## 2. Thành phần ứng dụng

### Frontend

Thư mục: `frontend/`

- Next.js 16 + React 19.
- Giao diện chat:
  - sidebar lịch sử chat;
  - workspace chat;
  - composer tìm kiếm web;
  - popup Cài đặt.
- Services:
  - `frontend/src/services/apiClient.ts`: gọi REST API và đọc SSE stream.
- Components chính:
  - `SearchWorkspace.tsx`: app shell, chat UI, settings modal.
  - `SearchResultPanel.tsx`: bubble chat, sources, attempts, debug trace.
  - `KeyManager.tsx`: quản lý Tavily keys.
  - `OpsDashboard.tsx`: metrics, LLM health/test, audit logs.
  - `PromptManagerPopup.tsx`: Prompt Manager panel.

### Backend

Thư mục: `backend/`

- FastAPI.
- Controllers:
  - `search_controller.py`
  - `chat_controller.py`
  - `llm_controller.py`
- Orchestrator:
  - `search_orchestrator.py`
- Services:
  - `query_analyst_service.py`
  - `query_planner_service.py`
  - `tavily_service.py`
  - `searxng_service.py`
  - `evidence_merge_service.py`
  - `llm_summary_service.py`
  - `query_cache.py`
  - `key_store.py`
  - `llm_runtime_store.py`
  - `chat_session_store.py`
  - `postgres_chat_session_store.py`

### Local infra tùy chọn

- PostgreSQL: lưu session/search trace.
- pgAdmin: quản trị DB local.
- SearXNG: fallback search local ổn định hơn public instances.

## 3. Pipeline tìm kiếm

```text
POST /api/v1/search hoặc /api/v1/search/stream
  -> Validate session
  -> Query Analyst
  -> Query Planner
  -> Multi-query Retrieval
      -> Tavily first
      -> SearXNG fallback nếu Tavily fail/quality thấp
  -> Evidence Merge
  -> Quality Gate
  -> LLM Summary
  -> Finalize summary
  -> Save chat messages + search run
  -> Return JSON hoặc stream SSE
```

### Bước 1: Query Analyst

File: `backend/src/services/query_analyst_service.py`

Nhiệm vụ:

- chuẩn hóa câu hỏi;
- nhận diện intent như `definition`, `architecture`, `comparison`, `general_exploration`;
- sinh sub-query để tăng coverage.

Mode:

- `rule`: dùng rule/template nội bộ;
- `llm`: gọi LLM để sinh sub-query, fallback về rule nếu LLM lỗi.

### Bước 2: Query Planner

File: `backend/src/services/query_planner_service.py`

Nhiệm vụ:

- ước lượng độ phức tạp: `simple`, `medium`, `complex`;
- chọn budget truy vấn;
- ưu tiên sub-query quan trọng.

### Bước 3: Retrieval

File: `backend/src/services/search_orchestrator.py`

Nhiệm vụ:

- chạy nhiều sub-query song song có giới hạn;
- dùng cache 2 lớp:
  - cache query chính;
  - cache sub-query;
- gọi Tavily trước;
- fallback SearXNG khi cần.

### Bước 4: Tavily-first

File: `backend/src/services/tavily_service.py`

Tavily là provider ưu tiên vì API trả kết quả web trực tiếp và có metadata tốt. Key được quản lý qua `TavilyKeyStore`:

- add/list/delete key;
- mask key;
- chọn key theo trạng thái;
- ghi success/failure;
- cooldown khi rate limit/lỗi.

### Bước 5: SearXNG fallback

File: `backend/src/services/searxng_service.py`

Fallback được dùng khi:

- không có Tavily key khả dụng;
- Tavily trả lỗi/rate limit;
- kết quả Tavily không đạt threshold;
- cần test fallback local.

Hardening:

- throttle QPS;
- circuit breaker;
- backup base URLs;
- local SearXNG Docker khuyến nghị cho dev.

### Bước 6: Evidence Merge

File: `backend/src/services/evidence_merge_service.py`

Nhiệm vụ:

- hợp nhất source từ nhiều query;
- lọc trùng URL;
- giữ nguồn tốt nhất theo top-k/quality;
- xuất số nguồn giữ/lọc để debug.

### Bước 7: Quality Gate

Quality gate quyết định có cần extra retrieval round hay không:

- nếu coverage thấp;
- nếu còn fallback queries;
- nếu cấu hình cho phép extra round.

### Bước 8: LLM Summary

File: `backend/src/services/llm_summary_service.py`

Nhiệm vụ:

- build prompt từ query + sources;
- gọi `/chat/completions` OpenAI-compatible;
- nếu output bị length stop, gọi continuation;
- nếu output vượt target length, gọi rewrite compact;
- fallback deterministic summary nếu LLM lỗi.

Runtime config:

- base URL;
- model;
- temperature;
- max tokens;
- system prompt;
- target output length.

### Bước 9: SSE streaming

Endpoint: `POST /api/v1/search/stream`

Event:

- `status`: trạng thái pipeline;
- `token`: chunk summary để UI hiển thị partial answer;
- `done`: final `SearchResultData`;
- `error`: lỗi có envelope rõ ràng.

Ghi chú: token hiện là chunk từ final summary sau khi LLM hoàn tất. Bước tiếp theo có thể nối trực tiếp upstream `stream=true` nếu model server hỗ trợ ổn định.

## 4. Data và session

Session store có 2 mode:

- local JSON;
- PostgreSQL.

Các phiên chat lưu:

- title;
- messages;
- metadata;
- search runs;
- attempts;
- sources;
- query analysis.

## 5. Feature flags

- `FEATURE_SESSION_HISTORY`
- `FEATURE_OPS_DASHBOARD`
- `FEATURE_LLM_RUNTIME_CONFIG`

Backend dùng prefix `APP_`, frontend dùng `NEXT_PUBLIC_`.

## 6. Observability

Hệ thống có:

- provider attempts trong mỗi response;
- query analysis fields;
- source count/attempt count;
- audit logs cho thao tác nhạy cảm;
- LLM health/test endpoint;
- Tavily key metrics.

## 7. Những lỗi đã hardening

- `APP_LLM_MAX_TOKENS=` rỗng từng làm Pydantic crash; hiện đã parse thành `None`.
- Frontend từng báo `ECONNREFUSED` khi backend crash; nguyên nhân đã được truy ngược về backend config.
- Remote LLM host khác subnet sẽ timeout; cần kiểm tra `curl <base_url>/models` từ máy backend.
- Public SearXNG dễ bị `403/429`; khuyến nghị self-host local.
- Windows/Git Bash có thể giữ port qua process reload/WinNAT; `setup.sh` đã hardening cleanup, docs có hướng dẫn `Restart-Service WinNat -Force`.
