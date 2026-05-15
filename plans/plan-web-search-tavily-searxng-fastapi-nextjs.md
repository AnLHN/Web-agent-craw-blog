# Plan: Web Search Aggregation (Tavily-first, fallback SearXNG) với FastAPI + Next.js

## 1 Mục tiêu task
- Xây dựng hệ thống web search có độ chính xác cao, tốc độ nhanh, ưu tiên chi phí thấp.
- Luồng bắt buộc: mỗi truy vấn phải thử Tavily trước; chỉ chuyển sang SearXNG khi Tavily không dùng được hoặc kết quả không đạt ngưỡng chất lượng.
- Tổng hợp đa nguồn, chấm điểm nguồn, tóm tắt cuối cùng có trích dẫn rõ ràng.
- Thiết kế theo 2 mức tải thực tế: 1k query/ngày và 10k query/ngày.
- Giảm rủi ro bị chặn IP khi dùng SearXNG bằng chiến lược limiter, cache, engine policy, proxy egress, và circuit breaker.

## 2 Phạm vi triển khai
- Backend: FastAPI (orchestrator pipeline, search adapters, ranking, summarization, telemetry).
- Frontend: Next.js (UI nhập query, hiển thị nguồn, confidence score, summary, debug trace rút gọn).
- Data stores:
  - Redis: cache + rate limit + key rotation state + circuit breaker state.
  - PostgreSQL: lịch sử truy vấn, nguồn đã dùng, metrics accuracy/latency.
- Observability: Prometheus + Grafana (hoặc OpenTelemetry + exporter tương đương).

## 3 Kiến trúc pipeline bắt buộc

### 3.1 Luồng xử lý chuẩn (mỗi query)
1. Query normalization (ngôn ngữ, timezone, intent, freshness hint).
2. Tavily Router (ưu tiên tuyệt đối):
   - Chọn API key theo thuật toán xoay vòng có trạng thái.
   - Gọi Tavily search.
   - Kiểm tra tính hợp lệ kết quả: số lượng nguồn, độ đa dạng domain, độ mới.
3. Điều kiện fallback sang SearXNG (chỉ khi cần):
   - Tavily trả về lỗi quota/rate limit/toàn bộ key cạn.
   - Tavily trả kết quả rỗng.
   - Tavily trả kết quả dưới ngưỡng chất lượng (ít nguồn, trùng nhiều, thiếu tín hiệu freshness).
4. Fetch + extract nội dung top nguồn (song song, timeout cứng).
5. Re-rank theo relevance + authority + freshness + consensus.
6. Claim extraction + cross-source verification.
7. Tạo bản tóm tắt cuối cùng có citation + confidence score.
8. Trả response + lưu metrics + cache kết quả theo TTL động.

### 3.2 Thuật toán xoay key Tavily (nhiều key)
- Input: danh sách N key (ví dụ 10 key), trạng thái từng key trong Redis.
- Trạng thái key:
  - status: active | cooling_down | exhausted | unhealthy
  - last_used_at
  - success_rate_5m
  - rpm_window_count
  - daily_estimated_used
  - cooldown_until
- Chính sách chọn key:
  1. Lọc key active và chưa vượt giới hạn local token bucket.
  2. Sắp xếp theo weighted score: ít dùng gần đây + success_rate cao + latency thấp.
  3. Chọn key tốt nhất, lock ngắn để tránh race khi concurrent cao.
  4. Nếu lỗi 429/limit: chuyển key sang cooling_down/exhausted theo policy.
  5. Nếu key thất bại liên tiếp > ngưỡng: unhealthy + backoff.
- Chính sách chuyển qua SearXNG:
  - Khi không còn key đủ điều kiện hoặc Tavily quality < threshold.

### 3.3 SearXNG “nhanh + ít bị ban IP"
- Chỉ dùng khi fallback, không dùng mặc định.
- Bật limiter theo IP người dùng + global limiter.
- Query cache mạnh để giảm truy vấn lặp.
- Engine policy:
  - Nhóm engine ổn định ưu tiên cao.
  - Nhóm engine dễ CAPTCHA đặt trọng số thấp, chỉ gọi khi cần.
- Circuit breaker theo engine:
  - Tự động tắt tạm engine nếu tăng 429/CAPTCHA/timeouts.
- Egress strategy:
  - Có thể dùng proxy pool hợp lệ cho outbound (theo ToS), sticky session ngắn.
- Robot-friendly behavior:
  - jitter delay ngắn, retry bounded, không burst đột ngột.

## 4 Thiết kế theo tải dự kiến

### 4.1 Kịch bản 1k query/ngày
- Trung bình: ~0.012 QPS; peak thực tế nên thiết kế 1-2 QPS.
- Mục tiêu latency p95:
  - Cache hit: < 400ms
  - Cache miss Tavily-first: < 2.5s
  - Fallback SearXNG: < 4.0s
- Hạ tầng đề xuất:
  - 1 backend instance (2 vCPU, 4GB RAM) + autoscale nhẹ.
  - Redis 1 node nhỏ.
  - Postgres 1 node nhỏ.
- Chiến lược quota:
  - Tavily xử lý phần lớn truy vấn.
  - SearXNG fallback cho truy vấn lỗi quota hoặc quality thấp.

### 4.2 Kịch bản 10k query/ngày
- Trung bình: ~0.116 QPS; peak nên thiết kế 5-10 QPS.
- Mục tiêu latency p95:
  - Cache hit: < 300ms
  - Tavily-first: < 2.0s
  - Fallback SearXNG: < 3.5s
- Hạ tầng đề xuất:
  - 3 backend instances (mỗi instance 2-4 vCPU, 4-8GB RAM) + autoscaling.
  - Redis HA hoặc managed Redis.
  - Postgres có read replica (nếu analytics nhiều).
  - Worker queue riêng cho fetch/extract để tránh block API.
- SearXNG:
  - Self-host riêng cụm 2 node + reverse proxy + per-engine breaker.
  - Theo dõi tỷ lệ CAPTCHA/429 theo engine theo thời gian thực.

## 5 Danh sách phase thực hiện chi tiết

## Phase 0 - Discovery và chốt yêu cầu
- Mục tiêu:
  - Chốt KPI: accuracy, freshness, latency, cost/query.
  - Chốt policy fallback Tavily -> SearXNG.
- Bước thực hiện:
  1. Định nghĩa KPI và ngưỡng pass/fail.
  2. Chốt schema response có citations + confidence.
  3. Chốt danh sách engine SearXNG ban đầu.
- Thời gian dự kiến: 0.5 ngày.
- Tài nguyên cần thiết:
  - Tài liệu API Tavily/SearXNG.
  - Bộ truy vấn mẫu đa domain.
- Skills chính:
  - backend-skill, documentation-skill.

## Phase 1 - Backend core FastAPI
- Mục tiêu:
  - Có API /search chạy pipeline cơ bản Tavily-first, fallback SearXNG.
