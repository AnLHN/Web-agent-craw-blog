import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.config.settings import Settings
from src.models.article_schemas import ArticleAsset, ArticleAssetDownloadStatus


class ArticleAssetService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def download_assets(self, assets: list[ArticleAsset], assets_dir: str) -> list[ArticleAsset]:
        target_dir = Path(assets_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded_by_checksum: dict[str, str] = {}
        updated_assets: list[ArticleAsset] = []
        headers = {"User-Agent": self.settings.article_fetch_user_agent, "Accept": "image/*,*/*;q=0.8"}
        async with httpx.AsyncClient(
            timeout=max(self.settings.request_timeout_seconds, 10.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            for asset in assets:
                updated_assets.append(await self._download_one(client, asset, target_dir, downloaded_by_checksum))
        return updated_assets

    async def _download_one(
        self,
        client: httpx.AsyncClient,
        asset: ArticleAsset,
        target_dir: Path,
        downloaded_by_checksum: dict[str, str],
    ) -> ArticleAsset:
        candidates = self._build_candidates(asset)
        if not candidates:
            return asset.model_copy(
                update={
                    "download_status": ArticleAssetDownloadStatus.SKIPPED,
                    "metadata": {**asset.metadata, "skip_reason": "no_valid_asset_url"},
                }
            )

        referer = asset.metadata.get("page_url") if isinstance(asset.metadata, dict) else None
        last_failure = "unknown"
        for source_url in candidates:
            parsed = urlparse(source_url)
            if parsed.scheme not in {"http", "https"}:
                last_failure = f"unsupported_scheme:{parsed.scheme or 'unknown'}"
                continue

            response, error = await self._request_with_retry(client, source_url, referer)
            if error is not None:
                last_failure = f"network_error: {error}"
                continue
            assert response is not None
            if response.status_code >= 400:
                last_failure = f"http_{response.status_code}"
                continue

            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if not content_type.startswith("image/"):
                last_failure = f"non_image_content_type:{content_type or 'unknown'}"
                continue

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.settings.article_asset_max_bytes:
                return asset.model_copy(
                    update={
                        "download_status": ArticleAssetDownloadStatus.SKIPPED,
                        "mime_type": content_type,
                        "metadata": {**asset.metadata, "skip_reason": "asset_too_large"},
                    }
                )

            content = response.content
            if len(content) > self.settings.article_asset_max_bytes:
                return asset.model_copy(
                    update={
                        "download_status": ArticleAssetDownloadStatus.SKIPPED,
                        "mime_type": content_type,
                        "metadata": {**asset.metadata, "skip_reason": "asset_too_large"},
                    }
                )

            checksum = hashlib.sha256(content).hexdigest()
            if checksum in downloaded_by_checksum:
                return asset.model_copy(
                    update={
                        "source_url": source_url,
                        "local_path": downloaded_by_checksum[checksum],
                        "mime_type": content_type,
                        "checksum": checksum,
                        "download_status": ArticleAssetDownloadStatus.DOWNLOADED,
                        "metadata": {**asset.metadata, "deduplicated": True},
                    }
                )

            extension = self._extension(content_type=content_type, source_url=source_url)
            filename = f"{asset.id}-{checksum[:12]}{extension}"
            path = target_dir / filename
            path.write_bytes(content)
            local_path = str(path)
            downloaded_by_checksum[checksum] = local_path
            return asset.model_copy(
                update={
                    "source_url": source_url,
                    "local_path": local_path,
                    "mime_type": content_type,
                    "checksum": checksum,
                    "download_status": ArticleAssetDownloadStatus.DOWNLOADED,
                }
            )

        if last_failure.startswith("non_image_content_type"):
            return asset.model_copy(
                update={
                    "download_status": ArticleAssetDownloadStatus.SKIPPED,
                    "metadata": {**asset.metadata, "skip_reason": last_failure},
                }
            )
        return self._mark_failed(asset, last_failure)

    @staticmethod
    async def _request_with_retry(
        client: httpx.AsyncClient, source_url: str, referer: str | None
    ) -> tuple[httpx.Response | None, str | None]:
        try:
            response = await client.get(source_url)
        except httpx.HTTPError as exc:
            return None, str(exc)
        if response.status_code != 403:
            return response, None

        retry_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        if isinstance(referer, str) and referer.strip():
            retry_headers["Referer"] = referer.strip()
        try:
            response = await client.get(source_url, headers=retry_headers)
        except httpx.HTTPError as exc:
            return None, str(exc)
        return response, None

    def _build_candidates(self, asset: ArticleAsset) -> list[str]:
        candidates: list[str] = []

        def push(value: str | None) -> None:
            if not value:
                return
            candidate = value.strip()
            if not candidate or candidate.startswith("data:") or candidate in candidates:
                return
            candidates.append(candidate)

        push(asset.source_url)
        metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
        for key in ("srcset", "data_srcset"):
            for candidate in self._parse_srcset(str(metadata.get(key) or "")):
                push(candidate)
        return candidates

    @staticmethod
    def _parse_srcset(value: str) -> list[str]:
        urls: list[str] = []
        for item in value.split(","):
            cleaned = item.strip()
            if not cleaned:
                continue
            url = cleaned.split(" ", 1)[0].strip()
            if url and url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def _mark_failed(asset: ArticleAsset, reason: str) -> ArticleAsset:
        return asset.model_copy(
            update={
                "download_status": ArticleAssetDownloadStatus.FAILED,
                "metadata": {**asset.metadata, "failure_reason": reason},
            }
        )

    @staticmethod
    def _extension(content_type: str, source_url: str) -> str:
        by_type = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        if content_type in by_type:
            return by_type[content_type]
        suffix = Path(urlparse(source_url).path).suffix
        if suffix and len(suffix) <= 8:
            return suffix
        return ".img"
