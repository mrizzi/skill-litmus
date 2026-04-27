#!/usr/bin/env bash
# Post results: PR comment or baseline commit.
# See docs/specs/2026-04-24-standalone-eval-runner-design.md Section 3.
#
# Usage:
#   post-results.sh pr       --workspace <dir> [--workspace <dir> ...]
#   post-results.sh baseline --workspace <dir> --evals-dir <path> --commit-hash <hash>

set -euo pipefail

COMMENT_MARKER="<!-- skill-litmus-results -->"

MODE="${1:-}"
[[ -z "$MODE" ]] && echo "Usage: post-results.sh {pr|baseline} [options]" >&2 && exit 1
shift

case "$MODE" in
    pr)
        WORKSPACES=()
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --workspace) WORKSPACES+=("$2"); shift 2 ;;
                *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
            esac
        done

        [[ ${#WORKSPACES[@]} -eq 0 ]] && echo "Error: at least one --workspace required" >&2 && exit 1

        # Build combined comment body
        BODY="$COMMENT_MARKER"$'\n'"## Skill Eval Results"$'\n'
        for ws in "${WORKSPACES[@]}"; do
            if [[ -f "$ws/summary.md" ]]; then
                BODY+=$'\n'"$(cat "$ws/summary.md")"$'\n'$'\n'"---"$'\n'
            else
                BODY+=$'\n'"**Warning:** No summary found in $ws"$'\n'
            fi
        done

        # Detect PR number
        PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null || true)
        if [[ -z "$PR_NUMBER" ]]; then
            echo "Error: could not detect PR number. Are you in a PR context?" >&2
            exit 1
        fi

        # Find existing skill-litmus comment to update
        COMMENT_ID=$(gh api "repos/{owner}/{repo}/issues/$PR_NUMBER/comments" \
            --jq ".[] | select(.body | startswith(\"$COMMENT_MARKER\")) | .id" \
            2>/dev/null | head -1 || true)

        if [[ -n "$COMMENT_ID" ]]; then
            gh api "repos/{owner}/{repo}/issues/comments/$COMMENT_ID" \
                -X PATCH -f body="$BODY" > /dev/null
            echo "Updated existing PR comment ($COMMENT_ID)"
        else
            gh pr comment "$PR_NUMBER" --body "$BODY" > /dev/null
            echo "Posted new PR comment"
        fi
        ;;

    baseline)
        WORKSPACE=""
        EVALS_DIR=""
        COMMIT_HASH=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --workspace)   WORKSPACE="$2";   shift 2 ;;
                --evals-dir)   EVALS_DIR="$2";   shift 2 ;;
                --commit-hash) COMMIT_HASH="$2"; shift 2 ;;
                *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
            esac
        done

        [[ -z "$WORKSPACE" ]]   && echo "Error: --workspace required" >&2 && exit 1
        [[ -z "$EVALS_DIR" ]]   && echo "Error: --evals-dir required" >&2 && exit 1
        [[ -z "$COMMIT_HASH" ]] && echo "Error: --commit-hash required" >&2 && exit 1

        BASELINE_DIR="$EVALS_DIR/baselines/$COMMIT_HASH"
        mkdir -p "$BASELINE_DIR"

        cp "$WORKSPACE/benchmark.json" "$BASELINE_DIR/"

        # Relative symlink so it works when the repo is cloned anywhere
        ln -snf "$COMMIT_HASH" "$EVALS_DIR/baselines/latest"

        git add "$EVALS_DIR/baselines/"
        git commit -m "chore: update baseline for ${COMMIT_HASH:0:7}" || true
        git push || true

        echo "Baseline committed: $BASELINE_DIR"
        ;;

    *)
        echo "Usage: post-results.sh {pr|baseline} [options]" >&2
        exit 1
        ;;
esac
