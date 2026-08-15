from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SearchConfig
from .github import GitHubApiError, GitHubClient
from .models import DiscoveryRun, QueryStat, RepositoryRecord
from .report import write_results
from .scoring import is_relevant, metadata_score, readme_score, repository_metadata_text
from .text import evidence_sentences

# A single unreachable repository must not end the sweep, but a long run of
# consecutive failures means the API is no longer answering usefully and the
# snapshot would understate coverage without saying so.
MAX_CONSECUTIVE_FAILURES = 10


class DiscoveryEngine:
    def __init__(self, config: SearchConfig, client: GitHubClient) -> None:
        self.config = config
        self.client = client

    def run(self) -> DiscoveryRun:
        repositories: dict[str, dict[str, Any]] = {}
        matched_searches: dict[str, set[str]] = {}
        query_stats: list[QueryStat] = []
        total_searches = len(self.config.queries) * len(self.config.search_modes)
        search_number = 0
        consecutive_failures = 0

        for query in self.config.queries:
            for mode in self.config.search_modes:
                search_number += 1
                print(f"[{search_number}/{total_searches}] search: {query!r} ({mode})", flush=True)
                try:
                    items, stat = self.client.search_repositories(query, mode)
                except GitHubApiError as exc:
                    if exc.rate_limited:
                        raise
                    consecutive_failures += 1
                    print(f"  search failed: {exc}", flush=True)
                    query_stats.append(
                        QueryStat(
                            query=query,
                            mode=mode,
                            total_count=0,
                            retrieved=0,
                            pages_retrieved=0,
                            incomplete_results=False,
                            capped_by_page_limit=False,
                            error=str(exc),
                        )
                    )
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        raise GitHubApiError(
                            f"Aborting after {consecutive_failures} consecutive search "
                            f"failures. Last error: {exc}"
                        ) from exc
                    continue

                consecutive_failures = 0
                query_stats.append(stat)
                search_key = f"{query} [{mode}]"
                for repository in items:
                    full_name = repository.get("full_name")
                    if not isinstance(full_name, str) or not full_name:
                        continue
                    # Identity is the numeric repository ID where available, so a
                    # repository renamed between runs is not counted twice.
                    identity = str(repository.get("id") or "") or full_name
                    repositories.setdefault(identity, repository)
                    matched_searches.setdefault(identity, set()).add(search_key)

        candidates = [
            (
                metadata_score(repository, matched_searches[identity], self.config),
                identity,
                repository,
            )
            for identity, repository in repositories.items()
        ]
        candidates.sort(
            key=lambda item: (
                -item[0],
                -int(item[2].get("stargazers_count") or 0),
                str(item[2].get("full_name") or "").casefold(),
            )
        )
        candidates = candidates[: self.config.github.readme_limit]

        print(f"Unique repositories discovered: {len(repositories)}", flush=True)
        print(f"Inspecting {len(candidates)} candidate READMEs", flush=True)

        retained: list[RepositoryRecord] = []
        inspection_failures: list[str] = []
        consecutive_failures = 0

        for index, (base_score, identity, repository) in enumerate(candidates, start=1):
            full_name = str(repository.get("full_name") or identity)
            print(f"[{index}/{len(candidates)}] README: {full_name}", flush=True)
            try:
                record = self._inspect(
                    base_score, full_name, repository, matched_searches[identity]
                )
            except GitHubApiError as exc:
                if exc.rate_limited:
                    raise
                consecutive_failures += 1
                inspection_failures.append(f"{full_name}: {exc}")
                print(f"  skipped after API error: {exc}", flush=True)
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise GitHubApiError(
                        f"Aborting after {consecutive_failures} consecutive repository "
                        f"failures. Last error: {exc}"
                    ) from exc
                continue

            consecutive_failures = 0
            if record is not None:
                retained.append(record)

        retained.sort(key=lambda repo: (-repo.score, -repo.stars, repo.full_name.casefold()))
        now = datetime.now(UTC).replace(microsecond=0)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        source_commit = os.environ.get("GITHUB_SHA") or None
        run_id = f"{timestamp}-{source_commit[:8]}" if source_commit else timestamp

        if inspection_failures:
            print(f"Repositories skipped after API errors: {len(inspection_failures)}", flush=True)

        return DiscoveryRun(
            schema_version=self.config.schema_version,
            run_id=run_id,
            generated_at_utc=now.isoformat().replace("+00:00", "Z"),
            source_commit=source_commit,
            config_sha256=self.config.source_sha256,
            github_api_version=self.config.github.api_version,
            queries_executed=total_searches,
            search_requests=sum(stat.pages_retrieved for stat in query_stats),
            unique_repositories_discovered=len(repositories),
            readmes_analyzed=len(candidates),
            final_count=len(retained),
            query_stats=tuple(query_stats),
            repositories=tuple(retained),
            inspection_failures=tuple(inspection_failures),
        )

    def _inspect(
        self,
        base_score: int,
        full_name: str,
        repository: dict[str, Any],
        matched_searches: set[str],
    ) -> RepositoryRecord | None:
        readme = self.client.fetch_readme(full_name)
        metadata_text = repository_metadata_text(repository)
        score = base_score + readme_score(readme.text, self.config)

        if score < self.config.ranking.min_final_score:
            return None
        if not is_relevant(metadata_text, readme.text, self.config):
            return None

        default_branch = str(repository.get("default_branch") or "")
        head_sha = (
            self.client.fetch_head_sha(full_name, default_branch) if default_branch else None
        )
        license_data = repository.get("license") or {}
        license_id = license_data.get("spdx_id") if isinstance(license_data, dict) else None
        topics = repository.get("topics") or []
        if not isinstance(topics, list):
            topics = []

        return RepositoryRecord(
            repository_id=int(repository.get("id") or 0),
            full_name=full_name,
            url=str(repository.get("html_url") or ""),
            description=str(repository.get("description") or ""),
            stars=int(repository.get("stargazers_count") or 0),
            forks=int(repository.get("forks_count") or 0),
            open_issues=int(repository.get("open_issues_count") or 0),
            language=(
                str(repository["language"]) if repository.get("language") is not None else None
            ),
            license=(str(license_id) if license_id else None),
            archived=bool(repository.get("archived")),
            fork=bool(repository.get("fork")),
            created_at=(str(repository["created_at"]) if repository.get("created_at") else None),
            updated_at=(str(repository["updated_at"]) if repository.get("updated_at") else None),
            pushed_at=(str(repository["pushed_at"]) if repository.get("pushed_at") else None),
            default_branch=default_branch,
            topics=tuple(str(topic) for topic in topics),
            matched_searches=tuple(sorted(matched_searches)),
            score=score,
            evidence=evidence_sentences(
                readme.text,
                domain_terms=self.config.domain_terms,
                economic_terms=self.config.economic_terms,
                forward_terms=self.config.forward_terms,
            ),
            readme_sha=readme.sha,
            head_sha=head_sha,
        )


def discover(config: SearchConfig, results_dir: Path) -> DiscoveryRun:
    run = DiscoveryEngine(config, GitHubClient(config.github)).run()
    markdown_path, json_path = write_results(run, results_dir)
    print(f"Wrote {markdown_path} and {json_path}", flush=True)
    return run

