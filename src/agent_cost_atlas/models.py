from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QueryStat:
    query: str
    mode: str
    total_count: int
    retrieved: int
    pages_retrieved: int
    incomplete_results: bool
    capped_by_page_limit: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryRecord:
    repository_id: int
    full_name: str
    url: str
    description: str
    stars: int
    forks: int
    open_issues: int
    language: str | None
    license: str | None
    archived: bool
    fork: bool
    created_at: str | None
    updated_at: str | None
    pushed_at: str | None
    default_branch: str
    topics: tuple[str, ...]
    matched_searches: tuple[str, ...]
    score: int
    evidence: tuple[str, ...]
    readme_sha: str | None
    head_sha: str | None


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    schema_version: str
    run_id: str
    generated_at_utc: str
    source_commit: str | None
    config_sha256: str
    github_api_version: str
    queries_executed: int
    search_requests: int
    unique_repositories_discovered: int
    readmes_analyzed: int
    final_count: int
    query_stats: tuple[QueryStat, ...]
    repositories: tuple[RepositoryRecord, ...]
    inspection_failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
