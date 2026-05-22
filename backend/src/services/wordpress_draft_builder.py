import html
import re

from src.models.article_schemas import (
    ArticleAsset,
    ArticleBlock,
    ArticleBlockType,
    ArticleDraftAttribution,
    ArticleDraftPreview,
    ArticleImportRun,
)


class WordPressDraftBuilder:
    def build(self, run: ArticleImportRun) -> ArticleDraftPreview:
        existing = run.draft or ArticleDraftPreview()
        title = existing.title or run.source.title or "Untitled article"
        attribution = existing.source_attribution or ArticleDraftAttribution(
            url=run.source.url,
            title=run.source.title,
            domain=run.source.domain,
        )
        content = self._render_html(run=run, attribution=attribution)
        return ArticleDraftPreview(
            title=title,
            slug=existing.slug or self._slugify(title),
            excerpt=existing.excerpt or self._excerpt(run.blocks),
            content_format="html",
            content=content,
            tags=existing.tags,
            categories=existing.categories,
            source_attribution=attribution,
        )

    def _render_html(self, run: ArticleImportRun, attribution: ArticleDraftAttribution) -> str:
        asset_by_id = {asset.id: asset for asset in run.assets}
        parts: list[str] = []
        for block in sorted(run.blocks, key=lambda item: item.order_index):
            rendered = self._render_block(block=block, asset_by_id=asset_by_id)
            if rendered:
                parts.append(rendered)
        parts.append(self._render_attribution(attribution))
        return "\n\n".join(parts).strip()

    def _render_block(self, block: ArticleBlock, asset_by_id: dict[str, ArticleAsset]) -> str:
        text = block.translated_text or block.source_text or ""
        if block.block_type == ArticleBlockType.HEADING:
            level = int(block.metadata.get("level") or 2)
            level = min(max(level, 2), 4)
            return f"<h{level}>{html.escape(text)}</h{level}>"
        if block.block_type == ArticleBlockType.PARAGRAPH:
            return self._render_text_with_links(text=text, links=block.metadata.get("links"), tag_name="p")
        if block.block_type == ArticleBlockType.QUOTE:
            return self._render_text_with_links(text=text, links=block.metadata.get("links"), tag_name="blockquote")
        if block.block_type == ArticleBlockType.LIST:
            return self._render_list(block=block, text=text)
        if block.block_type == ArticleBlockType.CODE:
            language = html.escape(block.language_hint or "")
            class_attr = f' class="language-{language}"' if language else ""
            return f"<pre><code{class_attr}>{html.escape(text)}</code></pre>"
        if block.block_type == ArticleBlockType.TABLE:
            return self._render_table(block=block)
        if block.block_type == ArticleBlockType.EMBED:
            return self._render_embed(block=block)
        if block.block_type == ArticleBlockType.IMAGE and block.asset_id:
            asset = asset_by_id.get(block.asset_id)
            if not asset:
                return ""
            return self._render_image(asset)
        return ""

    @staticmethod
    def _render_list(block: ArticleBlock, text: str) -> str:
        tag_name = "ol" if block.metadata.get("list_type") == "ol" else "ul"
        items = [line.strip() for line in text.splitlines() if line.strip()]
        if not items:
            return ""
        rendered_items = "".join(
            f"<li>{WordPressDraftBuilder._render_inline_links(item, block.metadata.get('links'))}</li>"
            for item in items
        )
        return f"<{tag_name}>{rendered_items}</{tag_name}>"

    @staticmethod
    def _render_inline_links(text: str, links: object) -> str:
        if not isinstance(links, list):
            return html.escape(text)
        by_id = {
            str(link.get("id") or "").strip(): str(link.get("href") or "").strip()
            for link in links
            if isinstance(link, dict)
        }
        parts: list[str] = []
        cursor = 0
        matched_any = False
        for match in re.finditer(r"\[LINK_(\d+):([^\]]+)\]", text):
            token = f"LINK_{match.group(1)}"
            href = by_id.get(token)
            if not href:
                continue
            matched_any = True
            parts.append(html.escape(text[cursor : match.start()]))
            label = match.group(2).strip()
            parts.append(
                f'<a href="{html.escape(href, quote=True)}" rel="nofollow noopener">{html.escape(label)}</a>'
            )
            cursor = match.end()
        if matched_any:
            parts.append(html.escape(text[cursor:]))
            return "".join(parts)

        rendered = html.escape(text)
        for link in links:
            if not isinstance(link, dict):
                continue
            label = str(link.get("text") or "").strip()
            href = str(link.get("href") or "").strip()
            if not label or not href or label not in text:
                continue
            rendered_label = html.escape(label)
            rendered = rendered.replace(
                rendered_label,
                f'<a href="{html.escape(href, quote=True)}" rel="nofollow noopener">{rendered_label}</a>',
                1,
            )
        return rendered

    @staticmethod
    def _render_image(asset: ArticleAsset) -> str:
        src = asset.local_path or asset.source_url
        alt = asset.alt_text or ""
        caption = str(asset.metadata.get("caption_vi") or "").strip() or asset.caption or ""
        image_html = f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
        if caption:
            return (
                "<figure>"
                f"{image_html}"
                f"<figcaption>{html.escape(caption)}</figcaption>"
                "</figure>"
            )
        return f"<figure>{image_html}</figure>"

    @staticmethod
    def _render_attribution(attribution: ArticleDraftAttribution) -> str:
        title = attribution.title or attribution.domain
        return (
            "<p><em>Source: "
            f'<a href="{html.escape(attribution.url, quote=True)}" rel="nofollow noopener">'
            f"{html.escape(title)}</a>"
            "</em></p>"
        )

    @staticmethod
    def _render_embed(block: ArticleBlock) -> str:
        source_url = str(block.metadata.get("source_url") or block.source_text or "").strip()
        if not source_url:
            return ""
        caption = str(block.metadata.get("caption_vi") or block.metadata.get("caption") or "").strip()
        iframe = (
            f'<iframe src="{html.escape(source_url, quote=True)}" '
            'loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe>'
        )
        if caption:
            return f"<figure>{iframe}<figcaption>{html.escape(caption)}</figcaption></figure>"
        return f"<figure>{iframe}</figure>"

    @staticmethod
    def _render_table(block: ArticleBlock) -> str:
        table_html = str(block.metadata.get("table_html") or "").strip()
        caption = str(block.metadata.get("caption_vi") or block.metadata.get("caption") or "").strip()
        if table_html:
            if caption:
                return f"<figure>{table_html}<figcaption>{html.escape(caption)}</figcaption></figure>"
            return table_html
        text = block.translated_text or block.source_text or ""
        return f"<p>{WordPressDraftBuilder._escape_multiline(text)}</p>"

    @staticmethod
    def _render_text_with_links(text: str, links: object, tag_name: str) -> str:
        return f"<{tag_name}>{WordPressDraftBuilder._render_inline_links(text, links)}</{tag_name}>"

    @staticmethod
    def _escape_multiline(text: str) -> str:
        return "<br>".join(html.escape(line.strip()) for line in text.splitlines() if line.strip())

    @staticmethod
    def _excerpt(blocks: list[ArticleBlock]) -> str | None:
        for block in sorted(blocks, key=lambda item: item.order_index):
            if block.block_type != ArticleBlockType.PARAGRAPH:
                continue
            text = (block.translated_text or block.source_text or "").strip()
            if not text:
                continue
            if len(text) <= 220:
                return text
            return text[:217].rstrip() + "..."
        return None

    @staticmethod
    def _slugify(value: str) -> str:
        text = value.strip().lower()
        text = re.sub(r"[^a-z0-9\s-]", "", text)
        text = re.sub(r"[\s_-]+", "-", text)
        return text.strip("-") or "untitled-article"
