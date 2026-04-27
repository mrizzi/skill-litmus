# Standalone Skill Eval Runner

**Date**: 2026-04-24
**Scope**: Extract eval execution into a standalone repo usable by any Claude Code plugin author

## Problem

The `run-evals` skill and its CI workflows are functional but not portable.
Three things bind them to the sdlc-plugins repo:

1. The `sdlc-workflow:` namespace is hardcoded in the subagent prompt
   that invokes the skill under test.
2. The CI workflows (`eval-pr.yml`, `eval-baseline.yml`) embed this
   repo's directory layout, GCP auth, and Vertex AI configuration.
3. No tooling exists to help a new skill adopter create their eval
   suite from scratch.

A plugin author who wants to eval-test their skills today would need to
reverse-engineer the framework, rewrite the CI workflows, and manually
author `evals.json` and fixture files.

## Solution

A new standalone repo (`skill-litmus`) containing:

- A **deterministic shell/Python engine** that orchestrates eval
  execution, grading, aggregation, and reporting.
- A **Claude Code plugin** (`skill-litmus`) with two skills:
  `run-evals` (thin interactive wrapper) and `develop-eval`
  (full-generation eval authoring).
- A **GitHub Action** that runs evals in CI with event-driven behavior.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Repo strategy | Standalone repo | Fully independent; installable without pulling sdlc-workflow |
| Orchestration | Deterministic shell script (Approach B) | LLM used only for eval execution and grading — no tokens spent on mechanical orchestration |
| CI packaging | Single GitHub Action, event-driven | Adopter writes one workflow file; action branches on `pull_request` vs `push` |
| Auth strategy | `ANTHROPIC_API_KEY` in environment | Simple, standard; no provider-specific logic in the action |
| Eval authoring | Full generation via `develop-eval` skill | Reads SKILL.md, generates fixtures, assertions, and test cases — not just scaffolding |
| CI template | Static file copied by `develop-eval` | Reviewable, diffable; no generated drift |
| Test categories | Standard + adversarial always; others via SKILL.md analysis | Not every skill has ambiguous-input or multi-source-input failure modes |
| `develop-eval` idempotency | Additive only on re-runs | Existing cases, fixtures, and assertions are never overwritten; only gaps are filled |
| evals.json divergences from agentskills.io | Kept, documented | See Section 9 |

## 1. Repo Structure

```
skill-litmus/
├── action.yml                          # GitHub Action entry point
├── plugins/
│   └── skill-litmus/
│       ├── .claude-plugin/
│       │   └── plugin.json
│       ├── scripts/                    # Inside plugin — distributed with install
│       │   ├── run-evals.sh
│       │   ├── aggregate_benchmark.py
│       │   ├── render_summary.py
│       │   └── post-results.sh
│       ├── templates/
│       │   └── eval-workflow.yml
│       └── skills/
│           ├── run-evals/
│           │   └── SKILL.md            # Thin wrapper calling ../../scripts/run-evals.sh
│           └── develop-eval/
│               └── SKILL.md
├── evals.schema.json
├── README.md
└── LICENSE
```

Scripts live inside the plugin directory so they are distributed when the
plugin is installed. The action references them via
`plugins/skill-litmus/scripts/` from repo root. The skills reference them
via `../../scripts/` relative to their own directory.

## 2. Deterministic Engine (`run-evals.sh`)

The core orchestrator. Replaces the LLM-driven orchestration in the
current `run-evals` SKILL.md.

```
run-evals.sh --evals <path> --skill <name> --workspace <dir> [--plugin <namespace>]
```

### Flow

1. **Parse `evals.json`** — `jq` extracts skill name, eval cases, file
   paths, assertions.
2. **Create workspace layout** — `mkdir -p` for each `eval-<id>/outputs/`.
3. **Execute each eval** — for each case, invoke `claude -p` with a
   prompt that reads fixture files, invokes the skill under test via the
   Skill tool (`/<plugin>:<skill>`), and writes outputs to
   `eval-<id>/outputs/`. Uses `--permission-mode dontAsk` and
   `--allowedTools Read Write Bash Skill Agent Glob` so the eval agent
   can invoke the Skill tool without interactive prompts. The `--plugin`
   flag defaults to auto-detection: walk up from the `evals.json`
   directory looking for `.claude-plugin/plugin.json`, read the `name`
   field. If not found or multiple candidates exist, the flag is
   required.
4. **Capture timing** — the shell wraps each `claude -p` with `time`,
   writes `eval-<id>/timing.json` with wall-clock duration.
5. **Grade each eval** — invoke `claude -p` with a grading prompt per
   eval case (assertions + outputs directory), writes
   `eval-<id>/grading.json`.
6. **Aggregate** — call `aggregate_benchmark.py --results <workspace>`.
7. **Render summary** — call
   `render_summary.py --results <workspace> --baseline <path>`.

