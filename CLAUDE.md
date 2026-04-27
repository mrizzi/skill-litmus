# skill-litmus

Standalone eval runner for Claude Code skills. Deterministic
shell/Python engine, a Claude Code plugin with two skills, and a GitHub
Action for CI.

## What This Project Is

A portable eval framework that any Claude Code plugin author can adopt.
It replaces the eval infrastructure previously embedded in the
sdlc-plugins repo with a standalone, reusable package.

Three deliverables:

1. **Deterministic engine** (`plugins/skill-litmus/scripts/`) — shell
   and Python scripts that orchestrate eval execution, grading,
   aggregation, and reporting. LLM is used only for eval execution and
   grading; all mechanical work is deterministic.
2. **Claude Code plugin** (`plugins/skill-litmus/`) — two skills:
   `run-evals` (thin wrapper for interactive use) and `develop-eval`
   (full-generation eval authoring).
3. **GitHub Action** (`action.yml`) — event-driven CI that runs evals on
   PRs (changed skills only, posts comment) and on push to main (all
   skills, commits baselines).

## Documentation

- [docs/specs/2026-04-24-standalone-eval-runner-design.md](docs/specs/2026-04-24-standalone-eval-runner-design.md) — Full design spec with all architectural decisions

## Repo Structure

```
skill-litmus/
├── action.yml                          # GitHub Action entry point
├── plugins/
│   └── skill-litmus/
│       ├── .claude-plugin/
│       │   └── plugin.json
│       ├── scripts/                    # Deterministic engine
│       │   ├── run-evals.sh            # Core orchestrator
│       │   ├── aggregate_benchmark.py  # Aggregates grading + timing into benchmark.json
│       │   ├── render_summary.py       # Renders Markdown summary with baseline comparison
│       │   └── post-results.sh         # PR comment / baseline commit logic
│       ├── templates/
│       │   └── eval-workflow.yml       # Opinionated CI template for adopters
│       └── skills/
│           ├── run-evals/
│           │   └── SKILL.md            # Thin wrapper — calls ../../scripts/run-evals.sh
│           └── develop-eval/
│               └── SKILL.md            # Full-generation eval authoring
├── evals.schema.json                   # JSON Schema for evals.json validation
├── README.md
└── LICENSE
```

## Key Architectural Decisions

- **Shell orchestration, not LLM orchestration.** `run-evals.sh` is a
  bash script that invokes `claude -p` for each eval case and grading
  step. No tokens are spent on mechanical orchestration.
- **Event-driven GitHub Action.** Single action that detects
  `pull_request` vs `push` and branches behavior accordingly.
- **agentskills.io-compatible with documented divergences.** The
  `evals.json` schema matches agentskills.io. Three intentional
  divergences (benchmark.json structure, eval directory naming, token
  counting) are documented with rationale in Section 9 of the design
  spec.

## Conventions

### Scripts

- `run-evals.sh` — bash, requires `jq`. The single entry point for both
  local and CI execution.
- `aggregate_benchmark.py` and `render_summary.py` — Python 3, no
  external dependencies (stdlib only).
- `post-results.sh` — bash, uses `gh` CLI for PR comments and `git` for
  baseline commits.

### evals.json Contract

```json
{
  "skill_name": "plan-feature",
  "plugin": "sdlc-workflow",
  "evals": [
    {
      "id": 1,
      "prompt": "...",
      "expected_output": "...",
      "files": ["files/fixture.md"],
      "assertions": ["The output contains X"]
    }
  ]
}
```

The `plugin` field is optional. If omitted, auto-detected by walking up
from the `evals.json` directory to find `.claude-plugin/plugin.json`.

### Output Layout

Every eval run produces this exact structure:

```
<workspace>/
├── benchmark.json
├── feedback.json
├── summary.md
├── eval-1/
│   ├── grading.json
│   ├── timing.json
│   └── outputs/
└── eval-N/
    └── ...
```

### Skills

- `run-evals` SKILL.md is a thin wrapper — it calls `run-evals.sh` and
  displays `summary.md`. No subagent spawning or aggregation logic.
- `develop-eval` SKILL.md is a full LLM skill — it reads a target
  SKILL.md, generates `evals.json`, fixture files, and optionally copies
  the CI template. It is idempotent (additive only on re-runs).

## Origin

Extracted from the [sdlc-plugins](https://github.com/mrizzi/sdlc-plugins)
repo where the eval framework was originally built as part of the
sdlc-workflow plugin. The migration path is documented in Section 8 of
the design spec.
