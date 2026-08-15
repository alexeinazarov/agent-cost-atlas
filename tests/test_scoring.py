from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_cost_atlas.config import load_config
from agent_cost_atlas.scoring import is_relevant, metadata_score, readme_score
from test_config import MINIMAL_CONFIG


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        path = Path(self._temp.name) / "search.toml"
        path.write_text(MINIMAL_CONFIG, encoding="utf-8")
        self.config = load_config(path)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_forward_language_increases_readme_score(self) -> None:
        plain = "An agent cost dashboard records cost after each run."
        forward = "An agent cost dashboard can forecast cost before deployment."
        self.assertGreater(readme_score(forward, self.config), readme_score(plain, self.config))

    def test_repository_requires_both_relevance_axes(self) -> None:
        self.assertTrue(is_relevant("agent runtime", "cost control", self.config))
        self.assertFalse(is_relevant("agent runtime", "latency telemetry", self.config))

    def test_query_recurrence_is_rewarded(self) -> None:
        repository = {
            "name": "tool",
            "description": "agent cost forecast",
            "topics": [],
            "stargazers_count": 0,
            "archived": False,
            "fork": False,
        }
        one = metadata_score(repository, {"q1"}, self.config)
        two = metadata_score(repository, {"q1", "q2"}, self.config)
        self.assertGreater(two, one)


if __name__ == "__main__":
    unittest.main()
