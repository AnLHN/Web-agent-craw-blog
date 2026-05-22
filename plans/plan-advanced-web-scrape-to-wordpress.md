# Plan: Advanced Web Scrape to WordPress Publishing Pipeline

## 1. Mục tiêu

Thêm một tool nâng cao cho Web Agent có khả năng nhận trực tiếp URL bài viết, cào đúng nội dung từ URL đó, tách text/media/code, dịch hoặc biên tập lại theo thuật ngữ chuyên ngành, rồi hỗ trợ đưa bài vào WordPress qua Chrome automation.

Use case chính:

- Mỗi ngày xử lý khoảng 3-4 bài, ưu tiên chất lượng hơn throughput.
- Người vận hành đưa danh sách URL nguồn cụ thể.
- Hệ thống không search lan man, không lấy bài khác ngoài link được giao.
- Bài đầu ra có thể dùng để đăng blog WordPress, giữ ảnh/code/block quote cần thiết và ghi rõ nguồn.

## 2. Phạm vi

### In scope

- Backend tool nhận URL thô và tạo `article_import_run`.
- Fetch HTML đúng URL được chỉ định.
- Extract nội dung chính:
  - title
  - author nếu có
  - publish/update date nếu có
  - main text
  - headings
  - image blocks
  - code/pre/bash blocks
  - tables hoặc embedded content ở mức metadata
- Download ảnh về local storage hoặc object storage.
- Tách non-text blocks khỏi phần text để agent xử lý đúng loại dữ liệu.
- Agent dịch/biên tập nội dung với glossary thuật ngữ chuyên ngành.
- Sinh draft bài WordPress:
  - title tiếng Việt
  - slug gợi ý
  - excerpt
  - content dạng block/HTML/Markdown
  - tags/categories gợi ý
  - source attribution
- Mở Chrome bằng remote debugging port riêng và tự paste draft vào WordPress editor.
- Có chế độ preview/dry-run trước khi paste hoặc publish.

### Out of scope giai đoạn đầu

- Auto-publish không cần người duyệt.
- Crawl toàn site hoặc tự phát hiện bài mới.
- Bypass paywall, login bất hợp pháp, CAPTCHA, hoặc nội dung bị cấm bởi robots/ToS.
- Xử lý khối lượng lớn kiểu scraping farm.

## 3. Nguyên tắc vận hành

- Chỉ scrape URL do người dùng cung cấp.
- Tôn trọng robots.txt, điều khoản nguồn, rate limit và bản quyền.
- Luôn lưu raw snapshot để audit nhưng không dùng raw HTML làm final content trực tiếp.
- Mọi bài WordPress đi qua bước review trước khi publish.
- Nếu nguồn có license hạn chế, hệ thống chỉ tạo summary/brief thay vì tái xuất bản dài.
- Media tải về phải giữ metadata nguồn: original URL, alt text, caption nếu có.
- Khi Auth/RBAC được triển khai, Article Import cần kiểm permission:
  - `article:import` cho crawl URL;
  - `article:translate` cho dịch tiếp;
  - `article:wordpress_dry_run` cho kiểm tra WordPress tab;
  - `article:wordpress_paste` cho paste thật vào WordPress, mặc định chỉ admin/operator được cấp quyền.

## 4. Kiến trúc pipeline đề xuất

```text
User URL list
  -> Article Import API
  -> URL Validator + robots/ToS guard
  -> Raw Fetcher
  -> Content Extractor
  -> Block Classifier
      -> text blocks
      -> image blocks
      -> code/bash/pre blocks
      -> tables/embeds/unknown blocks
  -> Asset Downloader
  -> Translation/Rewrite Agent
  -> WordPress Draft Builder
  -> Review Preview
  -> Chrome WordPress Automator
  -> Save run trace + status
```

## 4.1. Quan hệ với Web Search hiện tại

Article Import là một module mới nằm trong Web Agent hiện tại, không thay thế Search Chat và không dùng Tavily/SearXNG để tìm bài.

Phân chia:

```text
Web Agent
  -> Search Chat hiện có
      -> user query
      -> Tavily
      -> SearXNG fallback
      -> Evidence Merge
      -> LLM Summary

  -> Article Import mới
      -> user-provided URL
      -> scrape đúng URL
      -> extract blocks/assets/code/list/link placeholders
      -> 9Router GPT 5.5 dịch/rewrite theo batch nhỏ
      -> WordPress draft/paste
```

### Dùng lại từ Web Search cũ

Tận dụng các phần nền đã có:

- FastAPI app structure.
- Router/controller pattern trong backend.
- Service layer pattern.
- Settings/env config pattern.
- LLM runtime/config pattern, nhưng prompt phải tách namespace `article.*`.
- Audit log pattern cho thao tác nhạy cảm.
- Session/history hoặc Postgres store nếu cần lưu import runs.
- SSE/status streaming pattern để hiển thị tiến trình import realtime.
- Error response envelope và API response helpers.
- Frontend Next.js app shell/settings modal/component style.
- Ops Dashboard style để sau này thêm metrics Article Import.
- Test setup hiện có của backend/frontend.

