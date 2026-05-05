# Integration Test Job (Deferred)

Add this as Job 3 in `.github/workflows/test-action.yml` when ready to
run end-to-end eval tests with real API calls.

## Design

- Runs `run-evals.sh` directly against a minimal test fixture
- Costs ~$0.05/run (single eval, one assertion, trivial prompt)
- Skips gracefully when `ANTHROPIC_API_KEY` is unavailable (fork PRs)
- Calls `run-evals.sh` directly rather than `uses: ./` to avoid
  event-routing complexity

## Files to Create

`.github/test-fixtures/ci-eval/evals.json`:

```json
{
  "skill_name": "ci-eval",
  "plugin": "skill-litmus",
  "evals": [
    {
      "id": 1,
      "prompt": "Echo the text 'hello world' to stdout",
      "expected_output": "The text hello world printed to stdout",
      "files": [],
      "assertions": ["The output contains the text hello world"]
    }
  ]
}
```

## Workflow Job

```yaml
  integration:
    name: End-to-End Eval Run
    needs: unit-tests
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Skip if no API key
        if: env.ANTHROPIC_API_KEY == ''
        run: echo "::notice::Skipping — ANTHROPIC_API_KEY not configured"

      - name: Run eval engine with test fixture
        if: env.ANTHROPIC_API_KEY != ''
        run: |
          bash plugins/skill-litmus/scripts/run-evals.sh \
            --evals .github/test-fixtures/ci-eval/evals.json \
            --skill ci-eval \
            --workspace "$RUNNER_TEMP/ci-eval-workspace" \
            --plugin skill-litmus

      - name: Verify output structure
        if: env.ANTHROPIC_API_KEY != ''
        run: |
          ws="$RUNNER_TEMP/ci-eval-workspace"
          test -f "$ws/benchmark.json"
          test -f "$ws/summary.md"
          test -d "$ws/eval-1"
          test -f "$ws/eval-1/grading.json"
          test -f "$ws/eval-1/timing.json"
          jq -e '.run_summary.total_evals == 1' "$ws/benchmark.json"
          echo "All integration checks passed"
```

## Trigger Path Addition

Add `.github/test-fixtures/**` to the workflow's path filters when
enabling this job.
