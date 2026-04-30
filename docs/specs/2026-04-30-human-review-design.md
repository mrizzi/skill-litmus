# Human Review for Skill Litmus

Date: 2026-04-30

## 1. Overview

Add human-in-the-loop review to the skill-litmus eval pipeline.
Humans provide per-eval feedback via PR comments using slash commands.
That feedback drives skill iteration through develop-eval, closing the
loop between automated grading and human judgment.

Three slash commands:

- `/skill-litmus feedback` — capture per-eval human feedback
- `/skill-litmus rerun` — re-execute evals on the PR
- `/skill-litmus iterate` — run develop-eval with captured feedback
  (maintainers only)

Primary workflow is CI (GitHub Action on PRs). Local workflow mirrors
CI using the same scripts.

## 2. Motivation

Automated assertion grading catches what you thought to write assertions
for. Human review catches what you didn't: wrong approaches, poor style,
outputs that are technically correct but miss the point. The
agentskills.io eval model positions human review as a distinct step that
produces `feedback.json` — per-eval notes that feed into skill iteration
alongside failed assertions and execution transcripts.

skill-litmus currently runs evals and grades assertions automatically
but has no mechanism for capturing human feedback. The `develop-eval`
skill already reads `feedback.json` in iteration mode but nothing
populates it.

## 3. Design

### 3.1 Event Flow

The GitHub Action (`action.yml`) gains a third event path:
`issue_comment`. Existing `pull_request` and `push` paths are unchanged.

```
pull_request  → run changed evals, post PR review       (existing)
push          → run all evals, commit baselines          (existing)
issue_comment → parse /skill-litmus command, dispatch    (new)
```

Command routing in the `issue_comment` path:

1. Guard: only process comments on PRs, not plain issues.
2. Extract command and arguments from `github.event.comment.body`.
3. Match against `/skill-litmus\s+(feedback|rerun|iterate)\s*(.*)`.
4. Route to the appropriate handler.
5. React on the comment: 👀 when processing starts, ✅ when done,
   ❌ on error.

### 3.2 Slash Commands

#### `/skill-litmus feedback`

Captures per-eval human feedback from a PR comment.

**Input format.** The eval results PR review includes a bot-generated
feedback template listing all eval IDs. The user copies the template,
fills in notes, and posts it as a comment:

```
/skill-litmus feedback
eval-1: The axis labels are unreadable
eval-2:
eval-3: Months are in alphabetical order instead of chronological
```

Empty entries (e.g., `eval-2:`) mean "reviewed, looks fine." This
matches the agentskills.io convention where empty feedback is a
deliberate human judgment, not a default.

**Parsing.** Fully deterministic — regex matches `eval-(\d+):\s*(.*)`
lines. No LLM involved. Handled by `capture-feedback.sh`.

**Output.** Writes `feedback.json` to `evals/<skill>/feedback.json` and
commits to the PR branch. Format follows the agentskills.io model:

```json
{
  "eval-1": "The axis labels are unreadable",
  "eval-2": "",
  "eval-3": "Months are in alphabetical order instead of chronological"
}
```

**Multiple rounds.** If the user posts `/skill-litmus feedback` again,
entries are merged — new feedback replaces old feedback for the same eval
IDs.

**Bot reply.** Reacts ✅ and posts: "Feedback captured for eval-1,
eval-2, eval-3. Run `/skill-litmus iterate` to generate improvement
suggestions."

#### `/skill-litmus rerun`

Re-executes evals on the PR. Used after manually applying SKILL.md
changes or updating assertions.

**Implementation.** Calls the same shared script (`run-pr-evals.sh`)
used by the `pull_request` event path. The only difference is how the
base SHA is obtained:

- `pull_request` event: `github.event.pull_request.base.sha`
- `rerun` command: `gh pr view --json baseRefOid -q '.baseRefOid'`

Everything downstream — skill detection, baseline fetch, eval execution,
grading, aggregation, rendering, review posting — is identical. This
ensures complete consistency between event-triggered and
command-triggered runs.

**Bot reply.** Updates the existing PR review with new results (same as
`pull_request` path).