### Không dùng lại trực tiếp

- Không dùng Tavily/SearXNG cho Article Import vì input đã là URL cụ thể.
- Không dùng Evidence Merge của Search Chat làm core logic vì Article Import xử lý một bài nguồn theo block order, không merge nhiều search result.
- Không dùng chung prompt `search.summary`.
- Không dùng cache search query làm cache article raw HTML nếu chưa có key/schema riêng.

### Có thể dùng lại có điều kiện

- `llm_summary_service.py` chỉ nên được tham khảo pattern gọi LLM, không nhét logic article vào đó.
- Prompt Manager dùng lại UI/service pattern, nhưng cần `prompt_key` riêng.
- Chat session store có thể lưu history import nếu UI cần, nhưng import run nên có schema riêng.
- SSE endpoint pattern có thể tái dùng để stream:
  - `fetch_started`
  - `extract_done`
  - `assets_downloaded`
  - `translation_started`
  - `draft_ready`
  - `wordpress_pasted`

## 5. Data model đề xuất

### `article_import_runs`

- `id`
- `source_url`
- `status`: `queued | fetched | extracted | translated | draft_ready | pasted | failed`
- `source_domain`
- `source_title`
- `source_author`
- `source_published_at`
- `raw_snapshot_path`
- `extracted_json_path`
- `draft_json_path`
- `wordpress_post_id` nullable
- `created_at`, `updated_at`
- `error_message`

### `article_blocks`

- `id`
- `run_id`
- `order_index`
- `block_type`: `heading | paragraph | image | code | table | quote | embed | unknown`
- `source_text`
- `translated_text`
- `language_hint` cho code/text
- `asset_id` nullable
- `metadata`

### `article_assets`

- `id`
- `run_id`
- `source_url`
- `local_path`
- `mime_type`
- `width`, `height`
- `alt_text`
- `caption`
- `checksum`
- `download_status`

### `domain_extraction_profiles`

- `domain`
- `strategy`: `readability | custom_css | playwright_rendered`
- `include_selectors`
- `exclude_selectors`
- `notes`

## 6. Tool/API mới

### Backend endpoints

- `POST /api/v1/articles/import`
  - Input: `{ "url": "...", "mode": "draft", "target_language": "vi" }`
  - Tạo import run và chạy pipeline.

- `GET /api/v1/articles/import/{run_id}`
  - Trả status, extracted blocks, assets, draft preview.

- `POST /api/v1/articles/import/{run_id}/translate`
  - Chạy lại bước dịch/biên tập với prompt hoặc glossary mới.

- `POST /api/v1/articles/import/{run_id}/wordpress/paste`
  - Mở/kết nối Chrome debugging port và paste vào WordPress editor.

- `POST /api/v1/articles/import/{run_id}/wordpress/dry-run`
  - Kiểm tra WordPress editor có sẵn sàng không, không paste.

### Frontend view đề xuất

Thêm một tab trong Settings hoặc workspace riêng:

- `Article Import`
  - URL input
  - button `Fetch`
  - block preview: text/image/code/table
  - glossary selector
  - translated draft preview
  - WordPress target URL
  - `Dry Run`
  - `Paste Draft`

## 7. Scrape đúng URL nguồn

### Fetch strategy

1. Dùng HTTP fetch trước:
   - `httpx`
   - timeout cứng
   - redirect policy rõ ràng
   - user-agent định danh app

2. Nếu HTML render bằng JS hoặc thiếu article body:
   - fallback Playwright headless
   - chờ selector article/main
   - lưu rendered HTML snapshot

3. Nếu nguồn lỗi:
   - lưu failure reason
   - không retry quá nhiều
   - không tự đổi URL sang bài liên quan.

### Extract strategy

Ưu tiên thư viện/parser có sẵn:

- `readability-lxml` hoặc `trafilatura` cho article body.
- `BeautifulSoup`/`lxml` để giữ block order.
- Domain profile riêng nếu extractor tổng quát lấy sai.

Output extractor phải là structured blocks, không phải một chuỗi text lớn.

## 8. Tách text, ảnh, code và block đặc biệt

### Text blocks

- Heading giữ cấp H1/H2/H3.
- Paragraph giữ thứ tự.
- Quote giữ metadata nếu có.
- Link được giữ dạng `{ text, href }` để agent có thể quyết định giữ hoặc bỏ.

### Image blocks

- Tách khỏi text.
- Lưu:
  - source URL tuyệt đối
  - alt text
  - caption
  - vị trí trong bài
- Download về `data/article_assets/{run_id}/`.
- Tạo manifest để WordPress upload hoặc paste.

### Code/Bash blocks

- Tách `pre`, `code`, fenced code.
- Detect language:
  - shebang
  - class name như `language-bash`
  - nội dung có `$`, `sudo`, `npm`, `python`, `docker`
- Không dịch code.
- Chỉ dịch phần caption/giải thích xung quanh code.
- Khi build draft, giữ code bằng WordPress code block hoặc HTML `<pre><code>`.