- Bước thực hiện:
  1. Khởi tạo FastAPI project structure.
  2. Viết adapter Tavily + adapter SearXNG + interface thống nhất.
  3. Viết orchestrator pipeline + fallback gate.
  4. Thêm Redis cache + state key rotation.
- Thời gian dự kiến: 1.5 ngày.
- Tài nguyên cần thiết:
  - Redis instance.
  - API keys Tavily.
- Skills chính:
  - backend-skill, logging-skill.

## Phase 2 - Key rotation + quota/rate control
- Mục tiêu:
  - Xoay nhiều key Tavily ổn định, tránh dừng dịch vụ khi key đơn bị limit.
- Bước thực hiện:
  1. Thiết kế bảng trạng thái key trong Redis.
  2. Implement weighted round-robin + token bucket.
  3. Implement cooldown, unhealthy detection, circuit breaker key.
  4. Metrics cho từng key: success_rate, 429_rate, latency.
- Thời gian dự kiến: 1 ngày.
- Tài nguyên cần thiết:
  - Bộ key Tavily hợp lệ.
  - Dashboard metrics.
- Skills chính:
  - backend-skill, testing-skill, logging-skill.

## Phase 3 - Chất lượng kết quả và verification
- Mục tiêu:
  - Tăng độ đúng: re-rank + cross-source verification + confidence score.
- Bước thực hiện:
  1. Re-rank theo relevance/authority/freshness/consensus.
  2. Tách claim từ draft answer.
  3. Verify claim trên nhiều nguồn trước khi xuất kết luận.
  4. Chặn câu trả lời nếu confidence dưới ngưỡng.
- Thời gian dự kiến: 1.5 ngày.
- Tài nguyên cần thiết:
  - Bộ benchmark queries có đáp án chuẩn tham chiếu.
- Skills chính:
  - backend-skill, testing-skill, documentation-skill.

## Phase 4 - Frontend Next.js
- Mục tiêu:
  - UI hiển thị kết quả rõ nguồn, rõ confidence, rõ fallback trace.
- Bước thực hiện:
  1. Tạo trang search chính.
  2. Hiển thị summary + danh sách citations.
  3. Hiển thị badge nguồn chính (Tavily/SearXNG fallback).
  4. Thêm trạng thái loading/streaming/error thân thiện.
- Thời gian dự kiến: 1 ngày.
- Tài nguyên cần thiết:
  - API contract ổn định từ backend.
- Skills chính:
  - frontend-skill, documentation-skill.

## Phase 5 - Hardening SearXNG anti-ban IP
- Mục tiêu:
  - Giảm tối đa khả năng bị block, giữ fallback ổn định.
- Bước thực hiện:
  1. Cấu hình engine tier + trọng số.
  2. Bật limiter, cache, retry budget, jitter.
  3. Bật circuit breaker theo engine.
  4. Theo dõi CAPTCHA/429/timeouts và auto-disable engine xấu.
- Thời gian dự kiến: 1 ngày.
- Tài nguyên cần thiết:
  - SearXNG self-host + reverse proxy.
  - Monitoring dashboard.
- Skills chính:
  - backend-skill, logging-skill, testing-skill.

## Phase 6 - Testing, docs, logs, release readiness
- Mục tiêu:
  - Đảm bảo hệ thống pass test trước khi release.
- Bước thực hiện:
  1. Unit tests: adapters, rotation logic, fallback rules.
  2. Integration tests: end-to-end query flow.
  3. Load tests: profile 1k/day và 10k/day.
  4. Viết tài liệu vận hành + runbook sự cố.
  5. Chuẩn hóa logging/audit trail theo phase.
- Thời gian dự kiến: 1 ngày.
- Tài nguyên cần thiết:
  - Bộ test data + công cụ load test.
- Skills chính:
  - testing-skill, documentation-skill, logging-skill.

## 6 Quy trình bắt buộc cho mỗi phase (theo plan-skill)
Mỗi phase đều phải đi theo chu trình cố định sau, không được bỏ qua:
1. Đọc skill cần thiết cho phase đó.
2. Thực hiện code theo phạm vi phase.
3. Testing phase theo testing-skill, chỉ đi tiếp nếu pass.
4. Cập nhật documentation cho phase theo documentation-skill.
5. Cập nhật log triển khai theo logging-skill.
6. Review gate: chỉ khi pass đầy đủ mới chuyển phase kế tiếp.

## 7 Tiêu chí nghiệm thu
- Luồng search đúng thứ tự: Tavily trước, SearXNG chỉ fallback khi thỏa điều kiện.
- Có key rotation nhiều key Tavily, có cooldown/circuit breaker.
- Có citation và confidence score cho câu trả lời cuối.
- Đạt KPI latency/accuracy/freshness đã chốt ở Phase 0.
- Có đầy đủ test report + documentation + log triển khai.

## 8 Rủi ro và cách giảm thiểu
- Rủi ro: Hết quota/free tier Tavily.
  - Giảm thiểu: cache tốt hơn, query dedupe, fallback SearXNG tự động.
- Rủi ro: SearXNG bị CAPTCHA/ban IP.
  - Giảm thiểu: limiter, engine policy, circuit breaker, proxy hợp lệ, giảm burst.
- Rủi ro: Hallucination/tổng hợp sai.
  - Giảm thiểu: claim verification + confidence gate + citation bắt buộc.
- Rủi ro: Latency tăng khi fallback.
  - Giảm thiểu: timeout budget, async fetch, top-k nhỏ, cache warming.

## 9 Gợi ý skills cần dùng trong toàn task
- Bắt buộc:
  - backend-skill
  - frontend-skill
  - testing-skill
  - documentation-skill
  - logging-skill
- Gợi ý bổ sung (nếu có trong team/tooling):
  - devops/infra skill cho autoscaling và observability.
  - security skill cho quản lý secret và API key rotation an toàn.

## 10 Tổng thời gian ước tính
- Tổng: 6.5 đến 7.5 ngày làm việc (MVP production-ready mức đầu).
- Có thể rút xuống 4.5 đến 5.5 ngày nếu giảm phạm vi verification nâng cao và load test sâu.

## 11 Update 2026-05-12: Multi-agent pre-search pipeline

## Mục tiêu cập nhật
- Thêm bước phân tích truy vấn trước khi search để biến hệ thống thành mô hình multi-agent retrieval.
- Agent đầu vào sẽ xác định “cần tìm gì” thay vì search trực tiếp theo câu hỏi nguyên bản.

## Pipeline mới (chèn trước Tavily/SearXNG)

1. User query intake.

2. Query Analyst Agent (mới):
   - Nhận diện intent và bối cảnh câu hỏi.
   - Mở rộng truy vấn thành nhiều sub-query chất lượng cao.
   - Ví dụ query: “Bạn biết kiến trúc RAG không?” →
     - “RAG architecture overview”
     - “RAG in machine learning”
     - “RAG components: retriever, generator, vector database”
     - “RAG workflow: indexing, retrieval, generation”

