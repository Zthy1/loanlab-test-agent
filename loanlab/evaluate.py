"""Reproducible deterministic baseline evaluation, not a live model benchmark."""
import argparse
import json
from pathlib import Path

from .engine import run_case

CASES = [
    ("normal", "创建贷款并撤回", "normal", "PASS"),
    ("async", "创建贷款并撤回", "delayed", "PASS"),
    ("false-success", "创建贷款并撤回", "noop", "FAIL"),
    ("dependency-unavailable", "创建贷款并撤回", "query_error", "ERROR"),
    ("out-of-scope", "删除数据库", "normal", "REJECTED"),
]


def evaluate():
    rows = []
    for name, task, scenario, expected in CASES:
        report = run_case(task, scenario)
        rows.append({"case": name, "expected": expected, "actual": report["status"],
                     "matched": report["status"] == expected})
    return {"planner": "deterministic template", "backend": "local simulation",
            "live_model": False, "cases": rows, "matched": sum(r["matched"] for r in rows),
            "total": len(rows), "note": "受控场景契约检查，不代表真实业务或模型泛化准确率"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    body = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0 if result["matched"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
