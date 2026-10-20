"""Explicit live DeepSeek + local Fineract demonstration."""
import json
import os
from pathlib import Path

from .agent import run_agent
from .fineract import FineractBackend


def main():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("先在本机配置 DEEPSEEK_API_KEY；未进行模型或业务写操作")
    backend = FineractBackend()
    report = {"mode": "FINERACT_HTTP", "status": "ERROR"}
    try:
        backend.prepare()
        report = run_agent("创建一笔待审批贷款，撤回申请并验证最终状态", backend=backend)
    finally:
        report["cleanup"] = backend.cleanup()
        report["requests"] = backend.http.trace
        path = Path("reports/live-agent.json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["status"], "reports/live-agent.json")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
