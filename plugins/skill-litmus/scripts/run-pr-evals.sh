#!/usr/bin/env bash
# Shared PR logic — runs changed skills and posts results.
# See docs/specs/2026-04-30-human-review-design.md Section 3.6.
#
# Usage:
#   run-pr-evals.sh --base-sha <sha> --evals-dir <path> \
#                    --workspace-root <dir> --changed-files <text> \
#                    [--skills-dir <path>] [--baseline-branch <branch>]

set -euo pipefail

BASE_SHA=""
EVALS_DIR=""
WORKSPACE_ROOT=""
CHANGED_FILES=""
SKILLS_DIR=""
BASELINE_BRANCH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-sha)        BASE_SHA="$2";        shift 2 ;;
        --evals-dir)       EVALS_DIR="$2";       shift 2 ;;
        --workspace-root)  WORKSPACE_ROOT="$2";  shift 2 ;;
        --changed-files)   CHANGED_FILES="$2";   shift 2 ;;
        --skills-dir)      SKILLS_DIR="$2";      shift 2 ;;
        --baseline-branch) BASELINE_BRANCH="$2"; shift 2 ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -z "$BASE_SHA" ]]       && echo "Error: --base-sha required" >&2 && exit 1
[[ -z "$EVALS_DIR" ]]      && echo "Error: --evals-dir required" >&2 && exit 1
[[ -z "$WORKSPACE_ROOT" ]] && echo "Error: --workspace-root required" >&2 && exit 1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$BASELINE_BRANCH" ]]; then
    BASELINE_BRANCH=$(gh repo view --json defaultBranchRef -q '.defaultBranchRef.name' 2>/dev/null || echo "main")
fi

if [[ -z "$CHANGED_FILES" ]]; then
    CHANGED_FILES=$(git diff --name-only "$BASE_SHA"...HEAD 2>/dev/null || true)
fi

EVALS_TO_RUN=()
for evals_json in ${EVALS_DIR}*/evals.json; do
    [[ ! -f "$evals_json" ]] && continue
    skill_dir="$(dirname "$evals_json")"
    skill_name="$(basename "$skill_dir")"

    if echo "$CHANGED_FILES" | grep -qE "(${skill_dir}/|${SKILLS_DIR:-skills/}.*${skill_name})"; then
        EVALS_TO_RUN+=("$evals_json")
    fi
done

if [[ ${#EVALS_TO_RUN[@]} -eq 0 ]]; then
    echo "No changed suites detected."
    exit 0
fi

WORKSPACE_ARGS=()
for evals_json in "${EVALS_TO_RUN[@]}"; do
    skill_name=$(jq -r '.skill_name' "$evals_json")
    if [[ ! "$skill_name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo "Error: invalid skill_name in $evals_json: $skill_name" >&2
        continue
    fi
    ws="$WORKSPACE_ROOT/$skill_name"
    skill_dir="$(dirname "$evals_json")"

    baseline_args=()
    baseline_file="$skill_dir/baselines/latest/benchmark.json"
    baseline_tmp="$WORKSPACE_ROOT/baseline-${skill_name}.json"
    if git show "$BASELINE_BRANCH:$baseline_file" > "$baseline_tmp" 2>/dev/null; then
        baseline_args=(--baseline "$baseline_tmp")
    fi

    bash "$SCRIPT_DIR/run-evals.sh" \
        --evals "$evals_json" \
        --skill "$skill_name" \
        --workspace "$ws" \
        ${baseline_args[@]+"${baseline_args[@]}"}

    WORKSPACE_ARGS+=("--workspace" "$ws")
done

if [[ ${#WORKSPACE_ARGS[@]} -gt 0 ]]; then
    bash "$SCRIPT_DIR/post-results.sh" pr "${WORKSPACE_ARGS[@]}"
fi

echo "PR evals complete."
