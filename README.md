# Agent Cost Atlas

Reproducible discovery of open-source software concerned with the economics of AI agents and LLM workflows.

## Research objective

The repository is a discovery instrument, not a pre-populated competitor list. It searches public GitHub repositories for software related to agent/LLM operating cost, cost estimation, future-spend forecasting, budget enforcement, pre-execution estimation, cost governance, and FinOps.

Known competitor repository names are deliberately not seeded into the discovery protocol. Method-specific mathematical keywords are also not used as discovery terms. If a repository describes such a method in its own public text, that text may appear naturally in the recorded evidence.

## Repository layout

```text
agent-cost-atlas/
├── README.md
├── pyproject.toml
├── .python-version
├── config/
│   └── search.toml
├── src/
│   └── agent\_cost\_atlas/
│       ├── \_\_init\_\_.py
│       ├── \_\_main\_\_.py
│       ├── app.py
│       ├── config.py
│       ├── github.py
│       ├── models.py
│       ├── report.py
│       ├── scoring.py
│       └── text.py
├── tests/
│   ├── test\_config.py
│   ├── test\_engine.py
│   ├── test\_report.py
│   └── test\_scoring.py
├── results/
│   └── README.md
└── .github/
    └── workflows/
        └── discovery.yml
```

The root README contains documentation only. Source code lives under `src/`, research settings under `config/`, tests under `tests/`, and generated evidence under `results/`.

## Discovery protocol

`config/search.toml` is the inspectable research protocol. It defines:

* neutral discovery queries;
* GitHub API and pagination settings;
* candidate-ranking weights;
* functional/economic relevance terms;
* two discovery views: GitHub best-match relevance and recently updated repositories.

For every query/view pair, the generated report records GitHub's reported total, the number actually retrieved, page count, and whether collection was capped by the configured page limit. This makes incomplete query coverage visible rather than silently treating a truncated search as exhaustive.

The strongest candidates then undergo README inspection. Retained records contain public GitHub metadata, matched searches, short README evidence, the README content hash reported by GitHub, and the current default-branch head SHA.

## Outputs

A successful run creates:

* `results/latest.md` — human-readable ranked discovery table and query-coverage audit;
* `results/latest.json` — machine-readable snapshot with provenance and repository state.

The initial version intentionally maintains only a current snapshot. The schema already records stable repository IDs, run timestamps, README hashes and branch-head SHAs so a later longitudinal phase can add timestamped snapshots, commit deltas and concise change summaries without redesigning the discovery layer.

## Run in GitHub

Open **Actions → Discover open-source agent-cost projects → Run workflow**.

The workflow validates formatting, lint rules, compilation and unit tests before performing network discovery. If discovery succeeds, GitHub Actions commits the generated snapshot back to the branch.

## Run from a checkout

```bash
PYTHONPATH=src python -m agent\_cost\_atlas discover \\
  --config config/search.toml \\
  --results-dir results
```

The configuration resolver does not assume that the current working directory contains the configuration file. An explicit `--config` path is always accepted, and the default resolver can locate the repository root from the installed source tree or `GITHUB\_WORKSPACE`.

## Research status

**Phase 1: independent open-source discovery.**

Manual interpretation, competitor classification and any broader research report are performed only after inspection of the generated evidence.

