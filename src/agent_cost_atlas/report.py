from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .models import DiscoveryRun

# Evidence is third-party README text that is committed back to this
# repository, so structural Markdown characters are neutralised rather than
# rendered.
_MARKDOWN_ESCAPES = str.maketrans(
    {
        "|": "\\|",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "[": "\\[",
        "]": "\\]",
        "<": "&lt;",
        ">": "&gt;",
    }
)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def _escape_markdown(text: str) -> str:
    return " ".join(text.split()).translate(_MARKDOWN_ESCAPES)


def render_markdown(run: DiscoveryRun) -> str:
    failed_queries = [stat for stat in run.query_stats if stat.error]
    lines = [
        "# Open-source agent-cost discovery results",
        "",
        f"Generated: `{run.generated_at_utc}`  ",
        f"Run ID: `{run.run_id}`  ",
        f"Configuration SHA-256: `{run.config_sha256}`",
        "",
        f"- Query/mode searches executed: **{run.queries_executed}**",
        f"- Search result pages retrieved: **{run.search_requests}**",
        f"- Unique repositories discovered: **{run.unique_repositories_discovered}**",
        f"- Candidates selected for README inspection: **{run.readmes_analyzed}**",
        f"- Repositories passing the relevance filter: **{run.final_count}**",
        f"- Searches that failed: **{len(failed_queries)}**",
        f"- Repositories skipped after API errors: **{len(run.inspection_failures)}**",
        "",
        "## Repositories",
        "",
        "| # | Repository | Stars | License | Score | Evidence |",
        "|---:|---|---:|---|---:|---|",
    ]

    for index, repo in enumerate(run.repositories, start=1):
        evidence = repo.evidence[0] if repo.evidence else repo.description
        if len(evidence) > 300:
            evidence = f"{evidence[:297].rstrip()}..."
        lines.append(
            "| "
            f"{index} | [{repo.full_name}]({repo.url}) | {repo.stars} | "
            f"{repo.license or '-'} | {repo.score} | {_escape_markdown(evidence) or '-'} |"
        )

    lines.extend(
        [
            "",
            "## Query coverage",
            "",
            "| Query | Mode | GitHub total | Retrieved | Pages | Capped | Incomplete | Error |",
            "|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    lines.extend(
        f"| `{_escape_markdown(stat.query)}` | `{stat.mode}` | {stat.total_count} | "
        f"{stat.retrieved} | {stat.pages_retrieved} | "
        f"{'yes' if stat.capped_by_page_limit else 'no'} | "
        f"{'yes' if stat.incomplete_results else 'no'} | "
        f"{'yes' if stat.error else 'no'} |"
        for stat in run.query_stats
    )

    if failed_queries or run.inspection_failures:
        lines.extend(["", "## Collection failures", ""])
        lines.extend(
            f"- search `{_escape_markdown(stat.query)}` [{stat.mode}]: "
            f"{_escape_markdown(stat.error or '')}"
            for stat in failed_queries
        )
        lines.extend(f"- {_escape_markdown(failure)}" for failure in run.inspection_failures)

    lines.extend(
        [
            "",
            "## Reproducibility",
            "",
            "The report is generated from `config/search.toml`. Known competitor "
            "repository names are not seeded into the discovery configuration. "
            "`latest.json` contains machine-readable repository metadata, matched "
            "searches, README evidence, README hashes, default branches and current "
            "branch-head hashes so later runs can be compared without schema changes. "
            "Repositories that could not be inspected are recorded above rather than "
            "silently dropped from the coverage figures.",
            "",
        ]
    )
    return "\n".join(lines)


def write_results(run: DiscoveryRun, results_dir: Path) -> tuple[Path, Path]:
    json_path = results_dir / "latest.json"
    markdown_path = results_dir / "latest.md"
    json_text = json.dumps(run.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    _atomic_write(json_path, json_text)
    _atomic_write(markdown_path, render_markdown(run))
    return markdown_path, json_path
