from __future__ import annotations

import re
from functools import lru_cache

_WHITESPACE = re.compile(r"\s+")
_MARKDOWN = re.compile(r"[`*_>#|\[\]()]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\s+[\u2013\u2014-]\s+|\n+")


def normalize(text: str | None) -> str:
    return _WHITESPACE.sub(" ", (text or "").casefold()).strip()


@lru_cache(maxsize=512)
def _term_pattern(term: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in re.split(r"[\s-]+", term.strip().casefold()) if part]
    body = r"[\s-]+".join(parts)
    return re.compile(rf"(?<!\w){body}(?!\w)")


def has_term(text: str, term: str) -> bool:
    return _term_pattern(term).search(text) is not None


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(has_term(text, term) for term in terms)


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(has_term(text, term) for term in terms)


def evidence_sentences(
    readme: str,
    *,
    domain_terms: tuple[str, ...],
    economic_terms: tuple[str, ...],
    forward_terms: tuple[str, ...],
    limit: int = 3,
) -> tuple[str, ...]:
    clean = _MARKDOWN.sub(" ", readme)
    clean = re.sub(r"[ \t]+", " ", clean)
    ranked: list[tuple[int, str]] = []

    for sentence in _SENTENCE_BREAK.split(clean):
        sentence = _WHITESPACE.sub(" ", sentence).strip()
        if len(sentence) < 35:
            continue
        low = normalize(sentence)
        if not contains_any(low, domain_terms) or not contains_any(low, economic_terms):
            continue
        weight = (
            count_terms(low, economic_terms) * 2
            + count_terms(low, forward_terms) * 4
            + count_terms(low, domain_terms)
        )
        if len(sentence) > 360:
            sentence = f"{sentence[:357].rstrip()}..."
        ranked.append((weight, sentence))

    ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1].casefold()))
    output: list[str] = []
    seen: set[str] = set()
    for _, sentence in ranked:
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(sentence)
        if len(output) == limit:
            break
    return tuple(output)