### Unknown blocks

- Không ném bỏ im lặng.
- Lưu metadata và hiển thị trong preview để người vận hành quyết định.

## 9. Translation/Rewrite Agent

### Mục tiêu

- Dịch hoặc biên tập lại sang tiếng Việt tự nhiên.
- Giữ đúng thuật ngữ chuyên ngành.
- Không bóp méo claim kỹ thuật.
- Không dịch tên sản phẩm, API, command, class, function, model, filename.

### Prompt Manager riêng cho Article Import

Không dùng chung prompt của web search summary hiện tại. Chỉ dùng lại cơ chế quản lý prompt/config đã có trong Web Agent, nhưng phải tách prompt theo namespace và mục đích.

Nguyên tắc:

- `Prompt Manager` là framework quản lý prompt.
- Mỗi pipeline có prompt riêng.
- Search pipeline và Article Import pipeline không được dùng chung prompt runtime.
- Mọi thay đổi prompt Article Import không được làm đổi hành vi của Search Chat.

Prompt key đề xuất:

```text
search.query_analyst
search.summary
article.translate
article.rewrite
article.metadata
article.term_review
article.wordpress_style
```

Các prompt Article Import cần có:

- `article.translate`
  - dịch text block sang tiếng Việt;
  - giữ thuật ngữ theo glossary;
  - không dịch code, command, API, package, filename.

- `article.rewrite`
  - biên tập lại thành văn phong blog;
  - tránh văn dịch máy;
  - không thêm claim mới nếu nguồn không có.

- `article.metadata`
  - tạo title tiếng Việt;
  - tạo excerpt;
  - tạo slug;
  - gợi ý tags/categories.

- `article.term_review`
  - kiểm tra thuật ngữ chuyên ngành;
  - phát hiện thuật ngữ bị dịch sai hoặc không nhất quán;
  - trả warning để người vận hành review.

- `article.wordpress_style`
  - quy định heading/caption/source attribution;
  - quy định tone bài WordPress;
  - quy định cách render code/image/quote.

UI Prompt Manager nên có tab hoặc filter:

```text
Prompt Manager
  -> Search
      -> Query Analyst
      -> Summary
  -> Article Import
      -> Translate
      -> Rewrite
      -> Metadata
      -> Term Review
      -> WordPress Style
```

Schema runtime prompt nên hỗ trợ:

- `prompt_key`
- `version`
- `content`
- `status`: `draft | active | archived`
- `model`
- `temperature`
- `max_output_tokens`
- `notes`

Acceptance:

- Chỉnh `article.translate` không ảnh hưởng `search.summary`.
- Có thể rollback từng prompt key riêng.
- Import run lưu lại prompt key/version đã dùng để audit.

### LLM provider hiện tại: 9Router GPT 5.5

Pipeline hiện dùng 9Router làm OpenAI-compatible router và model mặc định `cx/gpt-5.5`. Business logic không khóa vào SDK/model cụ thể; provider chỉ là adapter gọi `/chat/completions`.

Mục tiêu:

- Dùng GPT 5.5 qua 9Router cho các bước cần hiểu ngôn ngữ:
  - dịch block text theo batch nhỏ;
  - rewrite thành văn phong blog;
  - giữ thuật ngữ chuyên ngành;
  - tạo title/excerpt/slug/tags;
  - dịch caption ảnh;
  - kiểm tra code block không bị thay đổi;
  - giữ placeholder link `[LINK_n:label]` qua dịch.
- Dùng 9Router làm lớp route API:
  - quản lý endpoint/key tập trung;
  - dễ đổi model (`cx/gpt-5.5`, review model, fallback model khác nếu cần);
  - không khóa pipeline vào một SDK cụ thể.

Backend nên có interface trung lập:

```text
ArticleLlmProvider
  -> translate_blocks(request) -> translated structured blocks
  -> build_blog_metadata(request) -> title/excerpt/slug/tags
  -> review_terms(request) -> glossary warnings
```

Implementation hiện tại:

```text
NineRouterOpenAIArticleProvider
  -> gọi 9Router endpoint
  -> model mặc định: cx/gpt-5.5
  -> response format: JSON object
  -> retry 429/500/502/503/504/timeout với backoff
  -> fallback parse/validate JSON trong backend
```

Lưu ý:

- Model chỉ xử lý nội dung và quyết định ngôn ngữ.
- Fetch URL, tải ảnh, lưu file, build draft, mở Chrome và paste WordPress vẫn do backend code làm.
- Nếu 9Router lỗi, pipeline đánh dấu `partial` và cho phép bấm Translate để resume phần chưa dịch.

### Glossary

Tạo file hoặc DB config:

- `retrieval`: truy xuất
- `embedding`: embedding hoặc vector nhúng tùy style guide
- `inference`: suy luận
- `fine-tuning`: tinh chỉnh
- `agent`: agent
- `tool calling`: gọi tool
- `rate limit`: giới hạn tần suất
- `fallback`: fallback hoặc phương án dự phòng
- `prompt`: prompt

Glossary nên có:

