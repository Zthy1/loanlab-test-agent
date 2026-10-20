"""DeepSeek Chat Completions client. Credentials never enter reports."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, *, transport=None):
        self.key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = "deepseek-flash"
        self.transport = transport
        self.calls = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.served_models = set()

    def complete(self, messages, tools):
        if self.calls >= 6:
            raise ModelError("已达到 6 次模型调用上限")
        self.calls += 1
        payload = {"model": self.model, "messages": messages, "tools": tools,
                   "tool_choice": "auto", "stream": False, "temperature": 0,
                   "max_tokens": 1200, "thinking": {"type": "disabled"}}
        if self.transport:
            data = self.transport(payload)
        else:
            if not self.key:
                raise ModelError("未配置 DEEPSEEK_API_KEY；未调用模型，未回退为模板")
            request = Request("https://api.deepseek.com/chat/completions",
                              data=json.dumps(payload).encode(), headers={
                                  "Content-Type": "application/json", "Authorization": "Bearer " + self.key})
            try:
                with urlopen(request, timeout=40) as response:
                    raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ModelError("模型响应超过大小限制")
                data = json.loads(raw)
            except HTTPError as exc:
                # Never return raw provider bodies, headers or credentials.
                raise ModelError(f"DeepSeek HTTP {exc.code}；请检查配置或额度") from None
            except (URLError, TimeoutError, OSError, ValueError):
                raise ModelError("DeepSeek 连接、超时或响应解析失败") from None
        try:
            if isinstance(data.get("model"), str):
                self.served_models.add(data["model"])
            usage = data.get("usage", {})
            for key in self.usage:
                self.usage[key] += int(usage.get(key, 0))
            message = data["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError()
            return message
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise ModelError("模型响应结构无效") from None
