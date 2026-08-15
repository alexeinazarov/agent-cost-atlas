from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SearchConfig
from .github import GitHubClient
from .models import DiscoveryRun, RepositoryRecord
from .report import write_results
from .scoring import is_relevant, metadata_score, readme_score, repository_metadata_text
from .text import evidence_sentences


class DiscoveryEngine:
    def __init__(self, config: SearchConfig, client: GitHubClient) -> None:
        self.config = config
        self.client = client

    def run(self) -> DiscoveryRun:
        repositories: dict[str, dict[str, Any]] = {}
        matched_searches: dict[str, set[str]] = {}
        query_stats = []
        total_searches = len(self.config.queries) * len(self.config.search_modes)
        search_number = 0

        for query in self.config.queries:
            for mode in self.config.search_modes:
                search_number += 1
                print(f"[{search_number}/{total_searches}] search: {query!r} ({mode})", flush=True)
                items, stat = self.client.search_repositories(query, mode)
                query_stats.append(stat)
                search_key = f"{query} [{mode}]"
                for repository in items:
                    full_name = repository.get("full_name")
                    if not isinstance(full_name, str) or not full_name:
                        continue
                    repositories.setdefault(full_name, repository)
                    matched_searches.setdefault(full_name, set()).add(search_key)

        candidates = [
            (
                metadata_score(repository, matched_searches[full_name], self.config),
                full_name,
                repository,
            )
            for full_name, repository in repositories.items()
        ]
        candidates.sort(
            key=lambda item: (
                -item[0],
                -int(item[2].get("stargazers_count") or 0),
                item[1].casefold(),
            )
        )
        candidates = candidates[: self.config.github.readme_limit]

        print(f"Unique repositories discovered: {len(repositories)}", flush=True)
        print(f"Inspecting {len(candidates)} candidate READMEs", flush=True)

        retained: list[RepositoryRecord] = []
        for index, (base_score, full_name, repository) in enumerate(candidates, start=1):
            print(f"[{index}/{len(candidates)}] README: {full_name}", flush=True)
            readme = self.client.fetch_readme(full_name)
            metadata_text = repository_metadata_text(repository)
            score = base_score + readme_score(readme.text, self.config)

            if score < self.config.ranking.min_final_score:
                continue
            if not is_relevant(metadata_text, readme.text, self.config):
                continue

            default_branch = str(repository.get("default_branch") or "")
            head_sha = (
                self.client.fetch_head_sha(full_name, default_branch) if default_branch else None
            )
            license_data = repository.get("license") or {}
            license_id = license_data.get("spdx_id") if isinstance(license_data, dict) else None
            topics = repository.get("topics") or []
            if not isinstance(topics, list):
                topics = []

            retained.append(
                RepositoryRecord(
                    repository_id=int(repository.get("id") or 0),
                    full_name=full_name,
                    url=str(repository.get("html_url") or ""),
                    description=str(repository.get("description") or ""),
                    stars=int(repository.get("stargazers_count") or 0),
                    forks=int(repository.get("forks_count") or 0),
                    open_issues=int(repository.get("open_issues_count") or 0),
                    language=(
                        str(repository["language"])
                        if repository.get("language") is not None
                        else None
                    ),
                    license=(str(license_id) if license_id else None),
                    archived=bool(repository.get("archived")),
                    fork=bool(repository.get("fork")),
                    created_at=(
                        str(repository["created_at"]) if repository.get("created_at") else None
                    ),
                    updated_at=(
                        str(repository["updated_at"]) if repository.get("updated_at") else None
                    ),
                    pushed_at=(
                        str(repository["pushed_at"]) if repository.get("pushed_at") else None
                    ),
                    default_branch=default_branch,
                    topics=tuple(str(topic) for topic in topics),
                    matched_searches=tuple(sorted(matched_searches[full_name])),
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
            )

        retained.sort(key=lambda repo: (-repo.score, -repo.stars, repo.full_name.casefold()))
        now = datetime.now(UTC).replace(microsecond=0)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        source_commit = os.environ.get("GITHUB_SHA") or None
        run_id = f"{timestamp}-{source_commit[:8]}" if source_commit else timestamp

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
        )


def discover(config: SearchConfig, results_dir: Path) -> DiscoveryRun:
    run = DiscoveryEngine(config, GitHubClient(config.github)).run()
    markdown_path, json_path = write_results(run, results_dir)
    print(f"Wrote {markdown_path} and {json_path}", flush=True)
    return run
