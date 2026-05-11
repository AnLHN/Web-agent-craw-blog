# Web Search Backend

FastAPI backend cho hệ thống search với luồng:
1. Ưu tiên Tavily (nhiều key, xoay vòng)
2. Chỉ fallback SearXNG khi Tavily không khả dụng hoặc chất lượng thấp
3. Dùng local vLLM (OpenAI-compatible API) để tóm tắt kết quả cuối

## LLM local (vLLM)

- Mặc định backend gọi `APP_LLM_BASE_URL=http://localhost:8007/v1`
- Endpoint được dùng: `POST /chat/completions`
- Nếu LLM lỗi hoặc trả rỗng, hệ thống tự fallback về summary extractive

## Run local

```bash
cd backend
/home/ntcai/ntc-hub/web-agent/.venv/bin/python -m pip install -e .[dev]
/home/ntcai/ntc-hub/web-agent/.venv/bin/python -m uvicorn src.main:app --reload --port 8000
```