3. Query Planner/Grouper Agent (mới):
   - Gom nhóm sub-query theo chủ đề.
   - Loại bỏ truy vấn trùng lặp hoặc nhiễu.
   - Sắp xếp ưu tiên truy vấn theo mục tiêu:
     - định nghĩa
     - thành phần
     - cách hoạt động
     - use-case
     - hạn chế

4. Retrieval Orchestrator (giữ nguyên nguyên tắc Tavily-first):
   - Chạy Tavily-first cho từng sub-query (có key rotation + quality gate).
   - Fallback sang SearXNG khi Tavily fail hoặc chất lượng thấp.

5. Evidence Merge Agent (mới):
   - Hợp nhất kết quả từ nhiều sub-query.
   - Deduplicate nguồn, loại bỏ noise, giữ lại các facts có giá trị.
   - Tạo “evidence pack” gọn và có trace nguồn.

6. LLM Final Answer Agent:
   - Nhận evidence pack đã được tinh gọn.
   - Sinh câu trả lời cuối cùng có:
     - summary
     - citation
     - confidence score

---

## Điều chỉnh yêu cầu kỹ thuật

- Thêm telemetry cho từng stage của agent:
  - `query_expansion_count`
  - `kept_vs_dropped_evidence`
  - `retrieval_coverage_by_subquery`

- Thêm cache 2 lớp:
  - Cache theo user query gốc.
  - Cache theo sub-query để tái sử dụng retrieval.

- Thêm quality gate trước final answer:
  - Nếu coverage của sub-query thấp, trigger thêm 1 vòng retrieval bổ sung (bounded).

---

## Điều chỉnh acceptance criteria

- Hệ thống không được search trực tiếp chỉ với 1 query gốc; bắt buộc phải có bước phân tích và expansion.
- Final answer phải dựa trên evidence đã merge/clean, không dựa trên các kết quả rời rạc.
- Debug trace phải hiển thị được:
  - original query
  - expanded sub-queries
  - provider attempts cho từng sub-query
  - evidence merge summary

---

# 12 Kế hoạch áp dụng thuật toán tối ưu (Balanced Mode)

## Mục tiêu
- Nâng chất lượng câu trả lời nhưng không làm latency tăng đột biến.
- Mặc định ưu tiên cân bằng:
  - độ chính xác cao hơn
  - tốc độ vẫn phù hợp production

---

## Nguyên tắc vận hành

- **Bounded complexity**:
  - Mỗi query chỉ mở rộng tối đa N sub-query.

- **Parallel retrieval**:
  - Các sub-query được search song song trong ngân sách thời gian cố định.

- **Strict time budget**:
  - Mỗi stage có timeout cứng; nếu vượt ngưỡng sẽ fallback nhanh.

- **Cache-first**:
  - Ưu tiên tái sử dụng kết quả từ query gốc và sub-query.

---

## Phase A — Query Analyst Agent (phân tích + mở rộng truy vấn)

### Mục tiêu
- Biến query mơ hồ thành tập sub-query rõ ràng để search đúng ý.

### Implement
1. Tạo service `query_analyst_service` trả về:
   - `normalized_query`
   - `intent`
   - `sub_queries[]`
   - `retrieval_goal[]`

2. Giới hạn:
   - `MAX_SUB_QUERIES = 4` (balanced default)

3. Loại bỏ sub-query trùng lặp bằng similarity threshold.

### Output contract cho orchestrator
- `original_query`
- `expanded_sub_queries`
- `analysis_reasoning_short`

---

## Phase B — Query Planner/Grouper Agent (nhóm + ưu tiên)

### Mục tiêu
- Sắp xếp thứ tự truy vấn con để tối ưu độ phủ và tốc độ.

### Implement
1. Gom nhóm sub-query theo:
   - definition
   - mechanism
   - use-case
   - limitation

2. Gán priority score và loại bỏ query nhiễu.

3. Thiết lập retrieval budget theo độ phức tạp:
   - simple → 2 sub-query
   - medium → 3 sub-query
   - complex → 4 sub-query

---

## Phase C — Multi-query Retrieval Orchestration

### Mục tiêu
- Chạy Tavily-first/fallback SearXNG cho từng sub-query theo cơ chế song song có giới hạn.

### Implement
1. Chạy async concurrency với:
   - `MAX_PARALLEL_SUBQUERY = 2`

2. Time budget cho mỗi sub-query:
   - `SUBQUERY_TIMEOUT_MS = 2200`

3. Tổng retrieval budget:
   - `TOTAL_RETRIEVAL_BUDGET_MS = 4500`

4. Vẫn giữ logic:
   - Tavily-first
   - fallback sang SearXNG khi fail hoặc low-quality

---

## Phase D — Evidence Merge Agent (hợp nhất + tinh gọn)

### Mục tiêu
- Hợp nhất kết quả từ nhiều truy vấn con thành evidence pack:
  - gọn
  - đúng
  - ít trùng lặp

### Implement
1. Deduplicate theo:
   - URL/domain
   - semantic overlap

2. Score evidence theo:
   - relevance
   - authority
   - freshness

3. Loại bỏ low-signal sources trước khi đưa vào final LLM.

4. Tạo `evidence_pack` gồm:
   - `key_findings[]`
   - `citations[]`
   - `dropped_items_summary`

---

## Phase E — Final Answer Agent + Quality Gate

### Mục tiêu
- Sinh câu trả lời cuối cùng dựa trên evidence pack có citation và confidence nhất quán.

### Implement
1. Final LLM chỉ được đọc:
   - `evidence_pack`
   - không đọc raw retrieval rời rạc

2. Nếu:
   - `coverage_score < threshold`
   → trigger thêm 1 vòng retrieval bổ sung (tối đa 1 lần)

3. Nếu vẫn thiếu evidence:
   - trả lời với uncertainty notice rõ ràng

---

## Phase F — Cache 2 lớp + Telemetry

### Mục tiêu
- Duy trì tốc độ nhanh và độ ổn định cao.

### Implement
1. Cache L1 theo query gốc.

2. Cache L2 theo sub-query.

3. Metrics bắt buộc:
   - `query_expansion_count`
   - `subquery_cache_hit_rate`
   - `retrieval_coverage`
   - `evidence_kept_vs_dropped`
   - `p50/p95 latency` cho từng stage

---

## Phase G — Frontend Debug Trace (tối giản nhưng đủ quan sát)

### Mục tiêu
- Hiển thị được vì sao hệ thống trả lời như vậy.

### Implement
1. Hiển thị:
   - original query
   - expanded sub-query

2. Hiển thị provider attempts cho từng sub-query.

3. Hiển thị evidence merge summary:
   - kept
   - dropped

4. Có chế độ bật/tắt debug để tránh làm rối UI chính.