- `term`
- `preferred_translation`
- `do_not_translate`
- `notes`
- `domain`

### Prompt policy

Agent chỉ nhận structured blocks:

- Text block: dịch/viết lại.
- Code block: giữ nguyên.
- Image block: tạo caption tiếng Việt nếu cần, không bịa nội dung ảnh.
- Table: dịch cell text, giữ số liệu.

Output vẫn là structured blocks để build WordPress draft.

### Structured output contract

9Router GPT 5.5 nên trả JSON theo schema ổn định. Backend không tin tuyệt đối output của model; luôn validate lại:

- đủ `block_id` tương ứng input;
- không mất block;
- code block không bị thay đổi;
- URL/asset id không bị model tự bịa;
- title/excerpt không vượt giới hạn cấu hình;
- thuật ngữ trong glossary được áp dụng hoặc có warning.

Ví dụ response nội bộ:

```json
{
  "title_vi": "Tieu de bai viet",
  "excerpt_vi": "Mo ta ngan",
  "slug": "tieu-de-bai-viet",
  "tags": ["AI", "Agent"],
  "translated_blocks": [
    {
      "block_id": "b1",
      "type": "paragraph",
      "text_vi": "Noi dung da dich"
    },
    {
      "block_id": "b2",
      "type": "code",
      "text_vi": "npm install example"
    }
  ],
  "warnings": []
}
```

## 10. WordPress Draft Builder

### Draft format nội bộ

```json
{
  "title": "Tiêu đề tiếng Việt",
  "slug": "tieu-de-tieng-viet",
  "excerpt": "Mô tả ngắn",
  "content_blocks": [],
  "tags": [],
  "categories": [],
  "source_attribution": {
    "url": "https://...",
    "title": "Original title",
    "domain": "example.com"
  }
}
```

### Output render

Hỗ trợ 2 chế độ:

- WordPress block comment format:
  - `<!-- wp:paragraph -->`
  - `<!-- wp:image -->`
  - `<!-- wp:code -->`

- HTML fallback:
  - `<h2>`
  - `<p>`
  - `<figure><img ...><figcaption>`
  - `<pre><code>`

MVP nên bắt đầu với HTML fallback vì paste ổn định hơn, sau đó nâng cấp Gutenberg block format.

## 11. Chrome WordPress Automator

### Cách chạy Chrome port riêng

Gợi ý local:

```powershell
Start-Process "chrome.exe" -ArgumentList @(
  "--remote-debugging-port=9227",
  "--user-data-dir=D:\NTC_AI\ChromeProfiles\web-agent-wp",
  "--new-window",
  "https://your-wordpress-site.com/wp-admin/post-new.php"
)
```

Hoặc qua script:

- `scripts/start_wp_chrome.ps1`
- port mặc định: `9227`
- profile riêng để không đụng Chrome cá nhân.

### Automation options

Ưu tiên Playwright connect qua CDP:

- Kết nối `http://127.0.0.1:9227`
- Tìm tab WordPress editor.
- Focus title field.
- Paste title.
- Focus content editor.
- Paste rendered HTML/block content.
- Upload/insert ảnh nếu MVP hỗ trợ media library.

MVP nên dùng paste draft trước, không publish:

- Nếu editor không đúng URL hoặc chưa login, trả lỗi rõ ràng.
- Nếu có unsaved content, hỏi/dừng ở UI thay vì ghi đè.
- Sau khi paste xong, lưu run status `pasted`.

## 12. Phase triển khai

### Phase A - Plan + contracts

- Chốt API contract cho article import.
- Chốt schema structured blocks.
- Chốt folder lưu raw snapshot/assets/draft.
- Chốt glossary format.
- Ước tính: 0.5 ngày.

### Phase B - Fetcher + extractor MVP

- Thêm service `article_fetcher_service.py`.
- Thêm service `article_extractor_service.py`.
- HTTP fetch + readability/trafilatura extraction.
- Tách block paragraph/heading/image/code.
- Unit test bằng fixture HTML.
- Ước tính: 1 ngày.

### Phase C - Asset downloader

- Download ảnh theo manifest.
- Deduplicate bằng checksum.
- Validate MIME type và kích thước.
- Không tải file quá lớn hoặc domain lạ nếu chưa allow.
- Ước tính: 0.5 ngày.

### Phase D - Translation/rewrite agent

- Tạo `article_translation_service.py`.
- Tạo provider adapter gọi 9Router GPT 5.5 qua OpenAI-compatible API.
- Tạo glossary config.
- Mở rộng Prompt Manager theo namespace `article.*`, không dùng chung prompt search.
- Prompt dịch theo structured blocks.
- Không dịch code.
- Test regression cho thuật ngữ chuyên ngành.
- Test regression khi 9router lỗi hoặc trả JSON không hợp lệ.
- Test regression chỉnh prompt Article Import không ảnh hưởng Search Summary.
- Ước tính: 1 ngày.

### Phase E - WordPress draft builder

