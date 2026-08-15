from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_cost_atlas.app import DiscoveryEngine
from agent_cost_atlas.config import load_config
from agent_cost_atlas.github import ReadmeDocument
from agent_cost_atlas.models import QueryStat
from test_config import MINIMAL_CONFIG


class FakeClient:
    def search_repositories(self, query: str, mode: str):
        repository = {
            "id": 42,
            "full_name": "example/agent-cost-tool",
            "name": "agent-cost-tool",
            "html_url": "https://github.com/example/agent-cost-tool",
            "description": "Agent cost forecast and budget gate",
            "stargazers_count": 7,
            "forks_count": 1,
            "open_issues_count": 2,
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
        return [repository], QueryStat(query, mode, 1, 1, 1, False, False)

    def fetch_readme(self, full_name: str) -> ReadmeDocument:
        return ReadmeDocument(
            text="This agent forecasts cost before deployment and enforces a budget gate.",
            sha="readme-sha",
        )

    def fetch_head_sha(self, full_name: str, default_branch: str) -> str:
        return "head-sha"


class EngineTests(unittest.TestCase):
    def test_engine_retains_provenance_and_future_diff_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "search.toml"
            path.write_text(MINIMAL_CONFIG, encoding="utf-8")
            config = load_config(path)
            run = DiscoveryEngine(config, FakeClient()).run()  # type: ignore[arg-type]

        self.assertEqual(run.final_count, 1)
        repository = run.repositories[0]
        self.assertEqual(repository.repository_id, 42)
        self.assertEqual(repository.readme_sha, "readme-sha")
        self.assertEqual(repository.head_sha, "head-sha")
        self.assertEqual(repository.matched_searches, ("agent cost [best_match]",))


if __name__ == "__main__":
    unittest.main()
