from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from src.models.article_schemas import (
    ArticleAsset,
    ArticleBlock,
    ArticleBlockType,
    ArticleSourceInfo,
)


@dataclass(frozen=True)
class ArticleExtractionResult:
    source: ArticleSourceInfo
    blocks: list[ArticleBlock]
    assets: list[ArticleAsset]


class ArticleExtractorService:
    def extract(self, html: str, source_url: str) -> ArticleExtractionResult:
        soup = BeautifulSoup(html, "html.parser")
        self._remove_noise(soup)
        container = self._main_container(soup)
        source = self._source_info(soup=soup, source_url=source_url)
        builder = _BlockBuilder(source_url=source_url)
        builder.walk(container)
        return ArticleExtractionResult(source=source, blocks=builder.blocks, assets=builder.assets)

    @staticmethod
    def _remove_noise(soup: BeautifulSoup) -> None:
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
            tag.decompose()

    @staticmethod
    def _main_container(soup: BeautifulSoup) -> Tag:
        return soup.find("article") or soup.find("main") or soup.body or soup

    def _source_info(self, soup: BeautifulSoup, source_url: str) -> ArticleSourceInfo:
        title = self._first_text(
            [
                soup.find("meta", attrs={"property": "og:title"}),
                soup.find("h1"),
                soup.find("title"),
            ],
            attr="content",
        )
        author = self._first_text(
            [
                soup.find("meta", attrs={"name": "author"}),
                soup.find("meta", attrs={"property": "article:author"}),
                soup.find(attrs={"class": "author"}),
            ],
            attr="content",
        )
        published_at = self._published_at(soup)
        return ArticleSourceInfo(
            url=source_url,
            domain=urlparse(source_url).netloc,
            title=title,
            author=author,
            published_at=published_at,
        )

    @staticmethod
    def _first_text(items: Iterable[Tag | None], attr: str) -> str | None:
        for item in items:
            if item is None:
                continue
            value = item.get(attr) if item.has_attr(attr) else item.get_text(" ", strip=True)
            if value:
                return str(value).strip()
        return None

    @staticmethod
    def _published_at(soup: BeautifulSoup) -> datetime | None:
        candidates = [
            soup.find("meta", attrs={"property": "article:published_time"}),
            soup.find("meta", attrs={"name": "date"}),
            soup.find("time"),
        ]
        for item in candidates:
            if item is None:
                continue
            raw = item.get("content") or item.get("datetime") or item.get_text(" ", strip=True)
            if not raw:
                continue
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
        return None


