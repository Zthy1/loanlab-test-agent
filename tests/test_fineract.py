from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch

from loanlab.business import run_suite
from loanlab.engine import ToolError
from loanlab.fineract import FineractHTTP, FineractBackend


class ContractAPI(BaseHTTPRequestHandler):
    """HTTP contract fixture, deliberately NOT an Apache Fineract instance."""
    loans = {}

    def log_message(self, *args):
        pass

    def respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if self.path == "/api/clients":
            return self.respond(200, {"resourceId": 71})
        if self.path == "/api/loans":
            assert data["clientId"] == 71 and data["productId"] == 10
            rid = len(self.loans) + 100
            self.loans[rid] = 100
            return self.respond(200, {"resourceId": rid})
        rid = int(self.path.split("/")[-1].split("?")[0])
        if self.loans[rid] != 100:
            return self.respond(403, {"errors": []})
        self.loans[rid] = 200 if self.path.endswith("command=approve") else 400
        self.respond(200, {"resourceId": rid})

    def do_GET(self):
        rid = int(self.path.split("/")[-1])
        self.respond(200, {"id": rid, "status": {"id": self.loans[rid]}})

    def do_DELETE(self):
        self.respond(200, {})


class FineractContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ContractAPI)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_http_adapter_lifecycle_and_redacted_report(self):
        ContractAPI.loans = {}
        with patch.dict("os.environ", {"FINERACT_TEST_ENV": "YES", "FINERACT_PRODUCT_ID": "10"}):
            http = FineractHTTP(base_url=f"http://127.0.0.1:{self.server.server_port}/api",
                                username="contract-user", password="contract-secret")
            report = run_suite(FineractBackend(http))
        self.assertEqual("PASS", report["status"])
        self.assertEqual(4, len(report["cases"]))
        self.assertIn("DELETE", {r["method"] for r in report["requests"]})
        self.assertNotIn("contract-secret", json.dumps(report))
        self.assertNotIn("Authorization", json.dumps(report))

    def test_external_target_is_rejected(self):
        with self.assertRaises(ValueError):
            FineractHTTP(base_url="https://bank.example/api", username="a", password="b")

    def test_test_environment_must_be_explicit(self):
        with patch.dict("os.environ", {"FINERACT_TEST_ENV": ""}):
            with self.assertRaises(ValueError):
                FineractHTTP(base_url="http://localhost:8443/api", username="a", password="b")

    def test_unknown_resource_is_blocked_before_request(self):
        backend = FineractBackend(http=object())
        with self.assertRaises(ToolError):
            backend.withdraw(999)
