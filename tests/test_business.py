import unittest

from loanlab.business import BusinessSimulation, run_suite, wait_state


class BusinessTests(unittest.TestCase):
    def test_all_lifecycle_contracts(self):
        report = run_suite()
        self.assertEqual("PASS", report["status"])
        self.assertEqual(4, len(report["cases"]))
        self.assertEqual({"PASS"}, {r["status"] for r in report["cases"]})

    def test_noop_mutant_is_detected(self):
        report = run_suite(BusinessSimulation(noop=True))
        self.assertEqual("FAIL", report["status"])
        self.assertEqual("FAIL", report["cases"][0]["status"])

    def test_illegal_state_mutant_is_detected(self):
        class Broken(BusinessSimulation):
            def withdraw(self, rid):
                self.loans[rid]["requested"] = self.clock.seconds
                return {"http_status": 200}
        report = run_suite(Broken())
        self.assertEqual("FAIL", report["cases"][1]["status"])
        self.assertEqual("FAIL", report["cases"][2]["status"])

    def test_delayed_state_converges(self):
        self.assertEqual("PASS", run_suite(BusinessSimulation(delay=2))["status"])

    def test_exact_deadline_is_observed(self):
        backend = BusinessSimulation(delay=5)
        rid = backend.create()["loan_id"]
        backend.withdraw(rid)
        self.assertTrue(wait_state(backend, rid, "WITHDRAWN_BY_CLIENT")["matched"])
        self.assertEqual(5, backend.clock.seconds)

    def test_cleanup_runs_after_setup_error(self):
        from loanlab.engine import ToolError
        class Broken(BusinessSimulation):
            def prepare(self):
                raise ToolError("setup failed")
        report = run_suite(Broken())
        self.assertEqual("ERROR", report["status"])
        self.assertTrue(report["cleanup"])
