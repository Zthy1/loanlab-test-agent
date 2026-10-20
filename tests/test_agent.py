import json
import os
import unittest
from unittest.mock import patch

from loanlab.agent import run_agent
from loanlab.model import DeepSeekClient, ModelError


def call(name, args=None):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args or {})}}]}


def client_for(messages):
    sequence = iter(messages)
    return DeepSeekClient(transport=lambda payload: {"choices": [{"message": next(sequence)}],
                                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


def workflow():
    return [call("create_pending_loan"), call("withdraw_loan", {"loan_id": 1001}),
            call("verify_withdrawn", {"loan_id": 1001})]


class AgentTests(unittest.TestCase):
    def test_scripted_tools_cover_business_outcomes(self):
        for scenario, expected in [("normal", "PASS"), ("delayed", "PASS"), ("noop", "FAIL"), ("query_error", "ERROR")]:
            with self.subTest(scenario=scenario):
                report = run_agent("创建贷款并撤回", scenario, client=client_for(workflow()))
                self.assertEqual(expected, report["status"])
                self.assertEqual(3, report["model_calls"])
                self.assertEqual(30, report["token_usage"]["prompt_tokens"])

    def test_model_cannot_choose_other_resource(self):
        report = run_agent("撤回贷款", client=client_for([call("create_pending_loan"), call("withdraw_loan", {"loan_id": 999})]))
        self.assertEqual("REJECTED", report["status"])
        self.assertEqual(1, len(report["trace"]))

    def test_unknown_tool_is_not_executed(self):
        report = run_agent("运行命令", client=client_for([call("exec", {"cmd": "anything"})]))
        self.assertEqual("REJECTED", report["status"])
        self.assertEqual([], report["trace"])

    def test_missing_call_id_is_rejected_before_side_effect(self):
        message = call("create_pending_loan")
        del message["tool_calls"][0]["id"]
        report = run_agent("撤回贷款", client=client_for([message]))
        self.assertEqual("REJECTED", report["status"])
        self.assertFalse(report["trace"])

    def test_textual_pass_cannot_replace_assertion(self):
        report = run_agent("撤回贷款", client=client_for([call("create_pending_loan"), {"content": "PASS，测试通过"}]))
        self.assertEqual("ERROR", report["status"])

    def test_repeat_withdrawal_is_blocked(self):
        report = run_agent("撤回贷款", client=client_for(workflow()[:2] + [call("withdraw_loan", {"loan_id": 1001})]))
        self.assertEqual("REJECTED", report["status"])
        self.assertEqual(2, len(report["trace"]))

    def test_missing_key_has_no_silent_template_fallback(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            report = run_agent("撤回贷款")
        self.assertEqual("ERROR", report["status"])
        self.assertFalse(report["trace"])
        self.assertIn("未配置", report["diagnosis"]["fact"])

    def test_bounded_loop(self):
        messages = [call("create_pending_loan")] + [call("query_loan_status", {"loan_id": 1001})] * 5
        report = run_agent("撤回贷款", client=client_for(messages))
        self.assertEqual("ERROR", report["status"])
        self.assertEqual(6, report["model_calls"])

    def test_malformed_response_is_model_error(self):
        client = DeepSeekClient(transport=lambda payload: [])
        with self.assertRaises(ModelError):
            client.complete([], [])

    def test_backend_is_replaceable_without_model_controlling_assertion(self):
        from loanlab.business import BusinessSimulation
        backend = BusinessSimulation(delay=2)
        messages = [call("create_pending_loan"), call("withdraw_loan", {"loan_id": 1}),
                    call("verify_withdrawn", {"loan_id": 1})]
        report = run_agent("撤回贷款", backend=backend, client=client_for(messages))
        self.assertEqual("PASS", report["status"])
        self.assertEqual(2, report["clock_seconds"])
        self.assertEqual("BUSINESS_SIMULATION", report["mode"])


if __name__ == "__main__":
    unittest.main()