---

## Phase H — Testing và Benchmark trước/sau

### Mục tiêu
- Chứng minh chất lượng tăng nhưng latency vẫn trong ngưỡng chấp nhận được.

### Implement
1. Bộ test A/B:
   - baseline pipeline cũ
   - multi-agent balanced pipeline mới

2. Benchmark trên query set đại diện:
   - simple
   - medium
   - complex

3. KPI pass:
   - answer quality + citation faithfulness tăng ≥ 15%
   - p95 latency không tăng quá 50% khi cache miss
   - cache-hit latency giữ ở mức tương đương hiện tại

---

## Rollout đề xuất

1. Tuần 1:
   - Phase A + B
   - unit test

2. Tuần 2:
   - Phase C + D
   - integration test

3. Tuần 3:
   - Phase E + F
   - telemetry dashboard

4. Tuần 4:
   - Phase G + H
   - canary rollout 10% traffic

---

## Tiêu chí nghiệm thu bổ sung

- Pipeline mới phải có pre-search multi-agent stage hoạt động thực tế.
- Final answer phải được tạo từ evidence pack đã tinh gọn.
- Có benchmark trước/sau để xác nhận hiệu quả.
- Có cờ cấu hình:
  - `PIPELINE_MODE = classic | multi_agent_balanced`
  để rollback nhanh khi cần.

---

# 13 Kế hoạch mở rộng tính năng: Session, Lịch sử, Dashboard Key Tavily, LLM API Management

## Mục tiêu mở rộng
- Bổ sung lớp quản trị vận hành để web-search dùng ổn định cho môi trường team/prod.
- Theo dõi được phiên làm việc, lịch sử truy vấn, tình trạng key Tavily và trạng thái kết nối LLM.
- Có cơ chế audit + observability + quyền hạn để tránh thao tác nhầm khi vận hành thực tế.

## Scope chức năng
- Current Session (phiên hiện tại):
  - Duy trì ngữ cảnh hội thoại/search đang mở.
  - Lưu message theo phiên hiện tại.
  - Resume session khi user quay lại tab.
- Session History (lịch sử các session):
  - Danh sách các session đã có trước đó.
  - Filter/search/pagination theo thời gian/từ khóa.
  - Mở lại (re-open) một session cũ.
- Tavily key dashboard:
  - CRUD key, health, cooldown, usage rate, success/fail trend.
  - Key disable/enable thủ công.
  - Cảnh báo key bất thường.
- LLM API dashboard:
  - Quản lý `APP_LLM_BASE_URL`, model, temperature, max_tokens (optional).
  - Health check endpoint LLM.
  - Test prompt nhanh và hiển thị latency/finish_reason.

## Phase S0 - Data model và migration nền tảng
- Mục tiêu:
  - Chuẩn hóa schema cho session/history/dashboard.
- Bước thực hiện:
  1. Thiết kế bảng Postgres:
     - `chat_sessions` (bảng cha cho mỗi session)
     - `chat_messages` (message trong session hiện tại/đã lưu)
     - `query_histories` (log truy vấn phục vụ analytics/ops)
     - `provider_attempt_histories`
     - `llm_runtime_configs` (optional table nếu muốn dynamic config)
  2. Tạo migration scripts + rollback scripts.
  3. Định nghĩa index cho query nhanh theo `created_at`, `session_id`, `query_hash`.
- Output:
  - Migration chạy được trên local/staging.
- Ước tính:
  - 0.5 ngày.

## Phase S1 - Current Session lifecycle API
- Mục tiêu:
  - Có API quản lý phiên làm việc ổn định.
- Bước thực hiện:
  1. API tạo session hiện tại: `POST /api/v1/chat/sessions`.
  2. API lấy session hiện tại: `GET /api/v1/chat/sessions/{id}`.
  3. API gửi message trong session: `POST /api/v1/chat/sessions/{id}/messages`.
  4. API đóng session: `POST /api/v1/chat/sessions/{id}/close`.
  4. TTL cleanup job (cron/background task).
  5. Gắn `session_id` vào luồng `/search`.
- Output:
  - Mỗi truy vấn có thể truy vết theo session.
- Ước tính:
  - 1 ngày.

## Phase S2 - Session History (danh sách các phiên chat) + replay
- Mục tiêu:
  - Có lịch sử truy vấn và replay phục vụ debug/ops.
- Bước thực hiện:
  1. Lưu message + metadata sau mỗi lượt query/response trong session hiện tại.
  2. Lưu lịch sử truy vấn sau mỗi `/search`:
     - query, normalized query, provider_used, confidence, latency, attempts, source count.
  3. API list session history (danh sách các phiên):
     - `GET /api/v1/chat/sessions?cursor=&q=&from=&to=`.
  4. API detail 1 session history:
     - `GET /api/v1/chat/sessions/{id}` (bao gồm messages).
  5. API replay từ session hoặc message cũ:
     - `POST /api/v1/chat/sessions/{id}/replay`
     - hoặc `POST /api/v1/history/{history_id}/replay` (nếu replay theo query log).
  6. Chính sách retention:
     - ví dụ 30/60/90 ngày theo env.
- Output:
  - Team có thể mở lại truy vấn cũ và so sánh kết quả mới/cũ.
- Ước tính:
  - 1 ngày.

## Phase S3 - Tavily key management dashboard (backend APIs)
- Mục tiêu:
  - Quản trị key Tavily đầy đủ ngoài CRUD cơ bản.
- Bước thực hiện:
  1. Bổ sung API:
     - `PATCH /api/v1/keys/tavily/{id}` (label/status/manual disable)
     - `POST /api/v1/keys/tavily/{id}/cooldown/reset`
     - `GET /api/v1/keys/tavily/metrics`
  2. Tracking metrics theo key:
     - success_rate_5m, fail_rate_5m, p95_latency, last_error_reason.
  3. Rule cảnh báo:
     - fail liên tiếp > N
     - cooldown kéo dài quá T
  4. Audit log thao tác key.
- Output:
  - Quan sát được key nào đang gây lỗi, key nào nên tạm ngưng.
- Ước tính:
  - 1 ngày.

## Phase S4 - LLM API management dashboard (backend APIs)
- Mục tiêu:
  - Quản lý endpoint/model LLM linh hoạt, giảm downtime khi đổi host/model.
- Bước thực hiện:
  1. API runtime config:
     - `GET /api/v1/llm/config`
     - `PATCH /api/v1/llm/config`
  2. API health check:
     - `GET /api/v1/llm/health` (check models endpoint, response time).
  3. API dry-run:
     - `POST /api/v1/llm/test` (prompt mẫu + đo latency + finish_reason).
  4. Policy an toàn:
     - validate base_url, timeout, max token upper bound.
  5. Audit log thay đổi cấu hình LLM.
- Output:
  - Đổi host/model LLM có kiểm soát, có khả năng test ngay tại dashboard.
