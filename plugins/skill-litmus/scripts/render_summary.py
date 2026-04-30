#!/usr/bin/env python3
"""Render results as Markdown summary with optional baseline comparison."""

import argparse
import json
import os
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def fmt_pct(value):
    return f"{value:.1%}"


def fmt_delta(value, fmt_fn=fmt_pct, invert=False):
    sign = "+" if value >= 0 else ""
    indicator = ""
    if value > 0:
        indicator = " (worse)" if invert else " (better)"
    elif value < 0:
        indicator = " (better)" if invert else " (worse)"
    return f"{sign}{fmt_fn(value)}{indicator}"


def render(results_dir, baseline_path=None, skill=None):
    benchmark_path = os.path.join(results_dir, "benchmark.json")
    if not os.path.exists(benchmark_path):
        print(f"Error: {benchmark_path} not found", file=sys.stderr)
        sys.exit(1)

    benchmark = load_json(benchmark_path)
    s = benchmark["run_summary"]

    baseline = None
    if baseline_path and os.path.exists(baseline_path):
        baseline = load_json(baseline_path)

    heading = f"# Eval Results: {skill}" if skill else "# Eval Results"
    lines = []
    lines.append(heading)
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(
        f"| Evals passed | {s['passed']}/{s['total_evals']}"
        f" ({fmt_pct(s['pass_rate'])}) |"
    )
    lines.append(
        f"| Assertions passed | {s['passed_assertions']}/{s['total_assertions']}"
        f" ({fmt_pct(s['assertion_pass_rate'])}) |"
    )
    lines.append(f"| Avg duration | {s['avg_duration_seconds']:.1f}s |")

    if baseline:
        bs = baseline["run_summary"]
        delta_pass = s["pass_rate"] - bs["pass_rate"]
        delta_assert = s["assertion_pass_rate"] - bs["assertion_pass_rate"]
        delta_dur = s["avg_duration_seconds"] - bs["avg_duration_seconds"]

        lines.append("")
        lines.append("### vs. Baseline")
        lines.append("")
        lines.append("| Metric | Delta |")
        lines.append("|--------|-------|")
        lines.append(f"| Pass rate | {fmt_delta(delta_pass)} |")
        lines.append(f"| Assertion pass rate | {fmt_delta(delta_assert)} |")
        lines.append(
            f"| Avg duration | "
            f"{fmt_delta(delta_dur, lambda v: f'{v:.1f}s', invert=True)} |"
        )

    lines.append("")
    lines.append("## Per-Eval Results")
    lines.append("")
    lines.append("| Eval | Status | Assertions | Duration |")
    lines.append("|------|--------|------------|----------|")

    for result in s["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"| eval-{result['eval_id']} | {status} "
            f"| {result['assertions_passed']}/{result['assertions_total']} "
            f"| {result['duration_seconds']:.1f}s |"
        )

    failed_results = [r for r in s["results"] if not r["passed"]]
    if failed_results:
        lines.append("")
        lines.append("## Failed Assertions")
        lines.append("")
        for result in failed_results:
            eval_id = result["eval_id"]
            grading_path = os.path.join(
                results_dir, f"eval-{eval_id}", "grading.json"
            )
            if os.path.exists(grading_path):
                grading = load_json(grading_path)
                lines.append(f"### eval-{eval_id}")
                lines.append("")
                for assertion in grading["assertions"]:
                    if not assertion["passed"]:
                        lines.append(f"- **{assertion['assertion']}**")
                        lines.append(f"  - {assertion['reasoning']}")
                lines.append("")

    output = "\n".join(lines)
    if not output.endswith("\n"):
        output += "\n"

    output_path = os.path.join(results_dir, "summary.md")
    with open(output_path, "w") as f:
        f.write(output)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Render summary as Markdown"
    )
    parser.add_argument("--results", required=True, help="Workspace directory")
    parser.add_argument(
        "--baseline", help="Path to baseline benchmark.json for comparison"
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        help="Skill name to include in the heading",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.results):
        print(f"Error: {args.results} is not a directory", file=sys.stderr)
        sys.exit(1)

    render(args.results, args.baseline, args.skill)
    print(f"Summary written to {os.path.join(args.results, 'summary.md')}")


if __name__ == "__main__":
    main()
