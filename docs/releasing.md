# Releasing

This document describes how to release a new version of the skill-litmus plugin and GitHub Action.

## Release Process

1. **Develop on a branch** — make skill/plugin/action changes on a feature branch, open a PR, get it reviewed, and merge to the default branch.

2. **Bump the version** — update the `version` field in **both** of these files (they must stay in sync):
   - `.claude-plugin/marketplace.json` — required by Claude Code for relative-path plugins to detect available updates
   - `plugins/skill-litmus/.claude-plugin/plugin.json` — required to pass `claude plugin validate` without warnings

   Follow [Semantic Versioning](https://semver.org/) using the decision criteria in the [Version Bump Decision Guide](#version-bump-decision-guide) below:
   - `0.X.0` → `0.(X+1).0` (y-stream) for new features or breaking changes
   - `0.X.Y` → `0.X.(Y+1)` (z-stream) for enhancements, bug fixes, and polish

3. **Commit the version bump** with the message:
   ```
   chore(release): bump version to X.Y.Z
   ```

4. **Push to the default branch.**

5. **Create a GitHub release** — tag the release commit and create a GitHub release:
   ```bash
   git tag vX.Y.Z <commit-sha>
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --latest --notes "<release notes>"
   ```

6. **Adopters reference the tag** in their GitHub Action workflows:
   ```yaml
   - uses: mrizzi/skill-litmus@v0.2.0
   ```

## Version Bump Decision Guide

The version bump decision is a **human judgment call**, not a mechanical scan of commit prefixes. A commit tagged `feat` does not automatically mean a y-stream bump — many `feat` commits are enhancements to existing functionality and belong in a z-stream release.

### Decision checklist

Ask these questions about the changes since the last release:

| Question | If yes |
|---|---|
| Does this release introduce a **new skill** (e.g. `develop-eval`)? | y-stream |
| Does it introduce a **breaking change** to the `evals.json` schema, output layout, or action inputs? | y-stream |
| Does it fundamentally change how the engine orchestrates eval execution or grading? | y-stream |
| Does it improve an **existing skill's output**, formatting, or prompts? | z-stream |
| Does it add guidance, guardrails, or documentation to an existing skill? | z-stream |
| Does it improve scripts without changing their interface? | z-stream |
| Is it a bug fix, typo correction, or documentation update? | z-stream |

If none of the y-stream criteria apply, use a z-stream bump — even if every commit uses the `feat` prefix.

### Examples

**z-stream (`feat` commits that are enhancements, not new features):**

- `feat: add skill name to eval result summary headings` — improves existing summary output formatting; no new capability is introduced
- `feat: post eval results as PR review instead of issue comment` — changes how results are posted but the eval workflow itself is unchanged

**y-stream (genuinely new features or breaking changes):**

- `feat: add develop-eval skill for eval authoring` — introduces an entirely new skill that didn't exist before
- `feat: add new required field to evals.json schema` — breaking change to the eval contract

## Changelog Scope

Not all commits belong in the changelog. Exclude commits that are purely internal housekeeping and have no user-facing impact:

- **Eval baselines** (`chore(evals): create baselines for …`) — these record expected outputs for skill evaluations and do not change plugin behavior.
- **Test-only changes** (`test: …`) — internal test additions or updates with no user-facing effect.

## Versioning Rules

- The version in `marketplace.json` is what Claude Code uses to detect whether an update is available for relative-path plugins. If the version doesn't change, `/plugin marketplace update` will skip the plugin even if files have changed.
- The version in `plugin.json` is required by `claude plugin validate` — omitting it produces a warning. It must match `marketplace.json` to stay consistent.
- Git tags are the primary version reference for GitHub Action consumers. The tag, `marketplace.json`, and `plugin.json` versions must all stay in sync.
