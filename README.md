# skill-litmus

An opinionated implementation of the
[agentskills.io eval specification](https://agentskills.io/skill-creation/evaluating-skills)
for agent skills.

The agentskills.io spec defines how to evaluate skill output quality
through structured test cases, LLM-graded assertions, and iterative
improvement. skill-litmus takes that spec and builds a complete,
deterministic execution engine around it --- shell scripts and Python
that handle orchestration, grading, aggregation, and reporting so that
LLM tokens are spent only on the parts that need them (running skills
and judging outputs).

Currently the engine runs evals through **Claude Code** (`claude -p`),
so an **Anthropic API key** is required. It ships as a Claude Code
plugin with two skills, a bash/Python engine, and a GitHub Action for
CI.

## Prerequisites

- **Claude Code** CLI (`claude`) ---
  [install instructions](https://docs.anthropic.com/en/docs/claude-code/overview)
- **Anthropic API key** --- set `ANTHROPIC_API_KEY` in your environment.
  The engine calls `claude -p` for eval execution and grading, which
  requires API access.
- **jq** --- JSON processing in shell scripts.
- **Python 3** --- stdlib only, no external dependencies.
- **gh** CLI --- required only for CI features (posting PR reviews,
  committing baselines).

## Install

Add skill-litmus as a Claude Code plugin:

```bash
claude plugin add mrizzi/skill-litmus
```

This gives you two skills:

| Skill | Purpose |
|-------|---------|
| `/skill-litmus:run-evals` | Run an eval suite and display results |
| `/skill-litmus:develop-eval` | Generate test cases, fixture files, and assertions for a skill |

## Quick start

### 1. Author evals

Use the `develop-eval` skill to generate evals automatically:

```
/skill-litmus:develop-eval
```

It reads your SKILL.md, identifies inputs, outputs, and failure modes,
then generates test cases with realistic prompts, fixture files, and
concrete assertions.

Alternatively, create `evals/<your-skill>/evals.json` by hand:

```json
{
  "skill_name": "your-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "A realistic user message that exercises the skill",
      "expected_output": "Human-readable description of what good output looks like",
      "files": ["files/fixture.csv"],
      "assertions": [
        "The output contains a summary section",
        "All input rows are accounted for in the result"
      ]
    }
  ]
}
```

### 2. Run evals

```
/skill-litmus:run-evals
```

Or directly via the engine:

```bash
plugins/skill-litmus/scripts/run-evals.sh \
  --evals evals/your-skill/evals.json \
  --skill your-skill \
  --workspace /tmp/eval-run
```

### 3. Review results

The run produces a workspace with this structure:

```
workspace/
  benchmark.json       # Aggregated pass rates and timing
  feedback.json        # Placeholder for human review notes
  summary.md           # Markdown report with per-eval results
  eval-1/
    execution.log      # Full agent transcript
    grading.json       # Per-assertion pass/fail with reasoning
    timing.json        # Wall-clock duration
    outputs/           # Files the skill produced
  eval-2/
    ...
```

## How it works

```
evals.json
    |
    v
run-evals.sh ── for each case ──> claude -p (execute skill, capture outputs)
    |                                  |
    |                                  v
    |                            claude -p (grade assertions against outputs)
    |                                  |
    v                                  v
aggregate_benchmark.py <──── grading.json + timing.json
    |
    v
render_summary.py ──> summary.md
```

The engine is deterministic shell and Python. LLM calls happen in
exactly two places: executing each eval case and grading the assertions
afterward. Everything else --- workspace layout, fixture handling,
aggregation, rendering, baseline comparison --- is mechanical.

Cases execute in parallel (background bash jobs). Grading also runs in
parallel after all executions complete.

## evals.json schema

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `skill_name` | string | yes | Slash-command name without plugin namespace |
| `plugin` | string | no | Plugin namespace. Auto-detected from `plugin.json` if omitted |
| `evals` | array | yes | One or more test cases |

Each eval object:

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `id` | integer | yes | Unique, stable, positive identifier |
| `prompt` | string | yes | User prompt sent to the skill |
| `expected_output` | string | yes | What good output looks like (human-readable) |
| `files` | string[] | no | Fixture file paths relative to the evals.json directory |
| `assertions` | string[] | yes | Statements graded as pass/fail by the LLM judge |

The full JSON Schema is in [`evals.schema.json`](evals.schema.json).

### Writing good assertions

Assertions are LLM-graded, so they should be specific and observable:

```
"The output includes a bar chart image file"       # specific, checkable
"Both axes are labeled"                             # observable
"The report includes at least 3 recommendations"   # countable
```

Avoid vague (`"The output is good"`) or overly brittle assertions
(`"The output contains exactly the string '...'"`) --- the former can't
be graded reliably, the latter fails on correct output with different
wording.

## CI with GitHub Actions

skill-litmus includes a GitHub Action that runs evals on PRs and tracks
baselines on merge. It also supports human-in-the-loop review through
slash commands posted as PR comments.

### Setup

1. Add your `ANTHROPIC_API_KEY` as a repository secret.
2. Copy the workflow template into your repo:

```bash
cp plugins/skill-litmus/templates/eval-workflow.yml \
   .github/workflows/eval.yml
```

Or let `develop-eval` do it --- it copies the template if no workflow
exists.

### Action inputs

```yaml
- uses: mrizzi/skill-litmus@v1
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  with:
    evals-dir: 'evals/'                # default
    skills-dir: 'skills/'             # auto-detected if omitted
    baseline-branch: 'main'           # defaults to repo default branch
```

### Workflow

The action responds to three GitHub events:

| Event | Trigger | What happens |
|-------|---------|--------------|
| `pull_request` | PR opened or updated | Runs evals for changed skills only, posts results as a PR review |
| `push` | Merge to main | Runs all eval suites, commits `benchmark.json` to `evals/<skill>/baselines/` |
| `issue_comment` | Slash command on a PR | Parses the command and dispatches to the appropriate handler (see below) |

A typical PR cycle looks like this:

1. Open or update a PR that changes a skill or its evals.
2. The action runs affected evals automatically and posts a review with
   results and a feedback template.
3. Review the results. Post human feedback using `/skill-litmus feedback`.
4. Run `/skill-litmus iterate` to run `develop-eval` in CI and get
   AI-proposed SKILL.md improvements based on failed assertions and
   your feedback.
5. Apply the suggested changes and run `/skill-litmus rerun` to verify.
6. Merge. The action commits baselines to main for future comparison.

### Slash commands

Post these as a comment on a PR where evals have run.

#### `/skill-litmus feedback`

Captures per-eval human feedback. The eval results review includes a
template you can copy and fill in:

```
/skill-litmus feedback
eval-1: The axis labels are unreadable
eval-2:
eval-3: Months are in alphabetical order instead of chronological
```

Empty entries (e.g., `eval-2:`) mean "reviewed, looks fine" --- this is
a deliberate signal, not a default. Feedback is committed to
`feedback.json` on the PR branch. Posting again merges new entries with
existing ones.

#### `/skill-litmus rerun`

Re-executes evals on the current PR head. Use after manually applying
SKILL.md changes or updating assertions. Results replace the existing
PR review.

#### `/skill-litmus iterate`

Runs `develop-eval` in CI to propose SKILL.md improvements. Reads
failed assertions, human feedback from `feedback.json`, and execution
transcripts, then posts suggested changes as a review comment with a
diff block.

**Maintainers only.** Restricted to repository owners, members, and
collaborators. Changes are never auto-applied --- the human decides
whether to accept them.

**Requires feedback first.** If no `feedback.json` exists on the PR
branch, the command replies with an error asking you to post
`/skill-litmus feedback` first.

### Baselines

On push to main, the action saves `benchmark.json` to
`evals/<skill>/baselines/<commit-hash>/` with a `latest` symlink. On
subsequent PRs, the engine loads the baseline and `summary.md` includes
delta comparisons for pass rate, assertion rate, and duration.

## Iterating on a skill

The `develop-eval` skill supports an iteration workflow. Point it at a
workspace with results from a previous run:

```
/skill-litmus:develop-eval
```

It reads failed assertions, human feedback from `feedback.json`, and
execution transcripts, then proposes targeted improvements to the
skill's SKILL.md. Changes are presented for review before applying.

This follows the agentskills.io iteration loop: run evals, grade, review
with a human, improve the skill, repeat.

## Divergences from agentskills.io

The evals.json schema is compatible with the agentskills.io spec. Four
intentional divergences exist in surrounding infrastructure:

1. **Eval directory location** --- agentskills.io places evals inside
   the skill directory (`my-skill/evals/evals.json`). skill-litmus
   stores them in a top-level `evals/` directory outside the skill path
   to avoid shipping test data and fixtures when releasing the skill.

2. **benchmark.json structure** --- agentskills.io uses
   `with_skill`/`without_skill` comparison with mean/stddev. skill-litmus
   uses a single `run_summary` with flat pass/fail counts, since the
   engine runs only the with-skill configuration and compares against
   stored baselines rather than a live without-skill run.

3. **Eval directory naming** --- agentskills.io uses descriptive names
   (`eval-top-months-chart/`). skill-litmus uses `eval-<id>/` keyed to
   the integer ID in evals.json for deterministic, collision-free
   directory creation.

4. **Token counting** --- agentskills.io records `total_tokens` per run.
   skill-litmus captures wall-clock `duration_seconds` instead, since
   `claude -p` does not expose token counts in its output.

## Project structure

```
skill-litmus/
  action.yml                           # GitHub Action
  evals.schema.json                    # JSON Schema for evals.json
  plugins/
    skill-litmus/
      .claude-plugin/
        plugin.json
      scripts/
        run-evals.sh                   # Core orchestrator
        aggregate_benchmark.py         # Builds benchmark.json
        render_summary.py              # Renders summary.md
        post-results.sh                # PR reviews and baseline commits
      skills/
        run-evals/
          SKILL.md                     # Interactive eval runner
        develop-eval/
          SKILL.md                     # Eval authoring and iteration
      templates/
        eval-workflow.yml              # CI template for adopters
  tests/
    ...
```

## License

[Apache 2.0](LICENSE)