### Parallelism

Steps 3-4 run eval cases in parallel (`&` + `wait`). Step 5 can overlap
— grade each eval as its execution completes.

### Token counting

Dropped from timing data. The current skill captures `total_tokens` from
task completion notifications, which is fragile and LLM-dependent. The
shell orchestrator captures wall-clock duration instead. Token counting
can be added back if the Claude Code CLI exposes usage stats in a
parseable format.

## 3. GitHub Action (`action.yml`)

Single action with event-driven behavior.

### Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `evals-dir` | `evals/` | Path to evals directory |
| `skills-dir` | auto-detected | Path to skills directory |
| `baseline-branch` | repo default branch | Branch for baseline comparison |

### Event-driven behavior

**On `pull_request`:**

1. Checkout the PR branch.
2. Discover changed skills by diffing `skills-dir/**/*.md` and
   `evals-dir/**/evals.json` against base SHA.
3. For each changed skill with an `evals.json`, call `run-evals.sh`.
4. Call `post-results.sh pr` — reads each workspace's `summary.md`,
   posts or updates a single PR comment with all results.

**On `push` (to default branch):**

1. Checkout the push commit.
2. Discover all eval suites (every `evals-dir/*/evals.json`).
3. For each, call `run-evals.sh`.
4. Call `post-results.sh baseline` — copies results to
   `evals/<skill>/baselines/<commit-hash>/`, updates `latest` symlink,
   commits and pushes.

### What the action does NOT do

- Gate merges — reports results only.
- Install model routers — assumes `ANTHROPIC_API_KEY` in environment.
- Run skills without `evals.json` — no eval suite, no run.

### Adopter setup

