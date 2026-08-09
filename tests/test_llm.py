import os
import unittest
from unittest.mock import Mock, patch

import llm


class LlmTests(unittest.TestCase):
    def test_bind_address_is_not_used_as_client_api_address(self):
        with patch.dict(os.environ, {"OLLAMA_HOST": "0.0.0.0"}, clear=False):
            self.assertEqual(llm._ollama_api_url(), "http://127.0.0.1:11434/api/chat")

    def test_chat_sends_schema_and_temperature_to_ollama(self):
        response = Mock()
        response.json.return_value = {"message": {"content": "{}"}}
        with patch("llm.requests.post", return_value=response) as post:
            llm.chat([], model="qwen2.5:14b", temperature=0.1, response_format={"type": "object"})
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["format"], {"type": "object"})
        self.assertEqual(payload["options"]["temperature"], 0.1)

    def test_chat_accepts_a_request_specific_timeout(self):
        response = Mock()
        response.json.return_value = {"message": {"content": "ok"}}
        with patch("llm.requests.post", return_value=response) as post:
            llm.chat([], timeout=45)
        self.assertEqual(post.call_args.kwargs["timeout"], 45)