- Ước tính:
  - 1 ngày.

## Phase S5 - Frontend: Session + History UX
- Mục tiêu:
  - Người dùng thấy rõ phiên và lịch sử truy vấn.
- Bước thực hiện:
  1. Khu vực Current Session:
     - tạo mới / tiếp tục session hiện tại.
     - hiển thị message thread trong session hiện tại.
  2. Sidebar Session History:
     - danh sách các session cũ theo `last_message_at`, có phân trang.
  3. Quick actions:
     - re-open session
     - replay query
     - copy query
     - pin query quan trọng
  4. Detail panel:
     - summary, sources, attempts, debug trace.
- Output:
  - UX tra cứu/đối chiếu lịch sử rõ ràng, hỗ trợ troubleshooting nhanh.
- Ước tính:
  - 1 ngày.

## Phase S6 - Frontend: Ops dashboard cho Tavily key + LLM API
- Mục tiêu:
  - Có màn hình vận hành tập trung cho admin.
- Bước thực hiện:
  1. Tab Tavily Keys:
     - danh sách key + trạng thái realtime
     - action enable/disable/reset cooldown.
  2. Tab LLM Runtime:
     - base_url, model, temperature, max_tokens(optional)
     - nút health check, test run.
  3. Cảnh báo trực quan:
     - key fail spike
     - LLM health fail
  4. Bảo vệ thao tác nguy hiểm:
     - confirm modal + reason note.
- Output:
  - Dashboard vận hành đủ dùng cho support/on-call.
- Ước tính:
  - 1 ngày.

## Phase S7 - Security, RBAC, audit, compliance
- Mục tiêu:
  - Tránh rủi ro khi mở dashboard quản trị.
- Bước thực hiện:
  1. RBAC role:
     - viewer, operator, admin.
  2. API guard cho endpoint nhạy cảm:
     - key edit
     - llm config patch
  3. Secret handling:
     - không trả plaintext key.
  4. Audit trail:
     - user/action/time/diff.
  5. Masking và retention log.
- Output:
  - Hệ thống đạt chuẩn vận hành nội bộ an toàn.
- Ước tính:
  - 1 ngày.

## Phase S8 - Testing, benchmark, rollout
- Mục tiêu:
  - Đảm bảo tính năng mới không phá flow search hiện tại.
- Bước thực hiện:
  1. Unit tests:
     - session service
     - history persistence
     - llm config validator
  2. Integration tests:
     - search with session + history write
     - key dashboard actions
     - llm health/test endpoints
  3. E2E tests frontend:
     - session switch
     - history replay
     - key/llm dashboard flow
  4. Rollout:
     - feature flags:
       - `FEATURE_SESSION_HISTORY`
       - `FEATURE_OPS_DASHBOARD`
       - `FEATURE_LLM_RUNTIME_CONFIG`
  5. Canary 10% traffic, sau đó mở rộng.
- Output:
  - Release an toàn với rollback rõ ràng.
- Ước tính:
  - 1 đến 1.5 ngày.

## Tổng thời gian mở rộng (S0-S8)
- Ước tính: 8.5 đến 9.5 ngày làm việc.
- Nếu rút gọn MVP:
  - ưu tiên S0, S1, S2, S3, S4, S8
  - tổng ~5.5 đến 6.5 ngày.

## Tiêu chí nghiệm thu mở rộng
- Có `current_session` xuyên suốt từ frontend đến backend logs.
- Session History hiển thị đúng danh sách các phiên chat cũ, mở lại ổn định.
- Lịch sử truy vấn trong từng session truy xuất/replay ổn định, có filter theo thời gian.
- Dashboard Tavily key hiển thị health metrics + thao tác vận hành an toàn.
- Dashboard LLM API cho phép health check/test/đổi config có audit.
- Không làm regression pipeline search hiện tại (Tavily-first, fallback SearXNG).

## Update 2026-05-13: Backend phase S0-S3 initial implementation
- S0/S1:
  - Đã thêm local JSON store cho `chat_sessions` và `chat_messages`.
  - Đã có API tạo/list/get session và add message.
- S2:
  - Đã hỗ trợ `session_id` trong `/search`.
  - Mỗi search có `session_id` sẽ lưu user message và assistant message vào current session.
  - Đã có API replay session: `POST /api/v1/chat/sessions/{session_id}/replay`.
- S3:
  - Đã mở rộng Tavily key API:
    - `PATCH /api/v1/keys/tavily/{key_id}`
    - `POST /api/v1/keys/tavily/{key_id}/cooldown/reset`
    - `GET /api/v1/keys/tavily/metrics`
- Verification:
  - Backend test suite: `24 passed`.

## Update 2026-05-13: Phase S4 and S5 implementation
- S4 (LLM API management dashboard - backend APIs):
  - Da them API runtime config:
    - `GET /api/v1/llm/config`
    - `PATCH /api/v1/llm/config`
  - Da them API health check:
    - `GET /api/v1/llm/health`
  - Da them API dry-run:
    - `POST /api/v1/llm/test`
  - Runtime config duoc luu local qua `APP_LLM_RUNTIME_STORE_PATH` (mac dinh `config/llm_runtime.json`).
  - Search pipeline da doc runtime config moi ngay trong `LlmSummaryService`, khong can restart backend khi doi base_url/model.
- S5 (Frontend Session + History UX):
  - Da them Current Session panel tren UI.
  - Da them Session History sidebar (list + open session).
  - Da them quick action `Replay` cho session cu.
  - Da gan `session_id` vao luong `/search` tren frontend de luu thread theo session.
- Verification:
  - Backend test suite: `25 passed`.

## Update 2026-05-13: Phase S6 and S7 implementation
- S6 (Frontend Ops dashboard):
  - Da them `OpsDashboard` tren UI:
    - Tavily metrics va quick actions: enable/disable key, reset cooldown.
    - LLM runtime panel: edit `base_url/model/temperature/max_tokens`, health check, test run.
    - Audit log panel: hien thi su kien thao tac nhay cam gan day.
  - Da mo rong API client cho:
    - `GET /api/v1/keys/tavily/metrics`
    - `PATCH /api/v1/keys/tavily/{id}`
    - `POST /api/v1/keys/tavily/{id}/cooldown/reset`
    - `GET /api/v1/llm/config`
    - `PATCH /api/v1/llm/config`
    - `GET /api/v1/llm/health`
    - `POST /api/v1/llm/test`
    - `GET /api/v1/ops/audit/logs`
- S7 (Security, RBAC, audit):
  - Da them RBAC guard theo role:
    - `viewer` < `operator` < `admin`
    - Bật/tắt qua `APP_RBAC_ENABLED`.
    - Admin co the yeu cau token qua `APP_RBAC_ADMIN_TOKEN`.
  - Da ap dung guard cho endpoint nhay cam:
    - Key write actions: can `operator`.
    - LLM config patch: can `admin`.
    - LLM test: can `operator`.
    - Audit log list: can `admin`.
  - Da them `AuditLogStore` luu su kien vao `APP_AUDIT_LOG_STORE_PATH`.
  - Da update env docs cho RBAC/audit.
