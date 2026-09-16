# -*- coding: utf-8 -*-
"""模型列表与最小模型调用：只连接本地临时 HTTP mock。"""
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import app
import connection
import core

SECRET = "models-test-secret-never-real"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def send_json(self, status, data, headers=None):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.server.seen.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path == "/v1/models":
            self.send_json(200, {"data": [{"id": "m-a"}, {"id": "m-b"}, {"id": "m-a"}]})
        elif self.path == "/alt/models":
            self.send_json(200, {"models": ["x", {"id": "y"}]})
        elif self.path == "/redirect/models":
            self.send_response(302); self.send_header("Location", "/v1/models"); self.send_header("Content-Length", "0"); self.end_headers()
        elif self.path == "/large/models":
            self.send_response(200); self.send_header("Content-Length", str(connection.MAX_RESPONSE_BYTES + 10)); self.end_headers()
        elif self.path == "/bad/models":
            raw = b"<html>not json</html>"; self.send_response(200); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        else:
            self.send_json(404, {"error": {"message": "missing"}})

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        self.server.seen.append(("POST", self.path, self.headers.get("Authorization"), body))
        if self.path == "/v1/chat/completions":
            self.send_json(200, {"id": "chatcmpl-test", "choices": [{"message": {"content": "OK"}}]})
        elif self.path == "/v1/responses":
            self.send_json(200, {"id": "resp-test", "output": [{"type": "message"}]})
        elif self.path == "/unauth/responses":
            self.send_json(401, {"error": {"message": "bad token " + SECRET}})
        else:
            self.send_json(404, {"error": {"message": "missing"}})


class ModelNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.seen = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(2)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="models_")
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"MODEL_TEST_KEY": SECRET})
        self.env.start(); self.addCleanup(self.env.stop)
        self.form = {"model": "m-a", "model_provider": "mock", "base_url": self.base + "/v1",
                     "env_key": "MODEL_TEST_KEY", "wire_api": "responses"}
        self.server.seen.clear()

    def test_http_only_localhost(self):
        self.assertEqual(connection.validate_endpoint(self.base).scheme, "http")
        with self.assertRaises(core.CoreError):
            connection.validate_endpoint("http://example.com/v1")

    def test_endpoint_join_no_duplicate_v1(self):
        self.assertEqual(connection.models_target(self.form)[1], "/v1/models")
        self.assertEqual(connection.connection_target(self.form)[1], "/v1/responses")
        self.assertEqual(connection.models_target(dict(self.form, base_url=self.base))[1], "/models")

    def test_models_openai_format_deduplicated(self):
        r = connection.fetch_models(self.form)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["models"], ["m-a", "m-b"])
        self.assertIn("不等于", r["message"])
        self.assertEqual(self.server.seen[0][:2], ("GET", "/v1/models"))
        self.assertEqual(self.server.seen[0][2], "Bearer " + SECRET)

    def test_models_known_alternate_format(self):
        r = connection.fetch_models(dict(self.form, base_url=self.base + "/alt"))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["models"], ["x", "y"])

    def test_models_redirect_large_and_invalid_json_fail_safe(self):
        for prefix, word in (("redirect", "跳转"), ("large", "过大"), ("bad", "JSON")):
            with self.subTest(prefix=prefix):
                r = connection.fetch_models(dict(self.form, base_url=self.base + "/" + prefix))
                self.assertFalse(r["ok"]); self.assertIn(word, r["message"])
                self.assertNotIn(SECRET, json.dumps(r, ensure_ascii=False))

    def test_chat_and_responses_real_structure(self):
        chat = connection.test_model_call(dict(self.form, wire_api="chat"))
        responses = connection.test_model_call(self.form)
        self.assertTrue(chat["ok"], chat); self.assertEqual(chat["protocol"], "chat")
        self.assertTrue(responses["ok"], responses); self.assertEqual(responses["protocol"], "responses")
        posts = [x for x in self.server.seen if x[0] == "POST"]
        self.assertEqual(posts[0][1], "/v1/chat/completions")
        self.assertEqual(json.loads(posts[0][3])["messages"][0]["content"], "Reply OK.")
        self.assertEqual(posts[1][1], "/v1/responses")
        self.assertEqual(json.loads(posts[1][3])["input"], "Reply OK.")

    def test_401_message_scrubs_secret(self):
        r = connection.test_model_call(dict(self.form, base_url=self.base + "/unauth"))
        self.assertFalse(r["ok"]); self.assertEqual(r["status"], 401)
        self.assertNotIn(SECRET, json.dumps(r, ensure_ascii=False))

    def test_api_token_binds_operation_and_uses_unsaved_secret_once(self):
        api = app.Api(core.Paths(self.tmp.name))
        with patch.dict(os.environ, {}, clear=True):
            prepared = api.prepare_models(self.form, SECRET)
            self.assertTrue(prepared["ok"], prepared)
            self.assertNotIn(SECRET, json.dumps(prepared, ensure_ascii=False))
            self.form["base_url"] = "http://127.0.0.1:1/changed"
            result = api.execute_network(prepared["token"], True)
            self.assertTrue(result["ok"], result)
            again = api.execute_network(prepared["token"], True)
            self.assertFalse(again["ok"])
            call = api.prepare_model_call(dict(self.form, base_url=self.base + "/v1"), SECRET)
            self.assertTrue(call["ok"])
            self.assertTrue(api.execute_network(call["token"], True)["ok"])

    def test_timeout_is_stubbed_and_redacted(self):
        with patch("connection._request", side_effect=core.CoreError("连接或响应等待超时（12 秒），未自动重试。")):
            r = connection.fetch_models(self.form)
        self.assertFalse(r["ok"]); self.assertIn("超时", r["message"])
        self.assertNotIn(SECRET, json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
