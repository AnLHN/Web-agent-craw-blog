import json
from dataclasses import dataclass
from itertools import count
from urllib.parse import quote

import httpx
import websockets

from src.config.settings import Settings


@dataclass(frozen=True)
class WordPressAutomationResult:
    ok: bool
    status: str
    message: str
    page_url: str | None = None


class WordPressAutomationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def dry_run(self) -> WordPressAutomationResult:
        try:
            page = await self._find_or_open_editor_page()
            return WordPressAutomationResult(
                ok=True,
                status="ready",
                message="WordPress editor is reachable",
                page_url=page.get("url"),
            )
        except Exception as exc:
            return WordPressAutomationResult(
                ok=False,
                status="failed",
                message=str(exc) or exc.__class__.__name__,
                page_url=None,
            )

    async def paste_draft(self, title: str, content: str) -> WordPressAutomationResult:
        try:
            page = await self._find_or_open_editor_page()
            websocket_url = page.get("webSocketDebuggerUrl")
            if not websocket_url:
                raise RuntimeError("wordpress_cdp_websocket_not_found")
            async with websockets.connect(websocket_url, max_size=8 * 1024 * 1024) as websocket:
                client = _CdpClient(websocket)
                await client.call("Runtime.enable")
                title_result = await client.evaluate(_set_title_expression(title))
                if not title_result:
                    raise RuntimeError("wordpress_title_field_not_found")
                content_result = await client.evaluate(_set_content_expression(content))
                if not content_result:
                    raise RuntimeError("wordpress_content_editor_not_found")
            return WordPressAutomationResult(
                ok=True,
                status="pasted",
                message="Draft content pasted into WordPress editor",
                page_url=page.get("url"),
            )
        except Exception as exc:
            return WordPressAutomationResult(
                ok=False,
                status="failed",
                message=str(exc) or exc.__class__.__name__,
                page_url=None,
            )

    async def _find_or_open_editor_page(self) -> dict:
        pages = await self._list_pages()
        if not pages and self.settings.wordpress_admin_url.strip():
            await self._open_page(self.settings.wordpress_admin_url.strip())
            pages = await self._list_pages()
        if not pages:
            raise RuntimeError("wordpress_editor_page_not_found")

        admin_url = self.settings.wordpress_admin_url.strip()
        candidates = pages
        if admin_url:
            candidates = [page for page in pages if str(page.get("url", "")).startswith(admin_url)] or pages
        for page in candidates:
            page_url = str(page.get("url", ""))
            if "wp-admin" in page_url or "post-new.php" in page_url or "post.php" in page_url:
                return page
        raise RuntimeError("wordpress_editor_page_not_found")

    async def _list_pages(self) -> list[dict]:
        base_url = self.settings.wordpress_chrome_cdp_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(f"{base_url}/json/list")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"wordpress_cdp_unreachable:{base_url}") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"wordpress_cdp_http_{response.status_code}")
        return [page for page in response.json() if page.get("type") == "page"]

    async def _open_page(self, url: str) -> None:
        base_url = self.settings.wordpress_chrome_cdp_url.rstrip("/")
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.put(f"{base_url}/json/new?{quote(url, safe=':/?&=%')}")
        if response.status_code >= 400:
            raise RuntimeError(f"wordpress_cdp_new_page_http_{response.status_code}")


class _CdpClient:
    def __init__(self, websocket):
        self.websocket = websocket
        self._ids = count(1)

    async def call(self, method: str, params: dict | None = None) -> dict:
        request_id = next(self._ids)
        await self.websocket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.websocket.recv())
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(message["error"].get("message") or f"cdp_error:{method}")
            return message.get("result") or {}

    async def evaluate(self, expression: str):
        result = await self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        if result.get("exceptionDetails"):
            raise RuntimeError("wordpress_editor_script_failed")
        return (result.get("result") or {}).get("value")


def _js_string(value: str) -> str:
    return json.dumps(value)


def _set_title_expression(title: str) -> str:
    return f"""
(() => {{
  const value = {_js_string(title)};
  const selectors = [
    "h1[contenteditable='true']",
    "textarea[name='post_title']",
    "#title",
    ".editor-post-title__input"
  ];
  for (const selector of selectors) {{
    const el = document.querySelector(selector);
    if (!el) continue;
    el.focus();
    if ("value" in el) {{
      el.value = value;
      el.dispatchEvent(new Event("input", {{ bubbles: true }}));
      el.dispatchEvent(new Event("change", {{ bubbles: true }}));
    }} else {{
      el.textContent = value;
      el.dispatchEvent(new InputEvent("input", {{ bubbles: true, inputType: "insertText", data: value }}));
    }}
    return true;
  }}
  return false;
}})()
"""


def _set_content_expression(content: str) -> str:
    return f"""
(() => {{
  const html = {_js_string(content)};
  const textarea = document.querySelector("textarea[name='content'], #content");
  if (textarea) {{
    textarea.focus();
    textarea.value = html;
    textarea.dispatchEvent(new Event("input", {{ bubbles: true }}));
    textarea.dispatchEvent(new Event("change", {{ bubbles: true }}));
    return true;
  }}
  const editor = document.querySelector(".block-editor-writing-flow [contenteditable='true'], [contenteditable='true'][role='textbox'], .block-editor-writing-flow");
  if (!editor) return false;
  editor.focus();
  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(editor);
  range.collapse(false);
  selection.removeAllRanges();
  selection.addRange(range);
  document.execCommand("insertHTML", false, html);
  editor.dispatchEvent(new InputEvent("input", {{ bubbles: true, inputType: "insertHTML", data: html }}));
  return true;
}})()
"""
