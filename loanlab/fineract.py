"""HTTP adapter for an explicitly configured, local Fineract test instance."""
import base64
from datetime import date
import json
import os
import ssl
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from uuid import uuid4

from .engine import ToolError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RealClock:
    def __init__(self):
        self.started = monotonic()

    @property
    def seconds(self):
        return monotonic() - self.started

    def wait(self, seconds):
        sleep(seconds)


class FineractHTTP:
    def __init__(self, *, base_url=None, username=None, password=None, tenant=None, opener=None):
        self.base = (base_url or os.environ.get("FINERACT_BASE_URL", "")).rstrip("/")
        parsed = urlsplit(self.base)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("仅允许显式配置的本机 Fineract 测试地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("地址不能包含凭据、查询或片段")
        if os.environ.get("FINERACT_TEST_ENV") != "YES":
            raise ValueError("必须设置 FINERACT_TEST_ENV=YES，确认这是隔离测试环境")
        username = username or os.environ.get("FINERACT_USERNAME", "")
        password = password or os.environ.get("FINERACT_PASSWORD", "")
        if not username or not password:
            raise ValueError("需要本机 FINERACT_USERNAME / FINERACT_PASSWORD")
        self.headers = {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode(),
                        "Fineract-Platform-TenantId": tenant or os.environ.get("FINERACT_TENANT", "default"),
                        "Content-Type": "application/json", "Accept": "application/json"}
        context = ssl.create_default_context(cafile=os.environ.get("FINERACT_CA_FILE") or None)
        self.opener = opener or build_opener(NoRedirect(), HTTPSHandler(context=context))
        self.trace = []

    def request(self, method, path, body=None):
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise ValueError("无效 API 路径")
        req = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                      headers=self.headers, method=method)
        started = monotonic()
        try:
            try:
                response = self.opener.open(req, timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                raw = response.read(1_000_001)
                status = response.code
            if len(raw) > 1_000_000:
                raise ToolError("Fineract 响应超限")
            data = json.loads(raw) if raw else {}
            if not isinstance(data, dict):
                raise ToolError("Fineract 响应应为 JSON 对象")
        except (URLError, OSError, ValueError):
            self.trace.append({"method": method, "path": path, "status": "TRANSPORT_ERROR"})
            raise ToolError("Fineract 连接、证书、超时或响应解析异常；写操作结果未知，禁止自动重试") from None
        self.trace.append({"method": method, "path": path, "status": status,
                           "elapsed_ms": round((monotonic() - started) * 1000, 2)})
        return {"http_status": status, "data": data}


STATUS = {100: "SUBMITTED_AND_PENDING_APPROVAL", 200: "APPROVED", 300: "ACTIVE", 400: "WITHDRAWN_BY_CLIENT"}


class FineractBackend:
    mode = "FINERACT_HTTP"

    def __init__(self, http=None):
        self.http = http or FineractHTTP()
        self.clock = RealClock()
        self.polls = []
        self.owned = set()
        self.resources = []
        self.client_id = None
        self.product_id = None
        # Explicit business date allows environments whose COB clock differs from today's date.
        self.day = os.environ.get("FINERACT_BUSINESS_DATE", date.today().isoformat())

    def _created(self, path, body, kind):
        result = self.http.request("POST", path, body)
        data = result["data"]
        if result["http_status"] not in {200, 201} or type(data.get("resourceId")) is not int:
            raise ToolError(f"Fineract 创建 {kind} 失败，HTTP {result['http_status']}")
        rid = data["resourceId"]
        self.resources.append({"kind": kind, "id": rid})
        return rid

    def prepare(self):
        suffix = uuid4().hex[:10]
        common = {"dateFormat": "yyyy-MM-dd", "locale": "en"}
        self.client_id = self._created("/clients", {**common, "officeId": 1, "legalFormId": 1,
            "firstname": "LoanLab", "lastname": suffix, "externalId": "loanlab-" + suffix,
            "active": True, "activationDate": self.day}, "clients")
        product_file = os.environ.get("FINERACT_PRODUCT_FILE")
        if product_file:
            from pathlib import Path
            product = json.loads(Path(product_file).read_text(encoding="utf-8"))
            product.update(name="LoanLab-" + suffix, shortName=suffix[:4])
            self.product_id = self._created("/loanproducts", product, "loanproducts")
        else:
            try:
                self.product_id = int(os.environ["FINERACT_PRODUCT_ID"])
            except (KeyError, ValueError):
                raise ToolError("需要已审核的 FINERACT_PRODUCT_FILE 或兼容的 FINERACT_PRODUCT_ID") from None

    def create(self, principal=5000):
        body = {"clientId": self.client_id, "productId": self.product_id, "loanType": "individual",
                "submittedOnDate": self.day, "expectedDisbursementDate": self.day,
                "principal": principal, "numberOfRepayments": 5, "repaymentEvery": 1,
                "repaymentFrequencyType": 2, "loanTermFrequency": 5, "loanTermFrequencyType": 2,
                "interestRatePerPeriod": 0, "amortizationType": 1, "interestType": 0,
                "interestCalculationPeriodType": 1, "transactionProcessingStrategyCode": "mifos-standard-strategy",
                "dateFormat": "yyyy-MM-dd", "locale": "en"}
        rid = self._created("/loans", body, "loans")
        self.owned.add(rid)
        return {"loan_id": rid, "status": self.query(rid)}

    def _owned(self, loan_id):
        if type(loan_id) is not int or loan_id not in self.owned:
            raise ToolError("拒绝操作非本次运行创建的贷款")

    def query(self, loan_id):
        self._owned(loan_id)
        result = self.http.request("GET", f"/loans/{loan_id}")
        try:
            state = STATUS[result["data"]["status"]["id"]]
            if result["http_status"] != 200:
                raise KeyError()
        except (KeyError, TypeError):
            raise ToolError(f"无法解析贷款状态，HTTP {result['http_status']}") from None
        self.polls.append({"second": round(self.clock.seconds, 3), "loan_id": loan_id, "status": state})
        return state

    def command(self, loan_id, command):
        self._owned(loan_id)
        if command not in {"approve", "withdrawnByApplicant"}:
            raise ToolError("不支持的业务命令")
        field = "approvedOnDate" if command == "approve" else "withdrawnOnDate"
        result = self.http.request("POST", f"/loans/{loan_id}?command={command}",
                                   {field: self.day, "locale": "en", "dateFormat": "yyyy-MM-dd"})
        if result["http_status"] in {401, 429} or result["http_status"] >= 500:
            raise ToolError(f"Fineract 认证、限流或服务异常，HTTP {result['http_status']}")
        # Only transport status enters reports, never raw API bodies with client information.
        return {"http_status": result["http_status"], "loan_id": loan_id}

    def withdraw(self, loan_id):
        return self.command(loan_id, "withdrawnByApplicant")

    def approve(self, loan_id):
        return self.command(loan_id, "approve")

    def cleanup(self):
        results = []
        for item in reversed(self.resources):
            if item["kind"] == "loanproducts":
                results.append({**item, "cleanup": "RETAINED", "reason": "产品采用测试专用名称，保留供排查"})
                continue
            try:
                response = self.http.request("DELETE", f"/{item['kind']}/{item['id']}")
                results.append({**item, "cleanup": "DELETED" if response["http_status"] in {200, 204} else "RETAINED",
                                "http_status": response["http_status"]})
            except ToolError:
                results.append({**item, "cleanup": "UNKNOWN"})
        return results