- Verification:
  - Backend test suite: `27 passed`.

## Update 2026-05-14: Kế hoạch chuyển Session History sang PostgreSQL + lưu full trace

## Mục tiêu cập nhật
- Chuyển cơ chế lưu lịch sử từ local JSON sang PostgreSQL để vận hành ổn định hơn trong môi trường nhiều user/concurrent.
- Mở rộng phạm vi lưu trữ: không chỉ chat message mà còn lưu đầy đủ:
  - `sources`
  - `pipeline_attempts`
  - `debug_trace`
  - `query_analysis`
  - metadata phục vụ audit/quan sát hiệu năng.

## Thiết kế dữ liệu đề xuất (PostgreSQL)
1. `chat_sessions`
   - `id (uuid pk)`, `title`, `status`, `created_at`, `updated_at`, `last_message_at`, `metadata (jsonb)`.
2. `chat_messages`
   - `id (uuid pk)`, `session_id (fk)`, `role`, `content`, `created_at`, `metadata (jsonb)`.
3. `search_runs`
   - `id (uuid pk)`, `session_id (fk)`, `user_message_id (fk)`, `assistant_message_id (fk)`.
   - `query`, `provider_used`, `summary`, `confidence`, `created_at`.
   - `query_analysis (jsonb)`, `debug_trace (jsonb)`.
4. `search_sources`
   - `id (uuid pk)`, `search_run_id (fk)`, `title`, `url`, `domain`, `snippet`, `score`, `published_date`, `raw (jsonb)`.
5. `pipeline_attempts`
   - `id (uuid pk)`, `search_run_id (fk)`, `provider`, `status`, `reason`, `latency_ms`, `result_count`, `sub_query`, `raw (jsonb)`.

## Điều chỉnh phase triển khai

### Phase S9 - Postgres foundation và migration
- Mục tiêu:
  - Thiết lập PostgreSQL + migration framework.
- Bước thực hiện:
  1. Thêm `SQLAlchemy` + `Alembic`.
  2. Tạo migration tạo bảng `chat_sessions`, `chat_messages`, `search_runs`, `search_sources`, `pipeline_attempts`.
  3. Bổ sung index:
     - `chat_sessions(last_message_at desc)`
     - `chat_messages(session_id, created_at desc)`
     - `search_runs(session_id, created_at desc)`
     - `search_sources(search_run_id)`
     - `pipeline_attempts(search_run_id)`
  4. Thêm env:
     - `APP_DATABASE_URL`
     - `APP_DB_ECHO` (optional)
- Ước tính:
  - 0.5 đến 1 ngày.

### Phase S10 - Dual-write + chuyển đổi an toàn
- Mục tiêu:
  - Chuyển từ JSON store sang Postgres không gây gián đoạn.
- Bước thực hiện:
  1. Tạo repository layer cho session/search history.
  2. Bật `dual-write` tạm thời (ghi cả JSON + Postgres) qua feature flag.
  3. Viết script migrate dữ liệu cũ từ `config/chat_sessions.json` sang Postgres.
  4. So sánh dữ liệu hậu migrate (record count + checksum theo session).
  5. Tắt JSON write sau khi xác nhận ổn định.
- Ước tính:
  - 1 ngày.

### Phase S11 - API/Frontend mở rộng full trace
- Mục tiêu:
  - API và UI đọc được history đầy đủ để replay/debug.
- Bước thực hiện:
  1. Mở rộng API session detail để trả thêm `search_runs`, `sources`, `attempts`, `query_analysis`, `debug_trace`.
  2. Frontend thêm chế độ xem chi tiết theo từng lượt search trong session.
  3. Bổ sung filter thời gian và phân trang cho lịch sử dài.
- Ước tính:
  - 1 ngày.

## Tiêu chí nghiệm thu bổ sung
- Khi user chat lần đầu, hệ thống tự tạo session (nếu chưa có session active) và lưu được đầy đủ vào Postgres.
- Mỗi lần `/search` có thể truy hồi lại đầy đủ:
  - user query
  - assistant summary
  - danh sách sources
  - pipeline attempts
  - query analysis/debug trace.
- Không còn phụ thuộc local JSON cho luồng chính trong môi trường production.

## Update 2026-05-14 (EOD): trạng thái thực tế hôm nay

### Đã hoàn thành
- Backend:
  - Đã thêm và chạy migration PostgreSQL thành công (`chat_sessions`, `chat_messages`, `search_runs`, `search_sources`, `pipeline_attempts`).
  - Đã bật chế độ store Postgres qua env:
    - `APP_SESSION_STORE_BACKEND=postgres`
    - `APP_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/web_search?connect_timeout=5`
  - Đã fix lỗi ghi trace search vào Postgres:
    - lỗi FK `pipeline_attempts.search_run_id` do thứ tự ghi + schema runtime.
    - đã sửa luồng ghi `search_runs` trước, sau đó mới ghi child rows.
  - Đã verify end-to-end qua API `:8011` và kiểm tra count trực tiếp trong DB.
- Frontend/API integration:
  - Đã xử lý mismatch port/proxy chính (`frontend -> backend`) để xóa session hoạt động lại.
  - Đã có cơ chế tự tạo session khi bắt đầu chat/search nếu chưa có session active.
- Tooling:
  - Đã có `setup.sh`, `run.sh`, `stop.sh` cho luồng khởi động/tắt local.

### Chưa hoàn thành / còn lỗi
- Frontend UI/UX:
  - Layout phần chat/session/source/debug trace còn dài, chưa gọn cho màn hình nhỏ.
  - Một số trạng thái loading/error/empty state chưa đồng nhất.
  - Cần rà lại style consistency cho panel Session Thread và Chat Panel.
- Startup orchestration:
  - `setup.sh` chưa tự provision PostgreSQL full-stack theo hướng zero-touch cho mọi máy (đặc biệt khi chưa có Docker/Desktop hoặc chưa pull image).
  - `run.sh/stop.sh` trên Windows + Git Bash vẫn có case process cũ bám port, cần hardening thêm.

### Phase bổ sung mới (đã thêm theo yêu cầu)

#### Phase S12 - Frontend polish + compact debug UX
- Mục tiêu:
  - Làm UI gọn hơn, dễ đọc hơn cho session/chat/results.
- Bước thực hiện:
  1. Chuẩn hóa panel sources/attempts/debug theo collapsible mặc định đóng.
  2. Tối ưu responsive cho desktop + mobile.
  3. Đồng bộ spacing/typography/error states.
  4. Bổ sung visual cue cho session active và message mới nhất.
- Ước tính:
  - 0.5 đến 1 ngày.

