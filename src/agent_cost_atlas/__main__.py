from __future__ import annotations

import argparse
from pathlib import Path

from .app import discover
from .config import ConfigurationError, load_config
from .github import GitHubApiError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-cost-atlas",
        description="Reproducible discovery of open-source AI-agent cost tooling.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover_parser = subparsers.add_parser("discover", help="Run the GitHub discovery sweep")
    discover_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to search TOML. Defaults to config/search.toml at the repository root.",
    )
    discover_parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory for generated latest.md and latest.json.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        if args.command == "discover":
            discover(config, args.results_dir.resolve())
            return 0
    except (ConfigurationError, GitHubApiError) as exc:
        print(f"error: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