class _BlockBuilder:
    def __init__(self, source_url: str):
        self.source_url = source_url
        self.blocks: list[ArticleBlock] = []
        self.assets: list[ArticleAsset] = []
        self._block_count = 0
        self._asset_count = 0

    def walk(self, node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            self._visit(child)

    def _visit(self, tag: Tag) -> None:
        name = tag.name.lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._add_text_block(
                block_type=ArticleBlockType.HEADING,
                text=tag.get_text(" ", strip=True),
                metadata={"level": int(name[1])},
            )
            return
        if name == "p":
            text, links = self._text_with_link_placeholders(tag)
            self._add_text_block(
                block_type=ArticleBlockType.PARAGRAPH,
                text=text,
                metadata={"links": links},
            )
            return
        if name == "blockquote":
            text, links = self._text_with_link_placeholders(tag)
            self._add_text_block(
                block_type=ArticleBlockType.QUOTE,
                text=text,
                metadata={"links": links},
            )
            return
        if name in {"ul", "ol"}:
            self._add_list_block(tag)
            return
        if name == "li":
            text, links = self._text_with_link_placeholders(tag)
            self._add_text_block(
                block_type=ArticleBlockType.PARAGRAPH,
                text=text,
                metadata={"list_item": True, "links": links},
            )
            return
        if name == "pre":
            self._add_text_block(
                block_type=ArticleBlockType.CODE,
                text=tag.get_text("\n", strip=False).strip(),
                metadata={},
                language_hint=self._language_hint(tag),
            )
            return
        if name == "code":
            self._add_text_block(
                block_type=ArticleBlockType.PARAGRAPH,
                text=tag.get_text(" ", strip=True),
                metadata={"inline_code": True},
            )
            return
        if name == "figure":
            caption = self._caption(tag)
            for img in tag.find_all("img"):
                self._add_image_block(img, caption=caption)
            for iframe in tag.find_all("iframe"):
                self._add_embed_block(iframe, caption=caption)
            for video in tag.find_all("video"):
                self._add_embed_block(video, caption=caption)
            for table in tag.find_all("table"):
                self._add_table_block(table, caption=caption)
            return
        if name == "img":
            self._add_image_block(tag, caption=None)
            return
        if name in {"iframe", "video"}:
            self._add_embed_block(tag, caption=None)
            return
        if name == "table":
            self._add_table_block(tag, caption=None)
            return

        self.walk(tag)

    def _add_text_block(
        self,
        block_type: ArticleBlockType,
        text: str,
        metadata: dict,
        language_hint: str | None = None,
    ) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        self._block_count += 1
        self.blocks.append(
            ArticleBlock(
                id=f"b{self._block_count}",
                order_index=len(self.blocks),
                block_type=block_type,
                source_text=cleaned,
                language_hint=language_hint,
                metadata=metadata,
            )
        )

    def _add_list_block(self, tag: Tag) -> None:
        items: list[str] = []
        links: list[dict[str, str]] = []
        link_index = 1
        for item in tag.find_all("li", recursive=False):
            text, item_links = self._text_with_link_placeholders(item, start_index=link_index)
            if text:
                items.append(text)
            links.extend(item_links)
            link_index += len(item_links)
        if not items:
            return
        self._block_count += 1
        self.blocks.append(
            ArticleBlock(
                id=f"b{self._block_count}",
                order_index=len(self.blocks),
                block_type=ArticleBlockType.LIST,
                source_text="\n".join(items),
                metadata={"list_type": tag.name.lower(), "items": items, "links": links},
            )
        )

    def _add_image_block(self, img: Tag, caption: str | None) -> None:
        # Prefer lazy-load attributes over placeholder src (often data:image/svg+xml).
        raw_src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("data-lazy-src")
            or img.get("src")
        )
        if not raw_src:
            return
        if str(raw_src).strip().startswith("data:"):
            raw_src = img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
            if not raw_src:
                return
        self._asset_count += 1
        asset_id = f"asset_{self._asset_count}"
        source_url = urljoin(self.source_url, str(raw_src))
        alt_text = str(img.get("alt") or "").strip() or None
        srcset = str(img.get("data-srcset") or img.get("srcset") or "").strip() or None
        self.assets.append(
            ArticleAsset(
                id=asset_id,
                source_url=source_url,
                alt_text=alt_text,
                caption=caption,
                metadata={
                    "page_url": self.source_url,
                    "srcset": srcset,
                    "data_srcset": str(img.get("data-srcset") or "").strip() or None,
                },
            )
        )
        self._block_count += 1
        self.blocks.append(
            ArticleBlock(
                id=f"b{self._block_count}",
                order_index=len(self.blocks),
                block_type=ArticleBlockType.IMAGE,
                asset_id=asset_id,
                metadata={"source_url": source_url, "alt_text": alt_text, "caption": caption, "srcset": srcset},
            )
        )

    def _add_embed_block(self, tag: Tag, caption: str | None) -> None:
        raw_src = tag.get("src") or tag.get("data-src")
        if not raw_src and tag.name.lower() == "video":
            source_child = tag.find("source")
            if source_child:
                raw_src = source_child.get("src")
        if not raw_src:
            return
        source_url = urljoin(self.source_url, str(raw_src))
        host = urlparse(source_url).netloc.lower()
        embed_type = "youtube" if ("youtube.com" in host or "youtu.be" in host) else "embed"
        self._block_count += 1
        self.blocks.append(
            ArticleBlock(
                id=f"b{self._block_count}",
                order_index=len(self.blocks),
                block_type=ArticleBlockType.EMBED,
                source_text=source_url,
                metadata={"embed_type": embed_type, "source_url": source_url, "caption": caption},
            )
        )

    def _add_table_block(self, tag: Tag, caption: str | None) -> None:
        text = tag.get_text(" | ", strip=True)
        if not text.strip():
            return
        self._block_count += 1
        self.blocks.append(
            ArticleBlock(
                id=f"b{self._block_count}",
                order_index=len(self.blocks),
                block_type=ArticleBlockType.TABLE,
                source_text=text,
                metadata={"table_html": str(tag), "caption": caption},
            )
        )

    def _text_with_link_placeholders(self, tag: Tag, start_index: int = 1) -> tuple[str, list[dict[str, str]]]:
        clone = BeautifulSoup(str(tag), "html.parser")
        root = clone.find(tag.name)
        if root is None:
            return tag.get_text(" ", strip=True), []

        links: list[dict[str, str]] = []
        for index, item in enumerate(root.find_all("a"), start=start_index):
            href = item.get("href")
            label = item.get_text(" ", strip=True)
            if not href or not label:
                continue
            token = f"LINK_{index}"
            item.replace_with(f"[{token}:{label}]")
            links.append({"id": token, "text": label, "href": urljoin(self.source_url, str(href))})
        return root.get_text(" ", strip=True), links

    @staticmethod
    def _caption(tag: Tag) -> str | None:
        caption = tag.find("figcaption")
        if not caption:
            return None
        text = caption.get_text(" ", strip=True)
        return text or None

    @staticmethod
    def _language_hint(tag: Tag) -> str | None:
        class_names = tag.get("class") or []
        for class_name in class_names:
            value = str(class_name)
            if value.startswith("language-"):
                return value.removeprefix("language-")
        text = tag.get_text("\n", strip=False)
        lowered = text.lower()
        if any(marker in lowered for marker in ["npm ", "sudo ", "docker ", "pip install", "#!/bin/bash"]):
            return "bash"
        if "python" in lowered or "def " in text:
            return "python"
        return None
