"""Teaching-only plan validation. No model, network, or business execution."""

import json
from pathlib import Path


def validate_plan(plan):
    """Validate exactly one reviewed scenario, not a general workflow language."""
    if not isinstance(plan, dict):
        raise ValueError("Plan must be an object")
    if plan.get("case_id") != "LOAN-WITHDRAW-001":
        raise ValueError("Only the reviewed withdrawal case is supported")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) != 3:
        raise ValueError("The reviewed case requires exactly three steps")
    expected = [
        {"tool": "create_pending_loan", "args": {}, "save_as": "loan_id"},
        {"tool": "withdraw_loan", "args": {"loan_id": "$loan_id"}},
        {"tool": "verify_withdrawn", "args": {"loan_id": "$loan_id"}},
    ]
    for index, (step, reviewed_step) in enumerate(zip(steps, expected), start=1):
        if step != reviewed_step:
            raise ValueError(f"Step {index} differs from the reviewed contract")
    return [step["tool"] for step in steps]


if __name__ == "__main__":
    path = Path(__file__).with_name("withdrawal_plan.json")
    with path.open(encoding="utf-8") as source:
        tools = validate_plan(json.load(source))
    print("PLAN_VALIDATED_NOT_EXECUTED")
    for index, tool in enumerate(tools, start=1):
        print(f"{index}. {tool}")
    print("No LLM call or Fineract request was made.")
