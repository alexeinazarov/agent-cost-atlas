from __future__ import annotations

import math
from typing import Any

from .config import SearchConfig
from .text import contains_any, count_terms, normalize


def repository_metadata_text(repository: dict[str, Any]) -> str:
    topics = repository.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    return normalize(
        " ".join(
            [
                str(repository.get("name") or ""),
                str(repository.get("description") or ""),
                " ".join(str(topic) for topic in topics),
            ]
        )
    )


def metadata_score(
    repository: dict[str, Any], matched_searches: set[str], config: SearchConfig
) -> int:
    text = repository_metadata_text(repository)
    ranking = config.ranking
    score = (
        min(len(matched_searches), ranking.query_recurrence_cap)
        * ranking.query_recurrence_weight
    )
    score += count_terms(text, config.domain_terms) * ranking.domain_term_weight
    score += count_terms(text, config.economic_terms) * ranking.economic_term_weight
    score += count_terms(text, config.forward_terms) * ranking.forward_term_weight

    stars = int(repository.get("stargazers_count") or 0)
    popularity = int(math.log10(max(1, stars + 1)))
    score += min(ranking.popularity_score_cap, popularity)
    if repository.get("archived"):
        score -= ranking.archived_penalty
    if repository.get("fork"):
        score -= ranking.fork_penalty
    return score


def readme_score(readme: str, config: SearchConfig) -> int:
    text = normalize(readme)
    if not text:
        return 0
    if not contains_any(text, config.domain_terms):
        return -config.ranking.readme_base_score
    if not contains_any(text, config.economic_terms):
        return -config.ranking.readme_base_score
    return (
        config.ranking.readme_base_score
        + min(8, count_terms(text, config.economic_terms) * 2)
        + min(16, count_terms(text, config.forward_terms) * 4)
    )


def is_relevant(metadata_text: str, readme: str, config: SearchConfig) -> bool:
    combined = normalize(f"{metadata_text} {readme}")
    return contains_any(combined, config.domain_terms) and contains_any(
        combined, config.economic_terms
    )
