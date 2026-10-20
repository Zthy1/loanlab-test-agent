"""Local-only demo UI and report API. Python standard library only."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from .engine import SCENARIOS, run_case
from .agent import run_agent


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "demo-runs"
WEB = Path(__file__).with_name("web")


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200, content_type="application/json; charset=utf-8"):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", "/app.js", "/style.css"}:
            name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[path]
            content_type = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
            return self.send((WEB / name).read_bytes(), content_type=content_type + "; charset=utf-8")
        if path == "/api/config":
            return self.send({"mode": "LOCAL_SIMULATION", "model_configured": bool(os.environ.get("DEEPSEEK_API_KEY")), "fineract_connected": False,
                              "scenarios": SCENARIOS})
        if path == "/api/runs":
            items = []
            for file in sorted(REPORTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
                data = json.loads(file.read_text(encoding="utf-8"))
                items.append({key: data[key] for key in ("run_id", "created_at", "status", "scenario_label", "elapsed_ms")})
            return self.send(items)
        match = re.fullmatch(r"/api/runs/([a-f0-9]{32})", path)
        if match:
            file = REPORTS / (match.group(1) + ".json")
            if file.is_file():
                return self.send(file.read_bytes())
        self.send({"error": "Not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/run":
            return self.send({"error": "Not found"}, 404)
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if origin and origin not in allowed:
            return self.send({"error": "不允许跨站提交"}, 403)
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.send({"error": "需要 JSON 请求"}, 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("请求大小无效")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) - {"task", "scenario", "planner"}:
                raise ValueError("请求字段无效")
            scenario = data.get("scenario", "normal")
            if not isinstance(scenario, str):
                raise ValueError("场景必须是字符串")
            planner = data.get("planner", "template")
            if planner not in ("template", "deepseek"):
                raise ValueError("未知规划模式")
            report = (run_agent if planner == "deepseek" else run_case)(data.get("task"), scenario)
        except (ValueError, TypeError) as exc:
            return self.send({"error": str(exc)}, 400)
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / (report["run_id"] + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.send(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"LoanLab: http://127.0.0.1:{args.port} (simulated business backend)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
