import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from loanlab import server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.previous_reports = server.REPORTS
        server.REPORTS = Path(cls.temp.name)
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()
        server.REPORTS = cls.previous_reports
        cls.temp.cleanup()

    def test_assets_load(self):
        for asset in ("/", "/app.js", "/style.css"):
            with urlopen(self.url + asset) as response:
                self.assertEqual(200, response.status)
                self.assertTrue(response.read())

    def test_run_is_saved_and_can_be_retrieved(self):
        data = json.dumps({"task": "创建贷款并撤回", "scenario": "noop"}).encode()
        request = Request(self.url + "/api/run", data=data, headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            report = json.load(response)
        self.assertEqual("FAIL", report["status"])
        with urlopen(self.url + "/api/runs/" + report["run_id"]) as response:
            self.assertEqual(report, json.load(response))

    def test_cross_origin_submission_is_blocked(self):
        request = Request(self.url + "/api/run", data=b"{}", headers={
            "Content-Type": "application/json", "Origin": "https://external.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(403, caught.exception.code)

    def test_report_path_is_restricted(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url + "/api/runs/README.md")
        self.assertEqual(404, caught.exception.code)

    def test_model_route_reports_missing_key_without_fallback(self):
        data = json.dumps({"task": "创建贷款并撤回", "planner": "deepseek"}).encode()
        request = Request(self.url + "/api/run", data=data, headers={"Content-Type": "application/json"})
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}), urlopen(request) as response:
            report = json.load(response)
        self.assertEqual("ERROR", report["status"])
        self.assertEqual([], report["trace"])

    def test_unknown_planner_is_rejected(self):
        data = json.dumps({"task": "创建贷款并撤回", "planner": "unknown"}).encode()
        request = Request(self.url + "/api/run", data=data, headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(400, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
