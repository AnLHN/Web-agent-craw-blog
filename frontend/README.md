# Web Agent Frontend

Next.js frontend cho Web Agent.

## Vai trò

- Hiển thị trải nghiệm chat tìm kiếm web.
- Sidebar trái quản lý lịch sử chat/session.
- Composer phía dưới gửi câu hỏi tới backend.
- Popup `Cài đặt` gom các manager:
  - Tavily Keys;
  - Ops Dashboard;
  - Prompt Manager.
- Đọc SSE từ `/api/v1/search/stream` để hiển thị trạng thái xử lý và câu trả lời đang tạo.

## Setup

```bash
cp .env.example .env.local
npm install
```

## Chạy dev

```bash
npm run dev -- --hostname 0.0.0.0 --port 3005
```

Frontend gọi API qua rewrite:

- `NEXT_PUBLIC_API_BASE=/api/v1`
- `API_PROXY_HOST=127.0.0.1`
- `API_PROXY_PORT=8011`

## Build checks

```bash
npm run lint
npm run build
```

## UI hiện tại

- Palette xanh + cam.
- Nhãn người dùng bằng tiếng Việt có dấu.
- Ô `Nguồn` trong composer là số kết quả web tối đa dùng làm nguồn cho câu trả lời.
- Replay session đã được gỡ khỏi UI để tránh gây rối cho người dùng thường.

## File chính

- `src/components/SearchWorkspace.tsx`
- `src/components/SearchResultPanel.tsx`
- `src/components/KeyManager.tsx`
- `src/components/OpsDashboard.tsx`
- `src/components/PromptManagerPopup.tsx`
- `src/services/apiClient.ts`
- `src/types/api.ts`
