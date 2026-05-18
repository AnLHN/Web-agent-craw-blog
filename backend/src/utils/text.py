from urllib.parse import urlparse
import re

from src.models.schemas import SourceItem


def extract_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower().strip()
        return netloc.replace("www.", "")
    except Exception:
        return "unknown"


def sanitize_snippet(text: str) -> str:
    cleaned = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(
        r"^\s*(skip to content|skip to main content|jump to content)\b[\s:#\-|]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(menu|navigation|home)\s*[|>:/-]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" -|:;")


def build_summary(query: str, sources: list[SourceItem]) -> str:
    if not sources:
        return f"Khong tim thay nguon phu hop cho truy van: {query}."

    lines = []
    for index, source in enumerate(sources[:3], start=1):
        snippet = sanitize_snippet(source.snippet)
        if not snippet:
            snippet = source.title
        lines.append(f"{index}. {snippet} (nguon: {source.domain})")

    return " ".join(lines)


def finalize_summary_for_response(summary: str, query: str, sources: list[SourceItem]) -> str:
    cleaned = (summary or "").replace("\r", "").replace("**", "").strip()
    cleaned = re.sub(r"^\s*(duoi day)[^:\n]{0,240}:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^\s*(skip to content|skip to main content|jump to content)\b[\s:#\-|]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^[ \t]*[-*][ \t]+", "", cleaned, flags=re.MULTILINE)

    lines = [line.rstrip() for line in cleaned.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    while lines:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
            continue
        if tail in {"*", "-"}:
            lines.pop()
            continue
        if re.search(r"(?:^|\s)(?:\d{1,3}[.)]?|[-*])\s*$", tail):
            lines.pop()
            continue
        break

    cleaned = "\n".join(lines).strip()
    if not cleaned:
        return build_summary(query=query, sources=sources)
    return cleaned


def cap_summary_length(text: str, max_chars: int) -> str:
    cleaned = (text or "").strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned

    candidate = cleaned[:max_chars].rstrip()
    last_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
    if last_end >= int(max_chars * 0.6):
        return candidate[: last_end + 1].strip()
    return candidate.rstrip(" ,;:-")


def compute_confidence(sources: list[SourceItem]) -> float:
    if not sources:
        return 0.0

    unique_domains = len({source.domain for source in sources})
    volume_score = min(len(sources) / 5.0, 1.0)
    diversity_score = min(unique_domains / 4.0, 1.0)
    avg_score = sum(source.score for source in sources) / len(sources)
    normalized_score = max(0.0, min(avg_score, 1.0))

    confidence = (0.45 * volume_score) + (0.35 * diversity_score) + (0.20 * normalized_score)
    return round(min(confidence, 0.99), 2)


def is_quality_enough(sources: list[SourceItem], min_results: int, min_domains: int) -> bool:
    if len(sources) < min_results:
        return False

    unique_domains = len({source.domain for source in sources})
    return unique_domains >= min_domains
