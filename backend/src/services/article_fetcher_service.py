from dataclasses import dataclass

import httpx

from src.config.settings import Settings


class ArticleFetchError(Exception):
    pass


@dataclass(frozen=True)
class ArticleFetchResult:
    final_url: str
    html: str
    status_code: int
    content_type: str


class ArticleFetcherService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch(self, url: str) -> ArticleFetchResult:
        headers = {
            "User-Agent": self.settings.article_fetch_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            async with httpx.AsyncClient(
                timeout=max(self.settings.request_timeout_seconds, 5.0),
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise ArticleFetchError(f"fetch_network_error: {exc}") from exc

        if response.status_code >= 400:
            raise ArticleFetchError(f"fetch_http_{response.status_code}")

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower() and response.text.lstrip()[:20].lower().find("<!doctype") == -1:
            raise ArticleFetchError(f"fetch_non_html_content_type: {content_type or 'unknown'}")

        return ArticleFetchResult(
            final_url=str(response.url),
            html=response.text,
            status_code=response.status_code,
            content_type=content_type,
        )