```yaml
on:
  pull_request:
    paths: ['skills/**/*.md', 'evals/**/evals.json']
  push:
    branches: [main]
    paths: ['skills/**/*.md', 'evals/**/evals.json']

jobs:
  eval:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: org/skill-litmus@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## 4. The `run-evals` Skill (Thin Wrapper)

Exists for local interactive UX — type `/skill-litmus:run-evals` instead
of remembering shell flags.

The SKILL.md:

1. Asks for skill name, evals path, and workspace.
2. Resolves the path to `run-evals.sh` relative to its own directory
   (`../../scripts/run-evals.sh`).
3. Invokes it via Bash with the provided arguments.
4. Reads the resulting `summary.md` and displays it to the user.

No subagent spawning, no timing capture, no aggregation logic in the
skill. The scripts handle aggregation, benchmark computation, and
baseline comparison internally. The skill calls the orchestrator and
displays the final output.

## 5. The `develop-eval` Skill (Full Generation)

LLM-powered eval authoring. Generates a ready-to-run eval suite from a
skill's SKILL.md.

### Discovery

1. Scans the repo for `**/SKILL.md` files.
2. If multiple found, lists them and asks which skill to target.
3. If one found, confirms with the user.

### Analysis

4. Reads the target SKILL.md — identifies inputs, outputs, failure
   modes, external dependencies, and prompt injection surfaces.
5. Determines which test case categories apply:
   - **Standard** (always) — golden path with well-formed input.
   - **Adversarial** (always) — prompt injection in the input data.
   - Additional categories based on SKILL.md analysis: incomplete or
     ambiguous input, complex multi-source input, edge cases specific
     to the skill's domain.

### Generation

6. For each test case, generates:
   - A realistic `prompt` that exercises the skill.
   - Fixture files in `evals/<skill>/files/`.
   - An `expected_output` description.
   - Concrete assertions grounded in the skill's SKILL.md promises.
7. Assembles `evals.json` with the full schema.
8. Writes `evals/<skill>/README.md` documenting what each case tests.

### CI setup

9. If `.github/workflows/eval.yml` does not exist, copies the template
   from `../../templates/eval-workflow.yml` and tells the maintainer to
   add their `ANTHROPIC_API_KEY` secret.

### Validation

10. Runs `evals.schema.json` against the generated `evals.json`.
11. Offers to run the eval suite immediately via `run-evals.sh`.

### Idempotency

- If `evals.json` exists, reads it first. Analyzes which test case
  categories are covered. Only generates cases for missing categories.
  Preserves existing cases, IDs, and assertions.
- If fixture files exist, does not regenerate them. New cases get new
  fixture files with non-colliding names.
- If `eval-workflow.yml` exists, skips the copy.
- Explicit user request required to regenerate an existing case.

## 6. The `develop-eval` Iteration Workflow

Beyond first-time generation, `develop-eval` supports the improvement
cycle after eval runs.

### Post-run analysis

1. Reads `grading.json` files from the workspace — identifies failed
   assertions.
2. Reads `feedback.json` — picks up human review notes.
3. Reads the skill's SKILL.md — understands current instructions.

### Proposes SKILL.md improvements

4. Following agentskills.io principles: generalize from feedback, keep
   instructions lean, explain the why.
5. Presents proposed changes to the maintainer for review before
   applying.

### Updates eval suite if needed

6. If failures reveal a gap in test coverage, proposes a new test case.
7. If an assertion always passes in both current and baseline, flags it
   for removal — it is not measuring skill value.
8. Follows the idempotency rules — additive changes only.

### Does NOT

- Auto-apply SKILL.md changes — the maintainer reviews and approves.
- Remove existing test cases without asking — only flags them.
- Run evals — tells the maintainer to run them after applying changes.

## 7. The `evals.json` Contract

The interface between `develop-eval` (producer) and `run-evals.sh`
(consumer). Stable across repo boundaries.

### Schema

```json
{
  "skill_name": "<slash-command name without plugin namespace>",
  "plugin": "<optional — plugin namespace for skill invocation>",
  "evals": [
    {
      "id": "<number — unique, stable across runs>",
      "prompt": "<the user prompt sent to the skill>",
      "expected_output": "<human-readable description of good output>",
      "files": ["<paths to fixture files, relative to evals.json directory>"],
      "assertions": ["<graded by LLM judge>"]
    }
  ]
}
```

### `plugin` field

Resolves the hardcoded namespace problem. `run-evals.sh` uses it to
construct the skill invocation (`/<plugin>:<skill_name>`). If omitted,
auto-detected by walking up from the `evals.json` directory to find
`.claude-plugin/plugin.json` and reading its `name` field.

### Formal schema

`evals.schema.json` at repo root provides JSON Schema validation.

## 8. Migration Path for sdlc-plugins

1. **Create the `skill-litmus` repo** with the structure from
   Section 1.
2. **Move the engine** — extract `aggregate_benchmark.py` and
   `render_summary.py` from
   `plugins/sdlc-workflow/skills/run-evals/scripts/`. Write
   `run-evals.sh` and `post-results.sh`.
3. **Add `plugin` field** to each existing `evals.json`:
   `"plugin": "sdlc-workflow"`.
4. **Install the new plugin** in sdlc-plugins.
5. **Replace CI workflows** — delete `eval-pr.yml` and
   `eval-baseline.yml`, add a single workflow using the new action.
6. **Remove the old `run-evals` skill** from
   `plugins/sdlc-workflow/skills/run-evals/`.
7. **Existing baselines stay untouched** — directory structure and file
   formats are unchanged.

Backward compatible: `evals.json` schema is a strict superset (only
`plugin` added). Output layout (`eval-<id>/`, `grading.json`,
`timing.json`, `benchmark.json`, `summary.md`) is identical.

## 9. Divergences from agentskills.io Conventions

This framework follows the [agentskills.io eval
guide](https://agentskills.io/skill-creation/evaluating-skills) for
`evals.json` schema, `grading.json` format, `timing.json` format, and
the overall eval-grade-review-iterate workflow. Two intentional
divergences exist.

### benchmark.json structure

**agentskills.io** defines `with_skill`, `without_skill`, and `delta`
keys because it runs both configurations (with and without the skill) in
each iteration to measure skill value.

**This framework** runs only the current skill version and compares
against stored baselines from previous commits. The `run_summary`
contains only the current run's stats. Baseline comparison is handled by
`render_summary.py`, which reads a separate baseline directory.

**Why:** The agentskills.io model optimizes for interactive skill
development — "is this skill better than no skill?" The baseline model
optimizes for CI regression detection — "did this change make the skill
worse?" Running both configurations doubles cost per eval run, which is
acceptable during initial development but wasteful in CI where every
push to main triggers a full eval suite. Stored baselines give the same
regression signal at half the cost.

### Eval directory naming

**agentskills.io** uses descriptive names (`eval-top-months-chart/`).

**This framework** uses numeric IDs (`eval-1/`, `eval-2/`) matching the
`id` field in `evals.json`.

**Why:** Numeric IDs are stable identifiers that survive prompt rewrites
and test case renames. A descriptive name derived from the prompt becomes
stale when the prompt changes, requiring directory renames that break
baseline symlinks and CI scripts. Numeric IDs decouple the directory
structure from test case content. The human-readable description lives
in `evals.json` and `README.md` where it belongs.

### Token counting in timing.json

**agentskills.io** includes `total_tokens` in `timing.json`, captured
from task completion notifications.

**This framework** captures wall-clock duration only. Token count is
omitted.

**Why:** The deterministic shell orchestrator invokes `claude -p` as a
subprocess. Token usage is reported inside the Claude Code session, not
exposed to the calling shell. Capturing it would require parsing
unstructured stderr output, which is fragile and provider-dependent.
Wall-clock duration is the reliable, provider-agnostic metric. Token
counting can be added if the Claude Code CLI exposes usage stats in a
parseable format.
