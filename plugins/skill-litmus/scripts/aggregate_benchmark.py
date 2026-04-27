#!/usr/bin/env python3
"""Aggregate grading and timing results into benchmark.json."""

import argparse
import glob
import json
import os
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def aggregate(results_dir):
    eval_dirs = sorted(
        glob.glob(os.path.join(results_dir, "eval-*")),
        key=lambda d: int(os.path.basename(d).split("-", 1)[1]),
    )

    results = []
    total_assertions = 0
    passed_assertions = 0
    total_duration = 0.0

    for eval_dir in eval_dirs:
        grading_path = os.path.join(eval_dir, "grading.json")
        timing_path = os.path.join(eval_dir, "timing.json")

        if not os.path.exists(grading_path):
            print(f"Warning: {grading_path} not found, skipping", file=sys.stderr)
            continue

        grading = load_json(grading_path)
        eval_id = grading["eval_id"]
        assertions = grading["assertions"]
        n_passed = sum(1 for a in assertions if a["passed"])
        n_total = len(assertions)

        total_assertions += n_total
        passed_assertions += n_passed

        duration = 0.0
        if os.path.exists(timing_path):
            timing = load_json(timing_path)
            duration = timing.get("duration_seconds", 0.0)
        total_duration += duration

        results.append({
            "eval_id": eval_id,
            "passed": n_passed == n_total,
            "assertions_passed": n_passed,
            "assertions_total": n_total,
            "duration_seconds": duration,
        })

    n_evals = len(results)
    n_passed_evals = sum(1 for r in results if r["passed"])

    benchmark = {
        "run_summary": {
            "total_evals": n_evals,
            "passed": n_passed_evals,
            "failed": n_evals - n_passed_evals,
            "pass_rate": round(n_passed_evals / n_evals, 3) if n_evals else 0.0,
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "failed_assertions": total_assertions - passed_assertions,
            "assertion_pass_rate": round(passed_assertions / total_assertions, 3) if total_assertions else 0.0,
            "avg_duration_seconds": round(total_duration / n_evals, 1) if n_evals else 0.0,
            "results": results,
        }
    }

    output_path = os.path.join(results_dir, "benchmark.json")
    with open(output_path, "w") as f:
        json.dump(benchmark, f, indent=2)
        f.write("\n")

    return benchmark


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate results into benchmark.json"
    )
    parser.add_argument(
        "--results", required=True, help="Workspace directory containing eval-* subdirs"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.results):
        print(f"Error: {args.results} is not a directory", file=sys.stderr)
        sys.exit(1)

    benchmark = aggregate(args.results)
    summary = benchmark["run_summary"]
    print(
        f"Aggregated {summary['total_evals']} evals: "
        f"{summary['passed']} passed, {summary['failed']} failed"
    )


if __name__ == "__main__":
    main()
