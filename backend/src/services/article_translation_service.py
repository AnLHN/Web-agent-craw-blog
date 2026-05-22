from dataclasses import dataclass, field
from typing import Any
from typing import Callable

from src.config.settings import Settings
from src.models.article_schemas import (
    ArticleBlock,
    ArticleBlockType,
    ArticleDraftPreview,
    ArticleImportRun,
    ArticleImportStatus,
    ArticlePromptUsage,
)
from src.services.article_llm_provider import ArticleLlmProvider, ArticleTranslationRequest
from src.services.article_prompt_service import ArticlePromptService


@dataclass(frozen=True)
class ArticleTranslationOutcome:
    status: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class ArticleTranslationService:
    BATCH_SIZE = 4
    CAPTION_BLOCK_PREFIX = "cap::"

    def __init__(self, settings: Settings, prompt_service: ArticlePromptService, provider: ArticleLlmProvider):
        self.settings = settings
        self.prompt_service = prompt_service
        self.provider = provider

    async def translate_run(
        self,
        run: ArticleImportRun,
        on_batch_progress: Callable[[int, int], None] | None = None,
    ) -> ArticleTranslationOutcome:
        if not getattr(self.provider, "configured", True):
            run.metadata["translation_status"] = "skipped_no_provider"
            run.prompt_usage = self._prompt_usage(provider="none", model=None)
            return ArticleTranslationOutcome(status="skipped_no_provider")

        try:
            asset_by_id = {asset.id: asset for asset in run.assets}
            payload, provider_name, model = await self._translate_payload_in_batches(
                run,
                on_batch_progress=on_batch_progress,
            )
            warnings = self._apply_payload(run=run, payload=payload, asset_by_id=asset_by_id)
            run.prompt_usage = self._prompt_usage(provider=provider_name, model=model)
            failed_batches = self._string_list(run.metadata.get("translation_failed_batches"))
            paused = bool(run.metadata.get("translation_paused"))
            status = "partial" if failed_batches or paused else "translated"
            run.metadata["translation_status"] = status
            if failed_batches:
                run.metadata["translation_error"] = failed_batches[-1]
            else:
                run.metadata.pop("translation_error", None)
            if warnings:
                run.metadata["translation_warnings"] = warnings
            else:
                run.metadata.pop("translation_warnings", None)
            run.status = ArticleImportStatus.TRANSLATED
            return ArticleTranslationOutcome(status=status, warnings=warnings)
        except Exception as exc:
            run.metadata["translation_status"] = "failed"
            run.metadata["translation_error"] = str(exc) or exc.__class__.__name__
            run.metadata.pop("translation_pause_reason", None)
            run.metadata.pop("translation_paused", None)
            run.metadata.pop("translation_failed_batches", None)
            run.prompt_usage = self._prompt_usage(provider="9router_openai", model=self.settings.article_openai_model)
            return ArticleTranslationOutcome(status="failed", error=str(exc) or exc.__class__.__name__)

    async def _translate_payload_in_batches(
        self,
        run: ArticleImportRun,
        on_batch_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[dict[str, Any], str, str | None]:
        asset_by_id = {asset.id: asset for asset in run.assets}
        blocks_to_translate = [
            block
            for block in run.blocks
            if block.block_type not in {ArticleBlockType.IMAGE, ArticleBlockType.UNKNOWN}
            and not (block.translated_text or "").strip()
        ]
        blocks_to_translate.extend(self._caption_virtual_blocks(run=run, asset_by_id=asset_by_id))
        batches = self._translation_batches(blocks_to_translate)
        if not batches:
            existing = run.draft
            run.metadata.pop("translation_failed_batches", None)
            run.metadata.pop("translation_paused", None)
            run.metadata.pop("translation_pause_reason", None)
            if on_batch_progress:
                on_batch_progress(1, 1)
            return {
                "title_vi": existing.title if existing else run.source.title,
                "excerpt_vi": existing.excerpt if existing else None,
                "slug": existing.slug if existing else None,
                "tags": existing.tags if existing else [],
                "categories": existing.categories if existing else [],
                "translated_blocks": [],
                "warnings": [],
            }, "9router_openai", self.settings.article_openai_model

        merged: dict[str, Any] = {
            "title_vi": None,
            "excerpt_vi": None,
            "slug": None,
            "tags": [],
            "categories": [],
            "translated_blocks": [],
            "warnings": [],
        }
        provider_name = "9router_openai"
        model: str | None = self.settings.article_openai_model
        glossary = self._default_glossary()
        failed_batches: list[str] = []
        max_batches = max(1, int(self.settings.article_translation_max_batches_per_run))
        system_prompt = (
            self.prompt_service.system_prompt()
            + "\n\nYou are translating one batch from a longer article. "
            "Return JSON for only the provided blocks. Keep block_id unchanged."
        )

        for batch_index, batch in enumerate(batches, start=1):
            if batch_index > max_batches:
                run.metadata["translation_paused"] = True
                run.metadata["translation_pause_reason"] = (
                    f"translated_{max_batches}_batches_this_run_press_translate_to_continue"
                )
                run.metadata["translation_batch_count"] = len(batches)
                run.metadata["translation_last_batch"] = batch_index - 1
                merged["warnings"].append("translation_paused:press_translate_to_continue")
                break
            try:
                result = await self.provider.translate_blocks(
                    ArticleTranslationRequest(
                        source=run.source,
                        blocks=batch,
                        target_language=run.target_language,
                        glossary=glossary,
                        system_prompt=system_prompt,
                    )
                )
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                failed = f"batch_{batch_index}:{error}"
                failed_batches.append(failed)
                merged["warnings"].append(f"translation_batch_failed:{failed}")
                run.metadata["translation_batch_count"] = len(batches)
                run.metadata["translation_last_batch"] = batch_index
                run.metadata["translation_failed_batches"] = failed_batches
                if on_batch_progress:
                    on_batch_progress(batch_index, len(batches))
                transient_quota_or_load = self._is_transient_translation_error(error)
                if transient_quota_or_load:
                    run.metadata["translation_paused"] = True
                    run.metadata["translation_pause_reason"] = "provider_temporarily_unavailable_retry_later"
                    break
                continue
            provider_name = result.provider
            model = result.model
            payload = result.payload
            for key in ("title_vi", "excerpt_vi", "slug"):
                if not merged.get(key) and self._optional_str(payload.get(key)):
                    merged[key] = self._optional_str(payload.get(key))
            if not merged["tags"]:
                merged["tags"] = self._string_list(payload.get("tags"))
            if not merged["categories"]:
                merged["categories"] = self._string_list(payload.get("categories"))
            merged["translated_blocks"].extend(
                item for item in payload.get("translated_blocks") or [] if isinstance(item, dict)
            )
            merged["warnings"].extend(str(item) for item in payload.get("warnings") or [] if str(item).strip())
            run.metadata["translation_batch_count"] = len(batches)
            run.metadata["translation_last_batch"] = batch_index
            if on_batch_progress:
                on_batch_progress(batch_index, len(batches))

        if failed_batches:
            run.metadata["translation_failed_batches"] = failed_batches
        else:
            run.metadata.pop("translation_failed_batches", None)
        if not failed_batches and not run.metadata.get("translation_paused"):
            run.metadata.pop("translation_pause_reason", None)
        return merged, provider_name, model

    def _apply_payload(self, run: ArticleImportRun, payload: dict[str, Any], asset_by_id: dict[str, Any]) -> list[str]:
        warnings: list[str] = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
        translated_by_id = {
            str(item.get("block_id")): item
            for item in payload.get("translated_blocks") or []
            if isinstance(item, dict) and item.get("block_id")
        }

        for block_id, translated in translated_by_id.items():
            if not block_id.startswith(self.CAPTION_BLOCK_PREFIX):
                continue
            caption_vi = str(translated.get("text_vi") or "").strip()
            if not caption_vi:
                continue
            target_id = block_id.removeprefix(self.CAPTION_BLOCK_PREFIX)
            asset = asset_by_id.get(target_id)
            if asset:
                asset.metadata["caption_vi"] = caption_vi
                continue
            target_block = next((item for item in run.blocks if item.id == target_id), None)
            if target_block:
                target_block.metadata["caption_vi"] = caption_vi

        for block in run.blocks:
            translated = translated_by_id.get(block.id)
            if not translated:
                if block.translated_text:
                    continue
                if block.block_type not in {ArticleBlockType.IMAGE, ArticleBlockType.UNKNOWN}:
                    warnings.append(f"missing_translation:{block.id}")
                continue
            text_vi = str(translated.get("text_vi") or "").strip()
            if block.block_type == ArticleBlockType.CODE:
                if text_vi != (block.source_text or ""):
                    warnings.append(f"code_block_changed:{block.id}")
                block.translated_text = block.source_text
                continue
            if text_vi:
                block.translated_text = text_vi

        if run.draft:
            run.draft.title = self._optional_str(payload.get("title_vi"))
            run.draft.excerpt = self._optional_str(payload.get("excerpt_vi"))
            run.draft.slug = self._optional_str(payload.get("slug"))
            run.draft.tags = self._string_list(payload.get("tags"))
            run.draft.categories = self._string_list(payload.get("categories"))
        else:
            run.draft = ArticleDraftPreview(
                title=self._optional_str(payload.get("title_vi")),
                excerpt=self._optional_str(payload.get("excerpt_vi")),
                slug=self._optional_str(payload.get("slug")),
                tags=self._string_list(payload.get("tags")),
                categories=self._string_list(payload.get("categories")),
            )
        return warnings

    def _translation_batches(self, blocks: list[ArticleBlock]) -> list[list[ArticleBlock]]:
        max_blocks = max(1, int(self.settings.article_translation_batch_size))
        max_chars = max(1000, int(self.settings.article_translation_max_batch_chars))
        batches: list[list[ArticleBlock]] = []
        current: list[ArticleBlock] = []
        current_chars = 0

        for block in blocks:
            block_chars = len(block.source_text or "")
            should_flush = bool(current) and (
                len(current) >= max_blocks or current_chars + block_chars > max_chars
            )
            if should_flush:
                batches.append(current)
                current = []
                current_chars = 0
            current.append(block)
            current_chars += block_chars

        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _is_transient_translation_error(error: str) -> bool:
        transient_markers = (
            "ninerouter_http_429",
            "ninerouter_http_500",
            "ninerouter_http_502",
            "ninerouter_http_503",
            "ninerouter_http_504",
            "reset after",
            "timeout",
            "timed out",
            "UNAVAILABLE",
        )
        return any(marker in error for marker in transient_markers)

    def _caption_virtual_blocks(self, run: ArticleImportRun, asset_by_id: dict[str, Any]) -> list[ArticleBlock]:
        virtual_blocks: list[ArticleBlock] = []
        table_or_embed_captions: list[ArticleBlock] = []
        for block in run.blocks:
            if block.block_type != ArticleBlockType.IMAGE or not block.asset_id:
                if block.block_type in {ArticleBlockType.TABLE, ArticleBlockType.EMBED}:
                    source_caption = str(block.metadata.get("caption") or "").strip()
                    caption_vi = str(block.metadata.get("caption_vi") or "").strip()
                    if source_caption and not caption_vi:
                        table_or_embed_captions.append(
                            ArticleBlock(
                                id=f"{self.CAPTION_BLOCK_PREFIX}{block.id}",
                                order_index=block.order_index,
                                block_type=ArticleBlockType.PARAGRAPH,
                                source_text=source_caption,
                                metadata={"kind": f"{block.block_type.value}_caption", "block_id": block.id},
                            )
                        )
                continue
            asset = asset_by_id.get(block.asset_id)
            if not asset:
                continue
            source_caption = str(asset.caption or block.metadata.get("caption") or "").strip()
            if not source_caption:
                continue
            if str(asset.metadata.get("caption_vi") or "").strip():
                continue
            virtual_blocks.append(
                ArticleBlock(
                    id=f"{self.CAPTION_BLOCK_PREFIX}{asset.id}",
                    order_index=block.order_index,
                    block_type=ArticleBlockType.PARAGRAPH,
                    source_text=source_caption,
                    metadata={"kind": "image_caption", "asset_id": asset.id},
                )
            )
        return virtual_blocks + table_or_embed_captions

    def _prompt_usage(self, provider: str, model: str | None) -> list[ArticlePromptUsage]:
        return [
            ArticlePromptUsage(
                prompt_key=prompt.prompt_key,
                version=prompt.version,
                model=model,
                provider=provider,
            )
            for prompt in self.prompt_service.active_prompts()
        ]

    @staticmethod
    def _default_glossary() -> list[dict[str, str]]:
        return [
            {"term": "retrieval", "preferred_translation": "truy xuất"},
            {"term": "fine-tuning", "preferred_translation": "tinh chỉnh"},
            {"term": "tool calling", "preferred_translation": "gọi tool"},
            {"term": "rate limit", "preferred_translation": "giới hạn tần suất"},
            {"term": "agent", "preferred_translation": "agent"},
            {"term": "prompt", "preferred_translation": "prompt"},
        ]

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
