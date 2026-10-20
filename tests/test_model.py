import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from loanlab.model import DeepSeekClient, ModelError


class ModelTests(unittest.TestCase):
    def test_http_contract_and_usage(self):
        body = {"choices": [{"message": {"role": "assistant", "content": "unsupported"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-placeholder"}), \
             patch("loanlab.model.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as opened:
            client = DeepSeekClient()
            message = client.complete([{"role": "user", "content": "task"}], [])
        request = opened.call_args.args[0]
        self.assertEqual("https://api.deepseek.com/chat/completions", request.full_url)
        payload = json.loads(request.data)
        self.assertEqual("deepseek-flash", payload["model"])
        self.assertEqual({"type": "disabled"}, payload["thinking"])
        self.assertEqual(12, client.usage["prompt_tokens"])
        self.assertEqual("unsupported", message["content"])

    def test_provider_error_body_is_not_reported(self):
        error = HTTPError("https://api.deepseek.com", 429, "sensitive provider body", {}, None)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-placeholder"}), \
             patch("loanlab.model.urlopen", side_effect=error):
            with self.assertRaises(ModelError) as caught:
                DeepSeekClient().complete([], [])
        self.assertIn("429", str(caught.exception))
        self.assertNotIn("sensitive", str(caught.exception))

    def test_call_budget(self):
        client = DeepSeekClient(transport=lambda payload: {"choices": [{"message": {}}]})
        for _ in range(6):
            client.complete([], [])
        with self.assertRaises(ModelError):
            client.complete([], [])


if __name__ == "__main__":
    unittest.main()