#### `/skill-litmus iterate`

Runs develop-eval in CI to propose SKILL.md improvements based on
captured feedback.

**Permission gate.** Before any processing, checks
`github.event.comment.author_association`. Only allows `OWNER`,
`MEMBER`, or `COLLABORATOR`. Rejects with ❌ and reply: "Only
repository maintainers can trigger iteration."

**Rationale for the gate.** Eval fixtures may contain adversarial
content (prompt injection test cases are a legitimate eval category).
The `iterate` command feeds eval outputs to `claude -p`, which could
be manipulated into proposing harmful SKILL.md changes. Gating to
maintainers ensures only trusted users can trigger this LLM-driven
step. Combined with the fact that changes are never auto-applied,
this provides defense in depth.

**Precondition.** Requires `feedback.json` to exist on the PR branch.
If missing, replies with ❌: "No feedback found. Post
`/skill-litmus feedback` first."

**Steps:**

1. Downloads the eval workspace artifact (uploaded by the most recent
   `rerun` or `pull_request` run).
2. Reads `feedback.json` from the PR branch.
3. Reads the skill's `SKILL.md`.
4. Invokes `claude -p` with the develop-eval iteration prompt: grading
   results + feedback + current SKILL.md → proposed improvements.
5. Posts proposed changes as a PR review comment with a diff block
   showing the suggested SKILL.md modifications.
6. Does NOT auto-apply changes. The human decides whether to apply.

### 3.3 Feedback Template in Eval Results

`render_summary.py` appends a feedback template to `summary.md` after
the results tables:

```markdown
### Provide feedback

Copy the block below, fill in your notes, and post as a PR comment:

    /skill-litmus feedback
    eval-1:
    eval-2:
    eval-3:
```

This makes the feedback format discoverable — users don't need to
remember syntax. The template lists all eval IDs from the current run.

### 3.4 feedback.json Lifecycle

`feedback.json` is created only by human review, never auto-generated.

- **No human review:** `feedback.json` does not exist. `develop-eval`
  handles this gracefully — iterates on failed assertions and execution
  transcripts alone.
- **Human reviewed:** `feedback.json` exists with entries for all evals.
  Empty string = "reviewed, looks fine." Non-empty = actionable
  feedback.
- **After merge:** `feedback.json` is on the PR branch. It merges into
  main as part of the PR, providing a record of human review.

This aligns with the agentskills.io model where `feedback.json` presence
signals that human review occurred, and empty entries are deliberate
human judgments, not defaults.

### 3.5 Data Persistence Between Commands

The three slash commands run as separate GitHub Actions workflow
invocations. Each gets a fresh environment.

**Split by ownership:**

| Data | Storage | Rationale |
|------|---------|-----------|
| `feedback.json` | Committed to PR branch | Human-authored, small, meaningful in PR diff |
| Eval workspace (grading.json, timing.json, outputs/) | GitHub Actions artifact | Machine-generated, ephemeral, potentially large |

- `pull_request` / `rerun` → runs evals, posts review, uploads
  workspace as artifact.
- `feedback` → commits `feedback.json` to PR branch.
- `iterate` → downloads workspace artifact + reads `feedback.json`
  from repo.

Artifacts use GitHub's default 90-day retention, sufficient for PR
lifecycles.

### 3.6 Shared PR Eval Logic

The eval execution logic currently inline in `action.yml`'s
`pull_request` path is extracted into `run-pr-evals.sh`. This script
takes a base SHA, evals directory, skills directory, and baseline
branch as inputs and handles: changed-skill detection, baseline fetch,
`run-evals.sh` invocation per suite, and `post-results.sh pr` call.

Both the `pull_request` event handler and the `rerun` command handler
call `run-pr-evals.sh` with identical parameters, differing only in
how the base SHA is obtained.

### 3.7 Local Workflow

Each CI command has a local equivalent using the same scripts:

| CI command | Local equivalent |
|---|---|
| `/skill-litmus rerun` | `bash run-evals.sh --evals <path> --skill <name> --workspace <ws>` |
| `/skill-litmus feedback` | `bash capture-feedback.sh --workspace <ws> --eval 1 "notes" --eval 2 ""` |
| `/skill-litmus iterate` | `/skill-litmus:develop-eval` with workspace path |

