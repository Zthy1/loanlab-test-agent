import unittest

from loanlab.compare import compare


class ComparisonTests(unittest.TestCase):
    def test_offline_mode_never_fabricates_model_results(self):
        report = compare()
        self.assertEqual(0, report["model_calls"])
        self.assertEqual(0, report["agent_summary"]["evaluated"])
        self.assertEqual({"SKIPPED"}, {r["agent"]["status"] for r in report["rows"]})
        self.assertEqual(2, report["template_summary"]["supported_tasks_rejected"])

    def test_global_model_budget_is_enforced(self):
        class Fake:
            model = "scripted-test-double"
            calls = 0
            usage = {"prompt_tokens": 0, "completion_tokens": 0}
            def complete(self, messages, tools):
                self.calls += 1
                return {"content": "不支持"}
        report = compare(live=True, max_calls=2, client_factory=Fake)
        self.assertEqual(2, report["model_calls"])
        self.assertEqual(2, report["agent_summary"]["evaluated"])
        self.assertEqual(6, sum(r["agent"]["status"] == "SKIPPED" for r in report["rows"]))