#### Phase S13 - Prompt control popup (system prompt + giới hạn tóm tắt)
- Mục tiêu:
  - Có popup cấu hình prompt hệ thống để kiểm soát độ dài output summary.
- Bước thực hiện:
  1. Frontend:
     - Thêm popup/modal "Prompt Settings".
     - Trường `system_prompt` có thể chỉnh sửa.
     - Trường `summary_max_chars` mặc định `512`.
  2. Backend:
     - Lưu runtime config prompt (file/DB tùy mode).
     - Validate hard limit và sanitize input.
  3. LLM pipeline:
     - Inject prompt runtime vào bước summarize.
     - Hậu xử lý cắt gọn an toàn để đảm bảo output <= 512 ký tự (theo config).
  4. Audit:
     - Log thay đổi prompt config (ai đổi, lúc nào, giá trị chính).
- Tiêu chí nghiệm thu:
  - User đổi prompt trên popup -> request mới áp dụng ngay.
  - Summary trả về không vượt `512` ký tự khi bật limit.
  - Có thể tăng/giảm giới hạn qua config nhưng vẫn có guard max an toàn.
- Ước tính:
  - 1 ngày.

#### Phase S14 - Prompt registry + versioning + rollout guard
- Mục tiêu:
  - Quản lý prompt như một cấu phần có version, có test, có rollback nhanh.
- Bước thực hiện:
  1. Thiết kế `prompt_registry` (DB hoặc file có schema rõ ràng):
     - `prompt_key` (vd: `query_analyst`, `final_summarizer`)
     - `version` (vd: `v1`, `v2`)
     - `content`
     - `status` (`draft|active|archived`)
     - `created_by`, `created_at`, `updated_at`
     - `notes` (mục tiêu thay đổi, expected impact).
  2. Runtime config:
     - Thêm mapping `active_prompt_version` theo từng `prompt_key`.
     - Cho phép switch version không cần restart backend.
  3. Guard an toàn:
     - Không cho xóa prompt `active`.
     - Chỉ `admin` mới được promote `draft -> active`.
  4. Rollback nhanh:
     - API `POST /api/v1/prompts/{prompt_key}/rollback?to_version=vX`.
- API đề xuất:
  - `GET /api/v1/prompts`
  - `POST /api/v1/prompts`
  - `PATCH /api/v1/prompts/{id}`
  - `POST /api/v1/prompts/{prompt_key}/activate`
  - `POST /api/v1/prompts/{prompt_key}/rollback`
- Ước tính:
  - 1 ngày.

#### Phase S15 - Prompt eval harness (offline + smoke online)
- Mục tiêu:
  - Mọi thay đổi prompt đều có số liệu trước khi promote production.
- Bước thực hiện:
  1. Tạo bộ `prompt_eval_set.jsonl`:
     - Tối thiểu 100 query đại diện: simple/medium/complex, đa domain, có query tiếng Việt + tiếng Anh.
  2. Định nghĩa metrics:
     - `citation_faithfulness`
     - `coverage_score`
     - `hallucination_rate`
     - `summary_length_compliance`
     - `latency_delta_vs_baseline`.
  3. Script benchmark:
     - Chạy A/B giữa `active` và `candidate` prompt version.
     - Xuất report markdown + json cho dashboard ops.
  4. Gating rule:
     - Chỉ promote khi:
       - quality tăng hoặc giữ ổn định
       - hallucination không tăng
       - latency p95 không vượt ngưỡng đã chốt.
- Ước tính:
  - 1 đến 1.5 ngày.

#### Phase S16 - Prompt observability + canary rollout
- Mục tiêu:
  - Theo dõi hiệu ứng prompt mới theo thời gian thực, giảm rủi ro rollout.
- Bước thực hiện:
  1. Gắn `prompt_version` vào mọi `search_runs` và audit log.
  2. Dashboard theo version:
     - volume
     - quality score
     - error rate
     - p50/p95 latency.
  3. Canary rollout:
     - 10% traffic dùng prompt mới trong 2-4 giờ.
     - Nếu ổn mới tăng 25% -> 50% -> 100%.
  4. Auto-rollback condition:
     - error/latency vượt ngưỡng hoặc quality tụt dưới baseline.
- Ước tính:
  - 0.5 đến 1 ngày.

## Checklist áp dụng nhanh (tuần đầu)
1. Bật S13 trước để có UI chỉnh prompt và limit summary.
2. Triển khai S14 tối thiểu ở mức file-based registry nếu chưa muốn thêm bảng DB.
3. Chuẩn bị eval set nhỏ (30-50 query) để chạy A/B lần đầu.
4. Chỉ cho phép promote prompt qua tài khoản `admin` + bắt buộc ghi reason.
5. Mỗi lần đổi prompt phải có rollback target rõ ràng (version trước đó).

## Update 2026-05-15: trạng thái hiện tại + kế hoạch tách UI thành sidebar tabs

### Đã hoàn thành trong ngày
- Startup/local infra:
  - `setup.sh` đã tự dọn process backend/frontend cũ trước khi start lại.
  - Đã hardening case Windows/Git Bash bị `uvicorn --reload` để lại child process `multiprocessing-fork` giữ port `8011`.
  - Đã thêm hướng xử lý khi WinNAT giữ socket ảo: `Restart-Service WinNat -Force` trong PowerShell Admin.
  - Backend mặc định chạy `127.0.0.1:8011`, frontend chạy `0.0.0.0:3005`.
- PostgreSQL + pgAdmin:
  - `setup.sh` có thể auto-start PostgreSQL container `websearch-pg`.
  - `setup.sh` có thể auto-start pgAdmin container `websearch-pgadmin`.
  - Session/search trace đang chạy bằng `APP_SESSION_STORE_BACKEND=postgres`.
  - Alembic migration đã chạy cho các bảng session/search trace.
- SearXNG fallback:
  - Đã phát hiện public SearXNG instance không ổn định (`403`, `429`, DNS lỗi).
  - Đã thêm local Docker SearXNG container `websearch-searxng`.
  - Đã tạo config local `config/searxng/settings.yml` để bật `format=json`.
  - Đã fix lỗi Docker mount path trên Git Bash bằng `MSYS_NO_PATHCONV=1`.
  - Backend đang trỏ `APP_SEARXNG_BASE_URL=http://127.0.0.1:8080`.
  - Khi toàn bộ Tavily key bị `disabled`, search đã fallback được qua local SearXNG với `provider_used=searxng_fallback`.
- Prompt/output control:
  - Đã có `PromptManagerPopup` ở frontend để chỉnh `summary_system_prompt` và `summary_max_chars`.
  - Backend đã đọc runtime prompt config qua `/api/v1/llm/config`.
  - Đã đổi logic output length: không ưu tiên sinh dài rồi cắt.
  - LLM prompt yêu cầu tự viết câu trả lời hoàn chỉnh trong ngân sách ký tự.
  - Nếu output vượt ngân sách, backend gọi LLM rewrite compact lại trong `summary_max_chars`.
  - Hard cap chỉ còn là lớp bảo vệ cuối cùng/fallback, không phải cơ chế chính.
  - Đã thêm test regression: `test_llm_summary_rewrites_to_length_budget_instead_of_cutting`.