- Tạo `wordpress_draft_builder.py`.
- Render HTML fallback.
- Render Gutenberg block format ở mức thử nghiệm.
- Preview API trả draft hoàn chỉnh.
- Ước tính: 0.5 ngày.

### Phase F - Chrome automation

- Tạo `wordpress_automation_service.py`.
- Script mở Chrome port riêng.
- Playwright connect CDP.
- Dry-run kiểm tra editor.
- Paste title/content vào WordPress.
- Không publish tự động trong MVP.
- Ước tính: 1 ngày.

### Phase G - Frontend Article Import UI

- Thêm view nhập URL.
- Hiển thị pipeline status.
- Preview blocks/assets/draft.
- Nút translate lại, dry-run, paste draft.
- Ước tính: 1 ngày.

### Phase H - Hardening + audit

- Lưu run trace đầy đủ.
- Retry/cancel rõ ràng.
- Domain profile override.
- Security guard cho URL/file download.
- Documentation vận hành.
- Ước tính: 1 ngày.

## 13. Thứ tự bắt đầu ngay

1. Tạo data contract `ArticleBlock`, `ArticleAsset`, `ArticleImportRun`.
2. Làm extractor MVP bằng fixture HTML trước, chưa cần WordPress.
3. Thêm asset downloader và block preview.
4. Gắn Translation Agent với glossary qua Gemini/9router provider.
5. Build draft HTML.
6. Sau khi draft ổn mới làm Chrome/WordPress automation.

Lý do: nếu extraction và structured blocks chưa tốt, automation WordPress chỉ làm lỗi bị đưa nhanh hơn vào editor. Phần khó nhất là giữ đúng cấu trúc bài và thuật ngữ, nên phải khóa chất lượng ở giữa pipeline trước.

## 14. Acceptance criteria MVP

- Nhập một URL cụ thể và hệ thống chỉ fetch đúng URL đó.
- Extract được title + nội dung chính + ảnh + code block theo đúng thứ tự.
- Ảnh được tải về local manifest.
- Code/bash giữ nguyên, không bị dịch hoặc format hỏng.
- Text được dịch/biên tập theo glossary.
- Draft preview hiển thị đủ title, excerpt, content, source attribution.
- Chrome dry-run xác nhận đã kết nối đúng WordPress editor.
- Paste draft vào WordPress post mới nhưng không tự publish.
- Mọi lỗi có status rõ ràng trong import run.

## 15. Rủi ro và giảm thiểu

- Extract sai nội dung do layout mỗi site khác nhau.
  - Giảm thiểu: domain extraction profiles và preview blocks.

- Vi phạm bản quyền nếu copy quá sát bài nguồn.
  - Giảm thiểu: rewrite/summarize theo policy, attribution, review thủ công.

- WordPress editor thay đổi UI làm automation lỗi.
  - Giảm thiểu: dry-run, selector fallback, ưu tiên paste HTML vào editor ổn định.

- Ảnh hotlink hoặc license không hợp lệ.
  - Giảm thiểu: tải về local, lưu metadata, review license trước publish.

- LLM dịch sai thuật ngữ.
  - Giảm thiểu: glossary, regression tests, review preview từng block.

## 16. File/module dự kiến

- `backend/src/models/article_schemas.py`
- `backend/src/controllers/article_import_controller.py`
- `backend/src/services/article_fetcher_service.py`
- `backend/src/services/article_extractor_service.py`
- `backend/src/services/article_asset_service.py`
- `backend/src/services/article_translation_service.py`
- `backend/src/services/article_llm_provider.py`
- `backend/src/services/ninerouter_gemini_article_provider.py`
- `backend/src/services/article_prompt_service.py`
- `backend/src/services/wordpress_draft_builder.py`
- `backend/src/services/wordpress_automation_service.py`
- `backend/tests/test_article_extractor.py`
- `backend/tests/test_article_translation_service.py`
- `backend/tests/test_article_prompt_isolation.py`
- `backend/tests/test_wordpress_draft_builder.py`
- `scripts/start_wp_chrome.ps1`
- `scripts/start_wp_chrome.sh`
- `frontend/src/components/ArticleImportPanel.tsx`

## 17. Ghi chú triển khai local

- Chrome automation nên dùng profile riêng:
  - tránh đụng session cá nhân;
  - giữ login WordPress ổn định;
  - dễ xoá/reset khi lỗi.
- Port CDP nên cấu hình được qua env:
  - `APP_WORDPRESS_CHROME_CDP_URL=http://127.0.0.1:9227`
  - `APP_WORDPRESS_ADMIN_URL=https://your-site.com/wp-admin/post-new.php`
- 9Router GPT 5.5 nên cấu hình qua env:
  - `APP_ARTICLE_LLM_PROVIDER=9router_openai`
  - `APP_9ROUTER_API_KEY=...`
  - `APP_9ROUTER_BASE_URL=...`
  - `APP_ARTICLE_OPENAI_MODEL=cx/gpt-5.5`
  - `APP_ARTICLE_TRANSLATION_MAX_OUTPUT_TOKENS=8000`
  - `APP_ARTICLE_TRANSLATION_BATCH_SIZE=3`
  - `APP_ARTICLE_TRANSLATION_MAX_BATCH_CHARS=8000`
