# Web Search Backend

FastAPI backend cho hệ thống search với luồng:
1. Ưu tiên Tavily (nhiều key, xoay vòng)
2. Chỉ fallback SearXNG khi Tavily không khả dụng hoặc chất lượng thấp

## Run local

```bash
cd backend
/home/ntcai/ntc-hub/web-agent/.venv/bin/python -m pip install -e .[dev]
/home/ntcai/ntc-hub/web-agent/.venv/bin/python -m uvicorn src.main:app --reload --port 8000
```
