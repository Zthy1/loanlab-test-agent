"""Deterministic teaching baseline. No LLM, network or Fineract calls."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .validate_plan import validate_plan


SCENARIOS = {
    "normal": {"label": "正常撤回", "delay": 0},
    "delayed": {"label": "延迟 2 秒后生效", "delay": 2},
    "noop": {"label": "返回 200，但状态不变", "delay": None},
    "query_error": {"label": "撤回后查询异常", "delay": 0},
}
TEMPLATE = Path(__file__).with_name("withdrawal_plan.json")


class ToolError(Exception):
    pass


class BusinessMismatch(Exception):
    pass


class VirtualClock:
    """Allows reproducible polling without pretending this is real latency."""

    def __init__(self):
        self.seconds = 0

    def wait(self, seconds):
        self.seconds += seconds


class SimulatedBackend:
    def __init__(self, scenario, clock):
        self.scenario = scenario
        self.clock = clock
        self.loans = {}
        self.polls = []

    def create(self):
        loan_id = 1001
        self.loans[loan_id] = {"status": "SUBMITTED_AND_PENDING_APPROVAL", "requested_at": None}
        return {"loan_id": loan_id, "status": self.loans[loan_id]["status"]}

    def withdraw(self, loan_id):
        loan = self.loans[loan_id]
        if loan["status"] != "SUBMITTED_AND_PENDING_APPROVAL":
            raise ToolError("贷款不处于待审批状态")
        loan["requested_at"] = self.clock.seconds
        return {"http_status": 200, "accepted": True, "loan_id": loan_id}

    def query(self, loan_id):
        loan = self.loans[loan_id]
        if self.scenario == "query_error" and loan["requested_at"] is not None:
            self.polls.append({"virtual_second": self.clock.seconds, "error": "模拟查询依赖不可用"})
            raise ToolError("模拟查询依赖不可用，无法确认最终状态")
        delay = SCENARIOS[self.scenario]["delay"]
        requested_at = loan["requested_at"]
        if requested_at is not None and delay is not None and self.clock.seconds - requested_at >= delay:
            loan["status"] = "WITHDRAWN_BY_CLIENT"
        self.polls.append({"virtual_second": self.clock.seconds, "loan_id": loan_id, "status": loan["status"]})
        return loan["status"]


class TemplatePlanner:
    """Replaceable planner boundary; this implementation is NOT an LLM."""

    name = "固定模板规划（非模型）"

    def plan(self, task):
        if not isinstance(task, str) or not task.strip() or len(task) > 500:
            raise ValueError("任务必须为 1–500 字的文本")
        if "撤回" not in task or not any(word in task for word in ("贷款", "申请")):
            raise ValueError("基线目前仅支持贷款申请撤回任务")
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def validate_contract(plan):
    # Top-level metadata is validated too. Execution does not trust model text.
    if not isinstance(plan, dict) or set(plan) != {"case_id", "description", "steps"}:
        raise ValueError("计划顶层字段不符合当前审核契约")
    if not isinstance(plan["description"], str) or len(plan["description"]) > 1000:
        raise ValueError("计划描述无效")
    validate_plan(plan)


def run_case(task, scenario="normal", *, planner=None, timeout_seconds=5, poll_interval=1):
    if scenario not in SCENARIOS:
        raise ValueError("未知模拟场景")
    if timeout_seconds <= 0 or poll_interval <= 0:
        raise ValueError("等待上限和轮询间隔必须大于零")
    planner = planner or TemplatePlanner()
    started = perf_counter()
    report = {
        "run_id": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LOCAL_SIMULATION",
        "planner": planner.name,
        "task": task,
        "scenario": scenario,
        "scenario_label": SCENARIOS[scenario]["label"],
        "injected_fault": scenario if scenario in {"noop", "query_error"} else None,
        "status": "ERROR",
        "plan": None,
        "trace": [],
        "polls": [],
        "evidence": {},
        "diagnosis": None,
    }
    try:
        plan = deepcopy(planner.plan(task))
        validate_contract(plan)
    except ValueError as exc:
        report.update(status="REJECTED", diagnosis={"method": "确定性规则", "fact": str(exc), "root_cause": "未执行，计划被拒绝"})
        report["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
        return report
    report["plan"] = plan
    clock = VirtualClock()
    backend = SimulatedBackend(scenario, clock)
    context = {}
    evidence = report["evidence"]

    def verify_withdrawn(loan_id):
        expected = "WITHDRAWN_BY_CLIENT"  # Reviewed contract, not model-controlled.
        deadline = clock.seconds + timeout_seconds
        evidence.update(loan_id=loan_id, expected=expected, timeout_virtual_seconds=timeout_seconds)
        while True:
            actual = backend.query(loan_id)
            evidence["actual"] = actual
            if actual == expected:
                return {"loan_id": loan_id, "expected": expected, "actual": actual, "passed": True}
            if clock.seconds >= deadline:
                raise BusinessMismatch("模拟等待期限内未观察到已撤回状态")
            clock.wait(min(poll_interval, deadline - clock.seconds))

    registry = {
        "create_pending_loan": backend.create,
        "withdraw_loan": backend.withdraw,
        "verify_withdrawn": verify_withdrawn,
    }
    for step in plan["steps"]:
        args = {key: context[value[1:]] if isinstance(value, str) and value.startswith("$") else value
                for key, value in step["args"].items()}
        entry = {"tool": step["tool"], "args": args, "virtual_start": clock.seconds}
        t0 = perf_counter()
        try:
            output = registry[step["tool"]](**args)
            entry.update(status="OK", output=output)
            if "save_as" in step:
                context[step["save_as"]] = output["loan_id"]
        except BusinessMismatch as exc:
            entry.update(status="FAIL", error=str(exc))
            report["status"] = "FAIL"
        except ToolError as exc:
            entry.update(status="ERROR", error=str(exc))
            report["status"] = "ERROR"
        entry["elapsed_ms"] = round((perf_counter() - t0) * 1000, 3)
        entry["virtual_end"] = clock.seconds
        report["trace"].append(entry)
        if entry["status"] != "OK":
            break
    else:
        report["status"] = "PASS"
    report["polls"] = backend.polls
    report["virtual_seconds"] = clock.seconds
    report["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
    if report["status"] == "PASS":
        fact, next_step = "代码断言观察到已撤回状态", "无需进一步诊断"
    elif report["status"] == "FAIL":
        fact, next_step = "撤回响应为 200，但等待期限内查询状态未满足预期", "接真实系统后检查状态更新、任务执行与查询一致性"
    else:
        fact, next_step = "查询工具异常，无法完成最终状态验证", "先排查查询依赖和连接，再确认业务实际状态"
    report["diagnosis"] = {
        "method": "确定性规则摘要（非模型诊断）",
        "fact": fact,
        "root_cause": "未确认；注入设置仅为实验标签，不等于诊断证据" if report["status"] != "PASS" else "不适用",
        "next_step": next_step,
    }
    return report