- Không lưu WordPress password trong code.
- Nếu cần login tự động, dùng session profile hoặc secret manager riêng.

## 18. Ghi chú chọn 9Router GPT 5.5

Lý do chọn hướng này:

- GPT 5.5 qua 9Router phù hợp cho dịch, rewrite và xử lý structured content.
- 9Router giúp tách pipeline khỏi một vendor SDK cụ thể.
- Khi cần đổi model hoặc fallback model, chỉ sửa config/provider.
- Backend vẫn giữ quyền kiểm soát các thao tác rủi ro cao như tải file và paste WordPress.

Checklist trước khi implement/vận hành:

1. Xác nhận 9Router endpoint đang dùng là OpenAI-compatible.
2. Chốt tên model chính xác trong 9Router, hiện là `cx/gpt-5.5`.
3. Kiểm tra dashboard 9Router có credential/provider active.
4. Không commit API key thật vào repo.
3. Test request nhỏ với structured JSON response.
4. Chốt limit input/output cho mỗi batch block.
5. Thêm retry/backoff và lỗi quota/rate limit rõ ràng.

## 19. Update Phase A/B implementation status

### Phase A completed

- Added Article Import API contract.
- Added structured schemas for import run, blocks, assets, draft preview, prompt usage.
- Added feature flag and env/config placeholders for Article Import, 9router/Gemini, and WordPress CDP.
- Added contract tests.

### Phase B completed

- Added `ArticleFetcherService` using HTTP fetch via `httpx`.
- Added `ArticleExtractorService` using HTML parsing via BeautifulSoup.
- `POST /api/v1/articles/import` now:
  - fetches the provided URL;
  - extracts source metadata;
  - separates heading, paragraph, image, code, quote, and table blocks;
  - creates asset manifest entries for images;
  - saves `raw.html` and `extracted.json`;
  - returns status `extracted` on success.
- Added fixture-based extractor tests.
- Added fetch failure response with `ARTICLE_FETCH_FAILED`.

### Phase C completed

- Added `ArticleAssetService` to download images from the extracted asset manifest.
- Asset downloader now:
  - validates image MIME type;
  - enforces `APP_ARTICLE_ASSET_MAX_BYTES`;
  - writes downloaded files under the run `assets` folder;
  - calculates SHA-256 checksum;
  - deduplicates repeated image content by checksum;
  - marks each asset as `downloaded`, `skipped`, or `failed`.
- `POST /api/v1/articles/import` now includes asset download counters:
  - `asset_downloaded_count`
  - `asset_failed_count`
  - `asset_skipped_count`
- Added tests for successful image download, checksum dedupe, non-image skip, and oversized asset skip.

### Phase D completed

- Added Article Import prompt namespace support via `ArticlePromptService`.
- Added provider abstraction:
  - `ArticleLlmProvider`
  - `ArticleTranslationRequest`
  - `ArticleTranslationResult`
- Added `NineRouterOpenAIArticleProvider` for OpenAI-compatible 9Router `/chat/completions`.
- Added `ArticleTranslationService` to:
  - call GPT 5.5 through 9Router when configured;
  - skip translation safely when 9router base URL is absent;
  - apply translated text back to structured blocks;
  - preserve code blocks exactly;
  - populate draft metadata (`title`, `excerpt`, `slug`, `tags`, `categories`);
  - attach prompt usage with `article.*` keys;
  - keep import successful when model output is invalid, with `translation_status=failed`.
- `POST /api/v1/articles/import` now can return status `translated` when translation succeeds.
- Added tests for:
  - article prompt namespace isolation from `search.summary`;
  - 9Router GPT 5.5 request + response application;
  - invalid JSON fallback without failing the import.

### Phase E completed

- Added `WordPressDraftBuilder`.
- Draft builder now renders HTML fallback from structured blocks:
  - headings as `<h2>`-`<h4>`;
  - paragraphs as `<p>`;
  - quotes as `<blockquote>`;
  - code as `<pre><code class="language-*">`;
  - images as `<figure><img ...><figcaption>`;
  - source attribution with `rel="nofollow noopener"`.
- `POST /api/v1/articles/import` now:
  - builds draft preview after translation/skip/failure;
  - saves `draft.json`;
  - returns status `draft_ready`;
  - includes `draft_status=ready`.
- Added tests for draft HTML rendering, translated content rendering, code preservation, image rendering, source attribution, and `draft.json` persistence.

### Phase F completed

- Added `WordPressAutomationService` using Playwright CDP.
- Added Chrome starter scripts:
  - `scripts/start_wp_chrome.ps1`
  - `scripts/start_wp_chrome.sh`
- Import runs now persist `run.json`, allowing follow-up actions by `run_id`.
- Implemented:
  - `GET /api/v1/articles/import/{run_id}`
  - `POST /api/v1/articles/import/{run_id}/wordpress/dry-run`
  - `POST /api/v1/articles/import/{run_id}/wordpress/paste`
