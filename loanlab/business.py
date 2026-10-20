"""Loan lifecycle regression suite, runnable against simulation or Fineract HTTP."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .engine import ToolError, VirtualClock
from .fineract import FineractBackend


class BusinessSimulation:
    mode = "BUSINESS_SIMULATION"

    def __init__(self, *, delay=0, noop=False):
        self.clock = VirtualClock()
        self.loans = {}
        self.polls = []
        self.delay, self.noop = delay, noop

    def prepare(self):
        pass

    def create(self):
        rid = len(self.loans) + 1
        self.loans[rid] = {"state": "SUBMITTED_AND_PENDING_APPROVAL", "requested": None}
        return {"loan_id": rid, "status": self.query(rid)}

    def query(self, rid):
        if type(rid) is not int or rid not in self.loans:
            raise ToolError("拒绝操作非本轮创建的贷款")
        loan = self.loans[rid]
        if loan["requested"] is not None and not self.noop and self.clock.seconds - loan["requested"] >= self.delay:
            loan["state"] = "WITHDRAWN_BY_CLIENT"
        self.polls.append({"second": self.clock.seconds, "loan_id": rid, "status": loan["state"]})
        return loan["state"]

    def approve(self, rid):
        if self.query(rid) != "SUBMITTED_AND_PENDING_APPROVAL":
            return {"http_status": 403}
        self.loans[rid]["state"] = "APPROVED"
        return {"http_status": 200}

    def withdraw(self, rid):
        if self.query(rid) != "SUBMITTED_AND_PENDING_APPROVAL":
            return {"http_status": 403}
        self.loans[rid]["requested"] = self.clock.seconds
        return {"http_status": 200}

    def cleanup(self):
        self.loans.clear()
        return [{"cleanup": "CLEARED", "kind": "memory"}]


def wait_state(backend, rid, expected, budget=5):
    deadline = backend.clock.seconds + budget
    while True:
        state = backend.query(rid)
        if state == expected or backend.clock.seconds >= deadline:
            return {"expected": expected, "actual": state, "matched": state == expected}
        backend.clock.wait(min(0.5, deadline - backend.clock.seconds))


def run_suite(backend=None):
    backend = backend or BusinessSimulation()
    report = {"run_id": uuid4().hex, "backend": backend.mode, "cases": [], "cleanup": [],
              "note": "资源守卫验证的是 Agent 边界，不等于服务端用户权限验证"}
    started = perf_counter()

    def record(name, operation):
        t0 = perf_counter()
        evidence = {}
        try:
            operation(evidence)
            status = "PASS"
        except AssertionError as exc:
            status = "FAIL"
            evidence["assertion"] = str(exc)
        except ToolError as exc:
            status = "ERROR"
            evidence["error"] = str(exc)
        report["cases"].append({"name": name, "status": status, "evidence": evidence,
                                "elapsed_ms": round((perf_counter() - t0) * 1000, 2)})

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def pending(e):
        rid = backend.create()["loan_id"]
        e.update(loan_id=rid, before=backend.query(rid))
        require(e["before"] == "SUBMITTED_AND_PENDING_APPROVAL", "前置状态必须为待审批")
        e["response"] = backend.withdraw(rid)
        require(e["response"]["http_status"] in {200, 201}, "撤回请求应受理")
        e["verification"] = wait_state(backend, rid, "WITHDRAWN_BY_CLIENT")
        require(e["verification"]["matched"], "期限内未观察到已撤回状态")

    def approved(e):
        rid = backend.create()["loan_id"]
        e["loan_id"] = rid
        e["approval"] = backend.approve(rid)
        require(e["approval"]["http_status"] in {200, 201}, "审批前置操作未成功")
        require(wait_state(backend, rid, "APPROVED")["matched"], "审批前置状态未生效")
        e["response"] = backend.withdraw(rid)
        e["after"] = backend.query(rid)
        require(e["response"]["http_status"] in {400, 403, 409, 422}, "非法状态撤回应被拒绝")
        require(e["after"] == "APPROVED", "失败操作不得改变已审批状态")

    def repeated(e):
        rid = backend.create()["loan_id"]
        e["loan_id"] = rid
        e["first"] = backend.withdraw(rid)
        require(e["first"]["http_status"] in {200, 201}, "首次撤回应受理")
        require(wait_state(backend, rid, "WITHDRAWN_BY_CLIENT")["matched"], "首次撤回未生效")
        e["second"] = backend.withdraw(rid)
        e["after"] = backend.query(rid)
        require(e["second"]["http_status"] in {400, 403, 409, 422}, "终态重复撤回应被拒绝（当前 Fineract 契约）")
        require(e["after"] == "WITHDRAWN_BY_CLIENT", "重复请求不得破坏终态")

    def isolation(e):
        a, b = backend.create()["loan_id"], backend.create()["loan_id"]
        e.update(loan_a=a, loan_b=b)
        require(a != b, "两份数据必须使用不同贷款 ID")
        response = backend.withdraw(a)
        require(response["http_status"] in {200, 201}, "A 撤回请求应受理")
        e["a"] = wait_state(backend, a, "WITHDRAWN_BY_CLIENT")
        e["b"] = backend.query(b)
        require(e["a"]["matched"] and e["b"] == "SUBMITTED_AND_PENDING_APPROVAL", "A 的操作不应修改 B")

    try:
        backend.prepare()
        for name, operation in [("pending_withdrawal", pending), ("approved_withdrawal_rejected", approved),
                                ("repeated_withdrawal_rejected", repeated), ("loan_state_isolation", isolation)]:
            record(name, operation)
    except (ToolError, ValueError) as exc:
        report["setup_error"] = str(exc)
    finally:
        report["cleanup"] = backend.cleanup()
    report["cleanup_status"] = "COMPLETE" if all(r["cleanup"] in {"DELETED", "CLEARED"} for r in report["cleanup"]) else "PARTIAL"
    report["requests"] = getattr(getattr(backend, "http", None), "trace", [])
    report["polls"] = backend.polls
    report["elapsed_ms"] = round((perf_counter() - started) * 1000, 2)
    report["status"] = "ERROR" if "setup_error" in report else (
        "ERROR" if any(c["status"] == "ERROR" for c in report["cases"]) else
        "FAIL" if any(c["status"] == "FAIL" for c in report["cases"]) else "PASS")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["simulation", "fineract"], default="simulation")
    parser.add_argument("--output", type=Path, default=Path("reports/business-suite.json"))
    args = parser.parse_args()
    try:
        backend = FineractBackend() if args.backend == "fineract" else BusinessSimulation()
        report = run_suite(backend)
    except (ValueError, ToolError) as exc:
        report = {"status": "ERROR", "setup_error": str(exc), "backend": args.backend}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
