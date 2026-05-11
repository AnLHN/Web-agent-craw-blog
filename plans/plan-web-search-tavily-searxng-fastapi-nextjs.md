# Plan: Web Search Aggregation (Tavily-first, fallback SearXNG) với FastAPI + Next.js

## 1) Mục tiêu task
- Xây dựng hệ thống web search có độ chính xác cao, tốc độ nhanh, ưu tiên chi phí thấp.
- Luồng bắt buộc: mỗi truy vấn phải thử Tavily trước; chỉ chuyển sang SearXNG khi Tavily không dùng được hoặc kết quả không đạt ngưỡng chất lượng.
- Tổng hợp đa nguồn, chấm điểm nguồn, tóm tắt cuối cùng có trích dẫn rõ ràng.
- Thiết kế theo 2 mức tải thực tế: 1k query/ngày và 10k query/ngày.
- Giảm rủi ro bị chặn IP khi dùng SearXNG bằng chiến lược limiter, cache, engine policy, proxy egress, và circuit breaker.

## 2) Phạm vi triển khai
- Backend: FastAPI (orchestrator pipeline, search adapters, ranking, summarization, telemetry).
- Frontend: Next.js (UI nhập query, hiển thị nguồn, confidence score, summary, debug trace rút gọn).
- Data stores:
  - Redis: cache + rate limit + key rotation state + circuit breaker state.
  - PostgreSQL: lịch sử truy vấn, nguồn đã dùng, metrics accuracy/latency.
- Observability: Prometheus + Grafana (hoặc OpenTelemetry + exporter tương đương).

## 3) Kiến trúc pipeline bắt buộc

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

## 4) Thiết kế theo tải dự kiến

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

## 5) Danh sách phase thực hiện chi tiết

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

## 6) Quy trình bắt buộc cho mỗi phase (theo plan-skill)
Mỗi phase đều phải đi theo chu trình cố định sau, không được bỏ qua:
1. Đọc skill cần thiết cho phase đó.
2. Thực hiện code theo phạm vi phase.
3. Testing phase theo testing-skill, chỉ đi tiếp nếu pass.
4. Cập nhật documentation cho phase theo documentation-skill.
5. Cập nhật log triển khai theo logging-skill.
6. Review gate: chỉ khi pass đầy đủ mới chuyển phase kế tiếp.

## 7) Tiêu chí nghiệm thu
- Luồng search đúng thứ tự: Tavily trước, SearXNG chỉ fallback khi thỏa điều kiện.
- Có key rotation nhiều key Tavily, có cooldown/circuit breaker.
- Có citation và confidence score cho câu trả lời cuối.
- Đạt KPI latency/accuracy/freshness đã chốt ở Phase 0.
- Có đầy đủ test report + documentation + log triển khai.

## 8) Rủi ro và cách giảm thiểu
- Rủi ro: Hết quota/free tier Tavily.
  - Giảm thiểu: cache tốt hơn, query dedupe, fallback SearXNG tự động.
- Rủi ro: SearXNG bị CAPTCHA/ban IP.
  - Giảm thiểu: limiter, engine policy, circuit breaker, proxy hợp lệ, giảm burst.
- Rủi ro: Hallucination/tổng hợp sai.
  - Giảm thiểu: claim verification + confidence gate + citation bắt buộc.
- Rủi ro: Latency tăng khi fallback.
  - Giảm thiểu: timeout budget, async fetch, top-k nhỏ, cache warming.

## 9) Gợi ý skills cần dùng trong toàn task
- Bắt buộc:
  - backend-skill
  - frontend-skill
  - testing-skill
  - documentation-skill
  - logging-skill
- Gợi ý bổ sung (nếu có trong team/tooling):
  - devops/infra skill cho autoscaling và observability.
  - security skill cho quản lý secret và API key rotation an toàn.

## 10) Tổng thời gian ước tính
- Tổng: 6.5 đến 7.5 ngày làm việc (MVP production-ready mức đầu).
- Có thể rút xuống 4.5 đến 5.5 ngày nếu giảm phạm vi verification nâng cao và load test sâu.