- Dry-run checks whether a WordPress editor page is reachable.
- Paste writes draft title/content into the detected WordPress editor and marks run status `pasted` on success.
- Automation failures return structured errors:
  - `WORDPRESS_DRY_RUN_FAILED`
  - `WORDPRESS_PASTE_FAILED`
  - `WORDPRESS_DRAFT_NOT_READY`
- Added tests with a fake automation service for persisted run loading, dry-run success, paste success, and paste failure.

### Phase G completed

- Added frontend Article Import API types.
- Added frontend Article Import API client methods:
  - `importArticle`
  - `fetchArticleImport`
  - `dryRunWordPressImport`
  - `pasteWordPressImport`
- Added `ArticleImportPanel`.
- Article Import UI now supports:
  - source URL input;
  - glossary key input;
  - optional WordPress target URL input;
  - import/fetch/build draft action;
  - status summary;
  - block preview;
  - asset manifest preview;
  - HTML draft preview;
  - WordPress dry-run;
  - WordPress paste draft.
- Added `Article Import` tab to the existing Settings modal, keeping the main chat workspace unchanged.
- Verified:
  - backend tests pass;
  - frontend lint passes;
  - frontend production build passes.

### Phase H completed

- Added URL safety guard for Article Import:
  - blocks `localhost`;
  - blocks private/loopback/link-local/reserved IP URLs by default;
  - allows override via `APP_ARTICLE_ALLOW_PRIVATE_URLS=true` for controlled local testing.
- Added run-id path hardening using strict `air_<uuidhex>` pattern before loading persisted runs.
- Added audit events for:
  - article import create success/failure/block;
  - WordPress dry-run success/failure;
  - WordPress paste success/failure.
- Added structured safety/error handling:
  - `ARTICLE_URL_BLOCKED`
  - `ARTICLE_IMPORT_NOT_FOUND`
  - existing WordPress structured errors retained.
- Added tests for:
  - localhost URL blocking;
  - private IP URL blocking;
  - audit log events for import and paste.
- Verified:
  - Article Import tests pass;
  - full backend tests pass;
  - frontend lint passes;
  - frontend production build passes.

### Still not implemented

- Playwright rendered fallback for JavaScript-heavy pages.
- Optional domain extraction profiles.
- Optional frontend polish after manual UX review.

### Phase G UX adjustment completed

- Promoted Article Import from the Settings modal into a top-level workspace mode.
- Added a sidebar mode switch above the `Chat moi` and chat history area:
  - `Web Search`
  - `Viet blog`
- Web Search and Article Import now switch smoothly without resetting their current local UI state.
- Settings modal now keeps only system/admin tools:
  - Tavily Keys
  - Ops Dashboard
  - Prompt Manager
- Main workspace now renders:
  - current Web Search chat when `Web Search` is selected;
  - Article Import scrape/write-blog UI when `Viet blog` is selected.
- Fixed Article Import horizontal overflow after a draft is generated:
  - long draft HTML wraps/scrolls inside its preview box;
  - long source URLs, asset paths, run IDs, and block text no longer push the page wider;
  - the initial import form stays at a normal default width before any draft is loaded.
- Added a 9router/Gemini health check:
  - backend endpoint `POST /api/v1/articles/import/llm/health`;
  - frontend `Check 9router` button inside Article Import;
  - UI shows provider readiness, model, base URL, API key presence, and latency.

### 9Router correction completed

- Corrected the frontend dashboard button:
  - local dashboard: `http://localhost:20128/dashboard`;
  - website/docs: `https://9router.com`.
- Corrected local 9Router configuration notes:
  - API base for backend: `http://127.0.0.1:20128/v1`;
  - start command: `npm install -g 9router && 9router`.
- Added env guidance:
  - `APP_9ROUTER_BASE_URL=http://127.0.0.1:20128/v1`;
  - `NEXT_PUBLIC_9ROUTER_DASHBOARD_URL=http://localhost:20128/dashboard`.

### 9Router setup integration completed

- Added 9Router to local setup flow.
- `setup.ps1` and `setup.sh` now:
  - read `NINEROUTER_INSTALL`;
  - install global `9router` with npm when enabled;
  - create the Windows npm global folder if missing;
  - write Article Import backend env for `APP_9ROUTER_BASE_URL`;
  - write frontend env for the 9Router dashboard/site buttons;
  - start 9Router when `NINEROUTER_AUTO_START=true`.
- `run.ps1` and `run.sh` now auto-start 9Router if configured.
- `stop.ps1` and `stop.sh` now stop the 9Router process started by project scripts.
- Root `.env` / `.env.example` now include:

```env
NINEROUTER_INSTALL=true
NINEROUTER_AUTO_START=true
NINEROUTER_START_MODE=terminal
NINEROUTER_BASE_URL=http://127.0.0.1:20128/v1
NINEROUTER_DASHBOARD_URL=http://localhost:20128/dashboard
```

### 9Router UI cleanup completed

- Removed the external `9Router site` button from Article Import.
- Kept only:
  - `Check 9router`;
  - `Open dashboard` for the local dashboard.
