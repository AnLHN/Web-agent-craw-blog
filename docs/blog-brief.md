# Blog brief: Web Agent

Tài liệu này là bản tóm tắt để viết blog/series bài viết về dự án Web Agent.

## 1. One-liner

Web Agent là một ứng dụng tìm kiếm web dạng chat, dùng Tavily làm nguồn chính, SearXNG làm fallback, và LLM local/remote để tổng hợp câu trả lời có nguồn dẫn.

## 2. Vấn đề đặt ra

Khi xây một “web search agent”, chỉ gọi một search API rồi ném kết quả vào LLM thường chưa đủ:

- API search có thể hết quota, rate limit hoặc lỗi.
- Public search fallback dễ bị chặn.
- Một query gốc có thể quá rộng hoặc mơ hồ.
- LLM dễ trả lời dài, thiếu nguồn hoặc bị cắt giữa chừng.
- Người dùng cần xem lịch sử chat, nguồn, pipeline attempts và trạng thái xử lý.

Web Agent giải quyết bằng một pipeline nhiều lớp thay vì một API call đơn giản.

## 3. Các key idea có thể viết thành blog

### 3.1 Tavily-first, SearXNG fallback

Ý tưởng:

- Tavily được ưu tiên vì có API search ổn định và metadata tốt.
- SearXNG dùng làm fallback khi Tavily không khả dụng hoặc kết quả thấp chất lượng.
- Fallback không chỉ dựa trên lỗi mà còn dựa trên quality threshold.

Điểm hay:

- Hệ thống chịu lỗi tốt hơn.
- Có thể chạy khi chưa có Tavily key bằng local SearXNG.
- Dễ debug vì response có `attempts`.

### 3.2 Query Analyst + Query Planner

Ý tưởng:

- Không search thẳng query gốc.
- Query Analyst chuẩn hóa intent và sinh sub-query.
- Query Planner chọn query nào nên chạy trước theo complexity/budget.

Blog angle:

- “Từ một câu hỏi người dùng thành nhiều truy vấn có chiến lược”.
- “Tại sao web search agent cần planner thay vì chỉ gọi search API”.

### 3.3 Multi-query retrieval + cache

Ý tưởng:

- Chạy nhiều sub-query có kiểm soát concurrency.
- Cache query chính và sub-query để giảm request lặp.
- Có timeout cho từng sub-query.

Blog angle:

- “Tối ưu latency và quota khi retrieval nhiều nguồn”.

### 3.4 Evidence Merge

Ý tưởng:

- Nhiều query có thể trả về trùng nguồn.
- Evidence Merge lọc trùng, giữ source tốt nhất, gom nguồn cho LLM.

Blog angle:

- “Lọc trùng và gom bằng chứng trước khi đưa vào LLM”.

### 3.5 Quality Gate

Ý tưởng:

- Nếu nguồn chưa đủ coverage, pipeline có thể chạy extra round.
- Quality gate là lớp quyết định có nên tìm thêm hay không.

Blog angle:

- “Một lớp kiểm định chất lượng trước khi synthesize”.

### 3.6 LLM Summary có guard độ dài

Ý tưởng:

- `summary_max_chars` là target output length, không phải cắt cứng ngay từ đầu.
- Backend prompt LLM tự viết trong ngân sách.
- Nếu quá dài, gọi rewrite compact.
- Nếu LLM lỗi, fallback deterministic summary.

Blog angle:

- “Đừng cắt câu trả lời của LLM giữa chừng: hãy cho nó rewrite có kiểm soát”.

### 3.7 Runtime Prompt Manager

Ý tưởng:

- Đổi system prompt và target output length qua UI.
- Không restart backend.
- Có audit log cho thao tác nhạy cảm.

Blog angle:

- “Prompt như runtime config, không phải hardcode”.

### 3.8 SSE streaming

Ý tưởng:

- `/search/stream` trả status/token/done/error.
- UI biết pipeline đang ở bước nào.
- Người dùng thấy hệ thống đang làm việc thay vì chờ một response im lặng.

Blog angle:

- “Stream trạng thái pipeline cho trải nghiệm agent tốt hơn”.

### 3.9 Chat UI + session history

Ý tưởng:

- UI giống ChatGPT: history bên trái, chat ở giữa, composer dưới cùng.
- Settings popup gom manager để không làm rối workspace.
- Session/search trace lưu local JSON hoặc PostgreSQL.

Blog angle:

- “Từ tool search thành trải nghiệm chat agent”.

### 3.10 Local-first dev setup

Ý tưởng:

- `setup.sh` tạo venv, cài deps, sync env, start services.
- Có thể auto-start PostgreSQL, pgAdmin, SearXNG.
- Hỗ trợ Windows/Git Bash.

Blog angle:

- “Dev experience cho AI app có nhiều service phụ thuộc”.

## 4. Pipeline tóm tắt để đưa vào bài

```text
User question
  -> Chat UI
  -> FastAPI SSE endpoint
  -> Query Analyst
  -> Query Planner
  -> Tavily-first retrieval
  -> SearXNG fallback
  -> Evidence Merge
  -> Quality Gate
  -> LLM Summary
  -> Final answer + sources + attempts
  -> Save session/search trace
```

## 5. Các “ứng dụng con” trong dự án

- Search Chat: trải nghiệm chính cho người dùng.
- Tavily Key Manager: thêm/xóa key, theo dõi trạng thái key.
- Ops Dashboard: metrics Tavily, LLM runtime, health check, test run, audit logs.
- Prompt Manager: chỉnh system prompt và target output length.
- Session History: lịch sử chat/search trace.
- Local Infra Orchestrator: `setup.sh`, `run.sh`, `stop.sh`, Docker local services.
- CI: GitHub Actions test/lint/build.

## 6. Các endpoint đáng nhắc trong blog

- `POST /api/v1/search`: search thường.
- `POST /api/v1/search/stream`: search có SSE.
- `GET /api/v1/keys/tavily`: list keys.
- `POST /api/v1/keys/tavily`: thêm key.
- `GET /api/v1/llm/config`: đọc runtime LLM config.
- `PATCH /api/v1/llm/config`: cập nhật runtime LLM config.
- `GET /api/v1/llm/health`: kiểm tra model endpoint.
- `POST /api/v1/llm/test`: test prompt nhanh.
- `GET /api/v1/chat/sessions`: list session.

## 7. Những bài blog đề xuất

1. Xây web search agent kiểu Tavily-first với SearXNG fallback.
2. Query Analyst và Query Planner: vì sao agent không nên search thẳng query gốc.
3. Evidence Merge và Quality Gate cho RAG/web search.
4. Runtime Prompt Manager cho LLM app.
5. SSE streaming cho trải nghiệm AI agent.
6. Thiết kế UI chat + settings popup cho web search app.
7. Setup local AI stack trên Windows/Git Bash với FastAPI, Next.js, PostgreSQL, SearXNG.

## 8. Trạng thái hiện tại

- Backend tests: 32 tests pass.
- Frontend lint/build pass.
- CI workflow đã có.
- UI đã chuyển sang chat workspace + Settings popup.
- Replay UI đã được gỡ khỏi frontend vì không cần cho người dùng thường.
