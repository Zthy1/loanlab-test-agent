import json
from pathlib import Path
import unittest

from loanlab.engine import TEMPLATE, TemplatePlanner, run_case


TASK = "创建一笔贷款，撤回申请并验证状态"


class EngineTests(unittest.TestCase):
    def test_normal_verifies_same_resource(self):
        report = run_case(TASK)
        self.assertEqual("PASS", report["status"])
        loan_id = report["trace"][0]["output"]["loan_id"]
        self.assertEqual(loan_id, report["trace"][1]["args"]["loan_id"])
        self.assertEqual(loan_id, report["evidence"]["loan_id"])

    def test_async_waits_and_stops_on_first_success(self):
        report = run_case(TASK, "delayed")
        self.assertEqual("PASS", report["status"])
        self.assertEqual([0, 1, 2], [p["virtual_second"] for p in report["polls"]])
        self.assertEqual(2, report["virtual_seconds"])

    def test_success_response_does_not_override_business_failure(self):
        report = run_case(TASK, "noop")
        self.assertEqual(200, report["trace"][1]["output"]["http_status"])
        self.assertEqual("FAIL", report["status"])
        self.assertEqual("SUBMITTED_AND_PENDING_APPROVAL", report["evidence"]["actual"])
        self.assertEqual(5, report["virtual_seconds"])
        self.assertEqual(1, sum(x["tool"] == "withdraw_loan" for x in report["trace"]))

    def test_query_error_is_not_a_confirmed_business_defect(self):
        report = run_case(TASK, "query_error")
        self.assertEqual("ERROR", report["status"])
        self.assertIn("未确认", report["diagnosis"]["root_cause"])
        self.assertEqual(1, len(report["polls"]))

    def test_runs_do_not_share_mutable_loan_state(self):
        run_case(TASK, "normal")
        self.assertEqual("FAIL", run_case(TASK, "noop")["status"])

    def test_unsupported_task_is_rejected_before_execution(self):
        report = run_case("删除所有用户")
        self.assertEqual("REJECTED", report["status"])
        self.assertEqual([], report["trace"])

    def test_model_like_plan_cannot_remove_or_change_assertions(self):
        class UntrustedPlanner:
            name = "unit test plan double; not a real model"

            def plan(self, task):
                plan = json.loads(TEMPLATE.read_text(encoding="utf-8"))
                plan["steps"][2] = {"tool": "declare_pass", "args": {}}
                return plan

        report = run_case(TASK, planner=UntrustedPlanner())
        self.assertEqual("REJECTED", report["status"])
        self.assertEqual([], report["trace"])

    def test_polling_does_not_exceed_deadline_for_uneven_interval(self):
        report = run_case(TASK, "noop", timeout_seconds=5, poll_interval=2)
        self.assertEqual([0, 2, 4, 5], [p["virtual_second"] for p in report["polls"]])
        self.assertEqual("FAIL", report["status"])

    def test_unknown_scenario_is_not_silently_mapped_to_normal(self):
        with self.assertRaises(ValueError):
            run_case(TASK, "unknown")


if __name__ == "__main__":
    unittest.main()