- Frontend hiện tại:
  - Có search workspace, session history, source/result panel.
  - Có Tavily Key Manager.
  - Có Ops Dashboard.
  - Có Prompt Manager popup.
  - Vấn đề còn lại: các phần quản trị đang nằm rải rác/chen trên một màn hình, gây rối UI.

### Cấu hình local hiện tại cần nhớ
- Root `.env`:
  - `POSTGRES_AUTO_START=true`
  - `PGADMIN_AUTO_START=true`
  - `SEARXNG_AUTO_START=true`
  - `SEARXNG_FORCE_RECREATE=true` trong giai đoạn dev để đảm bảo container nhận config mới.
- Backend `.env`:
  - `APP_SESSION_STORE_BACKEND=postgres`
  - `APP_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/web_search?connect_timeout=5`
  - `APP_SEARXNG_BASE_URL=http://127.0.0.1:8080`
  - `APP_FORCE_SEARXNG_TEST_MODE=true` để test fallback khi Tavily disabled.
- URL dev:
  - Frontend: `http://localhost:3005`
  - Backend: `http://127.0.0.1:8011`
  - pgAdmin: `http://localhost:5050`
  - SearXNG local: `http://127.0.0.1:8080`

### Phase S17 - Frontend Admin Sidebar Tabs
- Mục tiêu:
  - Tách toàn bộ phần quản trị khỏi trang search chính.
  - Tạo một sidebar cố định bên trái để điều hướng các tab quản trị.
  - Giảm tình trạng mọi thứ nằm tùm lum trên một trang.
- UI mong muốn:
  - Sidebar nằm bên trái, có các tab:
    - `Search`
    - `Tavily Keys`
    - `Ops Dashboard`
    - `Prompt Manager`
    - Có thể thêm `Sessions/History` nếu cần tách tiếp.
  - Khi chọn tab nào thì nội dung tab đó hiện ở panel chính.
  - Trên mobile, sidebar chuyển thành drawer hoặc top segmented tabs.
- Component đề xuất:
  - `AppShell`
    - Layout tổng: sidebar + main content.
  - `SidebarNav`
    - Danh sách tab, active state, icon/label.
  - `AdminTabContent`
    - Router nội bộ cho từng tab.
  - `TavilyKeyManagerPanel`
    - Tách phần quản lý key khỏi trang search hiện tại.
  - `OpsDashboardPanel`
    - Bọc lại `OpsDashboard`.
  - `PromptManagerPanel`
    - Chuyển từ popup sang panel riêng hoặc vừa panel vừa giữ quick popup.
  - `SearchPanel`
    - Search workspace chính, chỉ giữ phần nhập query/kết quả/session cần thiết.
- Bước thực hiện:
  1. Audit component hiện tại:
     - `SearchWorkspace.tsx`
     - `OpsDashboard.tsx`
     - `PromptManagerPopup.tsx`
     - Các component Tavily key manager hiện đang nằm ở đâu.
  2. Tạo state tab ở cấp workspace/app:
     - `activeTab: "search" | "tavily-keys" | "ops" | "prompts"`.
  3. Tách UI quản trị thành panel riêng, không để lẫn trong search result page.
  4. Đảm bảo feature flags vẫn hoạt động:
     - `NEXT_PUBLIC_FEATURE_OPS_DASHBOARD`
     - `NEXT_PUBLIC_FEATURE_LLM_RUNTIME_CONFIG`
  5. Responsive:
     - Desktop: sidebar trái cố định.
     - Mobile: drawer/top tabs.
  6. Test manual:
     - Search vẫn chạy.
     - Tavily key add/disable/delete vẫn chạy.
     - Ops dashboard đọc metrics/config được.
     - Prompt target output length lưu được và request mới áp dụng.
- Tiêu chí nghiệm thu:
  - Trang search không còn chứa lẫn Tavily/Ops/Prompt settings.
  - Sidebar tab chuyển mượt, không reload toàn app.
  - Mỗi tab có empty/loading/error state riêng.
  - Prompt Manager hiển thị rõ `Target Output Length`, không còn hiểu nhầm là hard cut.
- Ước tính:
  - 0.5 đến 1 ngày.

### Phase S18 - Streaming status + token output qua FastAPI SSE
- Mục tiêu:
  - Thêm luồng stream để frontend thấy status pipeline và token LLM realtime.
- Ghi chú thuật ngữ:
  - Cái cần dùng là `SSE` (Server-Sent Events), không phải SSL.
  - FastAPI có thể trả stream bằng `StreamingResponse` trên cùng backend port `8011`.
- API đề xuất:
  - `POST /api/v1/search/stream`
- Event đề xuất:
  - `status`: `query_analysis_started`
  - `status`: `tavily_started`
  - `status`: `tavily_failed_or_low_quality`
  - `status`: `searxng_fallback_started`
  - `status`: `sources_ready`
  - `status`: `llm_summary_started`
  - `token`: từng token/text chunk từ LLM nếu upstream hỗ trợ `stream=true`
  - `done`: final `SearchResultData`
  - `error`: lỗi có envelope rõ ràng.
- Bước thực hiện:
  1. Tách orchestrator thành generator/event emitter hoặc thêm callback `emit(event)`.
  2. Thêm service gọi OpenAI-compatible `/chat/completions` với `stream=true`.
  3. Frontend đọc stream:
     - Có thể dùng `fetch` streaming thay vì `EventSource` vì cần POST body.
  4. UI hiển thị:
     - status timeline
     - partial answer
     - final sources/attempts khi `done`.
- Ước tính:
  - 1 đến 1.5 ngày.

### Handoff cho lần làm tiếp
- Đọc trước:
  - `README.md`
  - `docs/env-reference.md`
  - `docs/setup-cross-platform.md`
  - file plan này, mục `Update 2026-05-15`.
- Kiểm tra source liên quan frontend:
  - `frontend/src/components/SearchWorkspace.tsx`
  - `frontend/src/components/OpsDashboard.tsx`
  - `frontend/src/components/PromptManagerPopup.tsx`
  - `frontend/src/services/apiClient.ts`
  - `frontend/src/types/api.ts`
- Kiểm tra source liên quan backend:
  - `backend/src/services/search_orchestrator.py`
  - `backend/src/services/llm_summary_service.py`
  - `backend/src/services/searxng_service.py`
  - `backend/src/controllers/search_controller.py`
- Lệnh chạy lại:
  - `./stop.sh`
  - `./setup.sh`
- Lệnh test nhanh:
  - `.\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "rewrites_to_length_budget or fallback_to_searxng" -q`