- Removed `NINEROUTER_SITE_URL` / `NEXT_PUBLIC_9ROUTER_SITE_URL` from setup/env wiring.

### 9Router visible terminal mode completed

- Added `NINEROUTER_START_MODE`.
- Default mode is `terminal`, so setup/run opens 9Router in its own terminal window when possible.
- Set `NINEROUTER_START_MODE=background` to run hidden and write logs under `logs/`.

### 9Router health fix completed

- Fixed backend 9Router calls by sending `stream=false`.
- Without `stream=false`, local 9Router returned SSE text like `data: [DONE]`, which caused JSON parsing error `Expecting value`.
- Updated Article Import default model to `cx/gpt-5.5`.
- Clarified frontend wording:
  - `Router auth: not set / optional` means backend-to-9Router auth is not configured;
  - provider credentials are configured inside the 9Router dashboard.

### Windows backend reload issue fixed

- Removed `--reload` from local backend start commands in `run.ps1`, `run.sh`, `setup.ps1`, and `setup.sh`.
- Reason: on Windows, Uvicorn reload spawned a child process through the system Python instead of the project `.venv`, which could keep old service code and env behavior during Article Import translation.
- Backend now starts directly from the project venv; rerun `run.ps1` after code changes.

### Translation and WordPress dry-run fixes completed

- Translation fixes:
  - set `APP_ARTICLE_TRANSLATION_MAX_OUTPUT_TOKENS=8000`;
  - increased 9Router translation timeout to 180 seconds;
  - added clearer `translation_json_invalid` errors when model output is truncated;
  - split translation into small batches with `APP_ARTICLE_TRANSLATION_BATCH_SIZE=3` and `APP_ARTICLE_TRANSLATION_MAX_BATCH_CHARS=8000`;
  - reruns now skip blocks that already have translated text;
  - image/unknown blocks are not sent back during reruns;
  - if a batch fails, the run is marked `partial` and the draft is still built with translated blocks plus original source fallback for missing blocks;
  - 9Router HTTP 429/500/502/503/504 and transport timeout/reset now retry with backoff before pausing;
  - verified the saved NVIDIA test run can translate successfully with 35 translated blocks.
- WordPress automation fixes:
  - replaced Playwright-based CDP automation with direct Chrome DevTools Protocol over HTTP/WebSocket;
  - avoids Windows `asyncio.create_subprocess_exec` / `NotImplementedError` from Playwright;
  - dry-run now returns a clear `wordpress_cdp_unreachable:http://127.0.0.1:9227` when Chrome CDP is not open.

### Current verification notes

- Backend Article Import contract tests pass: `22 passed`.
- Frontend lint passes.
- Shell syntax checks pass for `setup.sh`, `run.sh`, and `stop.sh`.
- PowerShell parser checks pass for `setup.ps1`, `run.ps1`, `stop.ps1`, and `scripts/start_wp_chrome.ps1`.
- Live backend/frontend proxy checks return JSON responses:
  - 9Router health: `ready` with `cx/gpt-5.5`;
  - latest saved article run: `draft_ready`, `translation=translated`, `35` translated text blocks, `7` image blocks.

### Frontend proxy timeout fix completed

- Root cause for `Backend returned non-JSON response (HTTP 500): Internal Server Error`:
  - Article Import can take longer than 30 seconds while fetching assets and translating batches;
  - calling through the Next.js rewrite `/api/v1/articles/import` can hit the dev proxy timeout;
  - Next then returns plain text `Internal Server Error`, so the frontend cannot parse JSON.
- Fixed frontend runtime config to call the backend directly:
  - `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8011/api/v1`
  - removed the duplicate later `NEXT_PUBLIC_API_BASE=/api/v1` line from `frontend/.env.local`.
- Updated setup scripts so future setup does not restore the proxy path:
  - `setup.ps1`;
  - `setup.sh`.
- Verified:
  - frontend bundle now contains `http://127.0.0.1:8011/api/v1`;
  - backend CORS allows `http://localhost:3005`;
  - frontend lint passes;
  - setup/run/stop syntax checks pass.

### Gemini quota/rate-limit continuation fix completed

- Root cause for `Translation error: batch_7:ninerouter_http_429`:
  - long articles can exceed Gemini/9Router quota when too many translation batches run in one request.
- Added a backend rate-limit guard:
  - `APP_ARTICLE_TRANSLATION_MAX_BATCHES_PER_RUN=6`;
  - each import/translate request processes up to 6 translation batches;
  - if more text remains, the run is marked `partial` with `translation_paused=true`;
  - pressing `Translate` again resumes from untranslated blocks because already translated blocks are skipped.
- Frontend now shows a short `Translation note` instead of the long raw 429 JSON:
  - paused guard: “Press Translate again after a short wait”;
  - true 429: “Gemini quota/rate limit reached”.
- Verified:
  - backend Article Import tests pass;
  - frontend lint passes;
  - backend restarted on `127.0.0.1:8011`;
  - frontend restarted on `localhost:3005`.
