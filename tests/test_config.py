from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agent_cost_atlas.config import ConfigurationError, load_config, resolve_config_path

MINIMAL_CONFIG = """
[research]
schema_version = "1.0"
project = "Agent Cost Atlas"

[github]
api_base_url = "https://api.github.com"
api_version = "2022-11-28"
user_agent = "agent-cost-atlas-tests/0.2"
per_page = 100
max_pages_per_query = 1
readme_limit = 10
search_delay_seconds = 0.0
core_delay_seconds = 0.0
timeout_seconds = 30.0
max_retries = 1

[ranking]
min_final_score = 10
query_recurrence_cap = 8
query_recurrence_weight = 3
domain_term_weight = 2
economic_term_weight = 3
forward_term_weight = 4
readme_base_score = 5
popularity_score_cap = 4
archived_penalty = 4
fork_penalty = 2

[discovery]
search_modes = ["best_match"]

[terms]
domain = ["agent", "agents", "llm"]
economic = ["cost", "costs", "budget", "spend"]
forward = ["forecast", "forecasting", "before deployment", "gate"]

[queries]
items = ["agent cost"]
"""


def _write_config(directory: Path, body: str) -> Path:
    path = directory / "search.toml"
    path.write_text(body, encoding="utf-8")
    return path


class ConfigTests(unittest.TestCase):
    def test_valid_configuration_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = load_config(_write_config(Path(directory), MINIMAL_CONFIG))

        self.assertEqual(config.schema_version, "1.0")
        self.assertEqual(config.queries, ("agent cost",))
        self.assertEqual(config.search_modes, ("best_match",))
        self.assertEqual(len(config.source_sha256), 64)

    def test_duplicate_queries_are_rejected(self) -> None:
        body = MINIMAL_CONFIG.replace(
            'items = ["agent cost"]',
            'items = ["agent cost", "agent cost"]',
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigurationError):
                load_config(_write_config(Path(directory), body))

    def test_unsupported_search_mode_is_rejected(self) -> None:
        body = MINIMAL_CONFIG.replace(
            'search_modes = ["best_match"]',
            'search_modes = ["best_match", "trending"]',
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigurationError):
                load_config(_write_config(Path(directory), body))

    def test_missing_configuration_reports_the_resolved_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.toml"
            with self.assertRaises(ConfigurationError):
                resolve_config_path(missing)

    def test_configuration_resolves_outside_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(project)
            (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
            (root / "config").mkdir()
            _write_config(root / "config", MINIMAL_CONFIG)

            previous_cwd = Path.cwd()
            previous_workspace = os.environ.get("GITHUB_WORKSPACE")
            os.environ["GITHUB_WORKSPACE"] = str(root)
            os.chdir(elsewhere)
            try:
                resolved = resolve_config_path(None)
            finally:
                os.chdir(previous_cwd)
                if previous_workspace is None:
                    os.environ.pop("GITHUB_WORKSPACE", None)
                else:
                    os.environ["GITHUB_WORKSPACE"] = previous_workspace

        self.assertEqual(resolved, (root / "config" / "search.toml").resolve())


if __name__ == "__main__":
    unittest.main()
