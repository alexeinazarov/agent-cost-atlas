# Agent Cost Atlas

Reproducible discovery of open-source software concerned with the economics of AI agents and LLM workflows.

## Scope

This repository searches public GitHub repositories for software related to:

- AI-agent and LLM operating costs
- cost estimation
- future-spend forecasting
- budget enforcement
- pre-deployment or pre-execution cost estimation
- cost governance and FinOps
- cost-aware agent execution

The discovery stage does not seed known competitor repository names.

The search vocabulary is stored in [`queries.txt`](queries.txt), so the discovery procedure is inspectable and reproducible.

## Outputs

Running the GitHub Action produces:

- [`RESULTS.md`](RESULTS.md) — human-readable ranked repository list
- [`results.json`](results.json) — machine-readable evidence and search metadata

Each retained repository includes its GitHub metadata, matched discovery queries, and README evidence where available.

## Method

1. Execute a set of neutral GitHub repository searches.
2. Deduplicate repositories returned by different queries.
3. Rank candidates using domain/economic relevance and recurrence across independent queries.
4. Inspect the READMEs of the strongest candidates.
5. Retain repositories containing both:
   - AI-agent / LLM relevance, and
   - economic / cost relevance.
6. Produce a reproducible report.

Popularity is deliberately a weak ranking signal. A small but highly relevant repository should be able to outrank a popular generic LLM project.

## Running

Open:

**Actions → Discover open-source agent cost projects → Run workflow**

The generated result files are committed back into this repository.

## Research status

Discovery infrastructure only.

Interpretation, competitor classification, and the final open-source market report are performed separately after manual review of the retrieved repositories.# agent-cost-atlas
Reproducible discovery of open-source tooling for AI agent cost estimation, forecasting and budget control.
