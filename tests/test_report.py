from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_cost_atlas.models import DiscoveryRun, QueryStat, RepositoryRecord
from agent_cost_atlas.report import write_results


class ReportTests(unittest.TestCase):
    def test_report_and_snapshot_are_written(self) -> None:
        repository = RepositoryRecord(
            repository_id=1,
            full_name="example/project",
            url="https://github.com/example/project",
            description="Agent cost forecast",
            stars=3,
            forks=1,
            open_issues=0,
            language="Python",
            license="MIT",
            archived=False,
            fork=False,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-08-01T00:00:00Z",
            pushed_at="2026-08-01T00:00:00Z",
            default_branch="main",
            topics=("agents",),
            matched_searches=("agent cost [best_match]",),
            score=20,
            evidence=("Agent cost forecasting before deployment.",),
            readme_sha="abc",
            head_sha="def",
        )
        run = DiscoveryRun(
            schema_version="1.0",
            run_id="20260815T080000Z",
            generated_at_utc="2026-08-15T08:00:00Z",
            source_commit=None,
            config_sha256="123",
            github_api_version="2026-03-10",
            queries_executed=1,
            search_requests=1,
            unique_repositories_discovered=1,
            readmes_analyzed=1,
            final_count=1,
            query_stats=(QueryStat("agent cost", "best_match", 1, 1, 1, False, False),),
            repositories=(repository,),
        )

        with tempfile.TemporaryDirectory() as directory:
            markdown, snapshot = write_results(run, Path(directory))
            self.assertTrue(markdown.is_file())
            self.assertTrue(snapshot.is_file())
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(payload["repositories"][0]["head_sha"], "def")
            self.assertIn("example/project", markdown.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
