from __future__ import annotations

import hashlib
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("config/search.toml")


class ConfigurationError(ValueError):
    """Raised when the research configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class RankingConfig:
    min_final_score: int
    query_recurrence_cap: int
    query_recurrence_weight: int
    domain_term_weight: int
    economic_term_weight: int
    forward_term_weight: int
    readme_base_score: int
    popularity_score_cap: int
    archived_penalty: int
    fork_penalty: int


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    api_base_url: str
    api_version: str
    user_agent: str
    per_page: int
    max_pages_per_query: int
    readme_limit: int
    search_delay_seconds: float
    core_delay_seconds: float
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True, slots=True)
class SearchConfig:
    schema_version: str
    project: str
    github: GitHubConfig
    ranking: RankingConfig
    search_modes: tuple[str, ...]
    domain_terms: tuple[str, ...]
    economic_terms: tuple[str, ...]
    forward_terms: tuple[str, ...]
    queries: tuple[str, ...]
    source_path: Path
    source_sha256: str


def _table(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError(f"Missing or invalid [{key}] table")
    return value


def _strings(table: dict[str, Any], key: str) -> tuple[str, ...]:
    value = table.get(key)
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{key!r} must be a non-empty TOML array")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigurationError(f"Every value in {key!r} must be a non-empty string")
    cleaned = tuple(item.strip() for item in value)
    if len(cleaned) != len(set(cleaned)):
        raise ConfigurationError(f"Duplicate entries found in {key!r}")
    return cleaned


def _integer(table: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ConfigurationError(f"{key!r} must be an integer >= {minimum}")
    return value


def _number(table: dict[str, Any], key: str, *, minimum: float = 0.0) -> float:
    value = table.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < minimum:
        raise ConfigurationError(f"{key!r} must be a number >= {minimum}")
    return float(value)


def _find_project_root() -> Path:
    candidates: list[Path] = []
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        candidates.append(Path(workspace).resolve())
    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve())

    checked: set[Path] = set()
    for candidate in candidates:
        start = candidate if candidate.is_dir() else candidate.parent
        for directory in (start, *start.parents):
            if directory in checked:
                continue
            checked.add(directory)
            if (directory / "pyproject.toml").is_file():
                return directory

    searched = ", ".join(str(path) for path in candidates)
    raise ConfigurationError(
        "Could not locate the repository root (pyproject.toml). "
        f"Starting points: {searched}. Pass --config explicitly if needed."
    )


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
    else:
        path = (_find_project_root() / DEFAULT_CONFIG).resolve()

    if not path.is_file():
        raise ConfigurationError(
            f"Search configuration not found: {path}. "
            "Expected config/search.toml or pass --config PATH."
        )
    return path


def load_config(path: str | Path | None = None) -> SearchConfig:
    source_path = resolve_config_path(path)
    raw = source_path.read_bytes()

    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Invalid TOML in {source_path}: {exc}") from exc

    research = _table(document, "research")
    github = _table(document, "github")
    ranking = _table(document, "ranking")
    discovery = _table(document, "discovery")
    terms = _table(document, "terms")
    queries = _table(document, "queries")

    schema_version = research.get("schema_version")
    project = research.get("project")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ConfigurationError("research.schema_version must be a non-empty string")
    if not isinstance(project, str) or not project.strip():
        raise ConfigurationError("research.project must be a non-empty string")

    api_base_url = github.get("api_base_url")
    api_version = github.get("api_version")
    user_agent = github.get("user_agent")
    for key, value in {
        "api_base_url": api_base_url,
        "api_version": api_version,
        "user_agent": user_agent,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"github.{key} must be a non-empty string")

    per_page = _integer(github, "per_page", minimum=1)
    if per_page > 100:
        raise ConfigurationError("github.per_page cannot exceed 100")

    modes = _strings(discovery, "search_modes")
    unsupported = set(modes) - {"best_match", "updated", "stars"}
    if unsupported:
        raise ConfigurationError(f"Unsupported search modes: {sorted(unsupported)}")

    return SearchConfig(
        schema_version=schema_version.strip(),
        project=project.strip(),
        github=GitHubConfig(
            api_base_url=api_base_url.rstrip("/"),
            api_version=api_version.strip(),
            user_agent=user_agent.strip(),
            per_page=per_page,
            max_pages_per_query=_integer(github, "max_pages_per_query", minimum=1),
            readme_limit=_integer(github, "readme_limit", minimum=1),
            search_delay_seconds=_number(github, "search_delay_seconds"),
            core_delay_seconds=_number(github, "core_delay_seconds"),
            timeout_seconds=_number(github, "timeout_seconds", minimum=1.0),
            max_retries=_integer(github, "max_retries", minimum=1),
        ),
        ranking=RankingConfig(
            min_final_score=_integer(ranking, "min_final_score"),
            query_recurrence_cap=_integer(ranking, "query_recurrence_cap", minimum=1),
            query_recurrence_weight=_integer(ranking, "query_recurrence_weight"),
            domain_term_weight=_integer(ranking, "domain_term_weight"),
            economic_term_weight=_integer(ranking, "economic_term_weight"),
            forward_term_weight=_integer(ranking, "forward_term_weight"),
            readme_base_score=_integer(ranking, "readme_base_score"),
            popularity_score_cap=_integer(ranking, "popularity_score_cap"),
            archived_penalty=_integer(ranking, "archived_penalty"),
            fork_penalty=_integer(ranking, "fork_penalty"),
        ),
        search_modes=modes,
        domain_terms=_strings(terms, "domain"),
        economic_terms=_strings(terms, "economic"),
        forward_terms=_strings(terms, "forward"),
        queries=_strings(queries, "items"),
        source_path=source_path,
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )
