from __future__ import annotations

import tempfile
import unittest
from email.message import Message
from pathlib import Path

from agent_cost_atlas.app import DiscoveryEngine
from agent_cost_atlas.config import GitHubConfig, load_config
from agent_cost_atlas.github import GitHubApiError, GitHubClient, ReadmeDocument
from agent_cost_atlas.models import QueryStat
from test_config import MINIMAL_CONFIG

CONFIG = GitHubConfig(
    api_base_url="https://api.github.com",
    api_version="2026-03-10",
    user_agent="agent-cost-atlas-tests/0.2",
    per_page=100,
    max_pages_per_query=1,
    readme_limit=10,
    search_delay_seconds=0.0,
    core_delay_seconds=0.0,
    timeout_seconds=30.0,
    max_retries=1,
)


class FailingClient(GitHubClient):
    """Client whose transport always fails with one configured API error."""

    def __init__(self, error: GitHubApiError) -> None:
        super().__init__(CONFIG, token="")
        self._error = error

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        raise self._error


def _repository(identifier: int, full_name: str) -> dict:
    return {
        "id": identifier,
        "full_name": full_name,
        "name": full_name.split("/")[-1],
        "html_url": f"https://github.com/{full_name}",
        "description": "Agent cost forecast and budget gate",
        "stargazers_count": 5,
        "forks_count": 0,
        "open_issues_count": 0,
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "archived": False,
        "fork": False,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "pushed_at": "2026-08-01T00:00:00Z",
        "default_branch": "main",
        "topics": ["agent", "cost"],
    }


class UnreliableClient:
    """Returns two candidates; one candidate fails during head inspection."""

    def search_repositories(self, query: str, mode: str):
        items = [_repository(1, "example/healthy"), _repository(2, "example/unreachable")]
        return items, QueryStat(query, mode, 2, 2, 1, False, False)

    def fetch_readme(self, full_name: str) -> ReadmeDocument:
        return ReadmeDocument(
            text="This agent forecasts cost before deployment and enforces a budget gate.",
            sha=f"readme-{full_name}",
        )

    def fetch_head_sha(self, full_name: str, default_branch: str) -> str | None:
        if full_name == "example/unreachable":
            raise GitHubApiError("temporary upstream failure", status=503)
        return "head-sha"


class ClientToleranceTests(unittest.TestCase):
    def test_empty_repository_yields_no_head_sha(self) -> None:
        client = FailingClient(GitHubApiError("Git Repository is empty.", status=409))
        self.assertIsNone(client.fetch_head_sha("example/empty", "main"))

    def test_missing_readme_yields_empty_document(self) -> None:
        client = FailingClient(GitHubApiError("Not Found", status=404))
        self.assertEqual(client.fetch_readme("example/no-readme"), ReadmeDocument("", None))

    def test_plain_forbidden_readme_is_not_silently_tolerated(self) -> None:
        client = FailingClient(GitHubApiError("Forbidden", status=403))
        with self.assertRaises(GitHubApiError):
            client.fetch_readme("example/forbidden")

    def test_rate_limit_exhaustion_is_never_tolerated(self) -> None:
        client = FailingClient(
            GitHubApiError("rate limit exceeded", status=403, rate_limited=True)
        )
        with self.assertRaises(GitHubApiError):
            client.fetch_readme("example/throttled")
        with self.assertRaises(GitHubApiError):
            client.fetch_head_sha("example/throttled", "main")

    def test_429_is_always_classified_as_rate_limited(self) -> None:
        self.assertTrue(GitHubClient._is_rate_limited(429, Message(), ""))

    def test_secondary_limit_message_is_recognized_without_headers(self) -> None:
        body = '{"message":"You have exceeded a secondary rate limit."}'
        self.assertTrue(GitHubClient._is_rate_limited(403, Message(), body))

    def test_plain_403_is_not_classified_as_rate_limited(self) -> None:
        self.assertFalse(GitHubClient._is_rate_limited(403, Message(), '{"message":"Forbidden"}'))


class EngineResilienceTests(unittest.TestCase):
    def test_one_failing_repository_does_not_end_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "search.toml"
            path.write_text(MINIMAL_CONFIG, encoding="utf-8")
            config = load_config(path)
            run = DiscoveryEngine(config, UnreliableClient()).run()  # type: ignore[arg-type]

        self.assertEqual(run.unique_repositories_discovered, 2)
        self.assertEqual(run.final_count, 1)
        self.assertEqual(run.repositories[0].full_name, "example/healthy")
        self.assertEqual(len(run.inspection_failures), 1)
        self.assertIn("example/unreachable", run.inspection_failures[0])


if __name__ == "__main__":
    unittest.main()
