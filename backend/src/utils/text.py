from urllib.parse import urlparse

from src.models.schemas import SourceItem


def extract_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower().strip()
        return netloc.replace("www.", "")
    except Exception:
        return "unknown"


def build_summary(query: str, sources: list[SourceItem]) -> str:
    if not sources:
        return f"Khong tim thay nguon phu hop cho truy van: {query}."

    lines = []
    for index, source in enumerate(sources[:3], start=1):
        snippet = source.snippet.strip().replace("\n", " ")
        if not snippet:
            snippet = source.title
        lines.append(f"{index}. {snippet} (nguon: {source.domain})")

    return " ".join(lines)


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