`capture-feedback.sh` is the same script used by both CI and local.
It accepts two input modes (PR comment body via `--comment` or CLI
flags via `--eval`) and an `--output` path for where to write
`feedback.json`. In CI, output is `evals/<skill>/feedback.json`
(committed to PR branch). Locally, output is `<workspace>/feedback.json`.
Both produce the same format.

`run-evals.sh` and `develop-eval` already exist and require no
changes for local use.

## 4. File Changes

### New files

| File | Purpose |
|---|---|
| `plugins/skill-litmus/scripts/capture-feedback.sh` | Parse per-eval feedback, write `feedback.json`. Dual-mode: PR comment body or CLI flags. |
| `plugins/skill-litmus/scripts/run-pr-evals.sh` | Shared PR eval logic extracted from `action.yml`. Called by both `pull_request` and `rerun`. |

### Modified files

| File | Changes |
|---|---|
| `action.yml` | Add `issue_comment` event routing. Replace inline PR logic with `run-pr-evals.sh` call. Add command parsing, permission checks, artifact upload/download. |
| `plugins/skill-litmus/scripts/render_summary.py` | Append feedback template (eval ID list with empty slots) to `summary.md`. |
| `plugins/skill-litmus/scripts/post-results.sh` | Add `comment-reply` subcommand for posting bot responses to PR comments. |
| `plugins/skill-litmus/templates/eval-workflow.yml` | Add `issue_comment` to `on:` triggers. Add `permissions: pull-requests: write, contents: write`. |
| `plugins/skill-litmus/scripts/run-evals.sh` | Remove empty `feedback.json` creation (line 257). `feedback.json` is now human-authored only. |

### Minor modifications

| File | Changes |
|---|---|
| `plugins/skill-litmus/skills/develop-eval/SKILL.md` | Add graceful handling of missing `feedback.json` — iterate on failed assertions and execution transcripts alone when no human review has occurred. |

### Unchanged files

| File | Rationale |
|---|---|
| `evals.schema.json` | `feedback.json` is a separate file, not part of `evals.json`. |
| `plugins/skill-litmus/skills/run-evals/SKILL.md` | No changes needed. |
| `plugins/skill-litmus/scripts/aggregate_benchmark.py` | Not affected. |

## 5. agentskills.io Alignment

This design follows the agentskills.io eval model with the same
intentional divergence approach used elsewhere in skill-litmus
(documented in Section 9 of the original design spec).

**Aligned:**

- `feedback.json` format: keyed by eval ID, empty string = "reviewed,
  looks fine."
- `feedback.json` lifecycle: created only by human review, not
  auto-generated.
- Iteration loop: feedback + failed assertions + execution transcripts
  → proposed SKILL.md improvements.
- Human review is a distinct step, not merged with automated grading.

**Divergences:**

| Area | agentskills.io | skill-litmus | Rationale |
|------|---------------|-------------|-----------|
| Feedback key format | Descriptive names (`eval-top-months-chart`) | Numeric IDs (`eval-1`) | Consistent with existing skill-litmus naming (Section 9 of original spec). |
| Feedback entry point | Manual file editing | Slash commands in PR comments + CLI | CI-first workflow; humans shouldn't edit JSON by hand. |
| Iteration trigger | Manual (give signals to LLM) | `/skill-litmus iterate` command | Automated CI step with permission gating. |

## 6. Security Considerations

- **Prompt injection via eval outputs.** The `iterate` command feeds
  eval outputs (which may contain adversarial content) to `claude -p`.
  Mitigations: maintainer-only permission gate, changes are never
  auto-applied (posted as review comment with diff), human reviews
  proposed changes before applying.
- **Comment body parsing.** Command parsing uses strict regex matching.
  Only exact command names are accepted. Free text is confined to
  per-eval feedback entries and never interpreted as commands.
- **PR branch commits.** The `feedback` command commits to the PR
  branch. Only `feedback.json` is written — the commit content is
  deterministic (parsed from the structured comment, not LLM-generated).
