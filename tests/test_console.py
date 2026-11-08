import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tests.helpers import load  # noqa: F401
from sagak.console import make_handler


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = os.path.join(self.dir.name, ".env")
        with open(self.env, "w") as f:
            f.write("TELEGRAM_ALLOWED_USERS=1,2\n")
        os.environ["SAGAK_STATE_DIR"] = self.dir.name
        self.calls = []

        def fake_send(**kw):
            self.calls.append(kw)
            return {"sent": 0 if kw["dry_run"] else 2, "lines": []}

        self.notes = []

        def fake_notify(text, to="others", dry_run=False, env_path=None):
            self.notes.append({"text": text, "to": to, "dry_run": dry_run})
            return {"sent": 0 if dry_run else 1, "count": 1, "to": to}

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("tok", 0, self.env, send=fake_send))
        self.port = self.httpd.server_address[1]
        # Host 확인용 포트를 실제 포트로 다시 만든다
        self.httpd.RequestHandlerClass = make_handler("tok", self.port, self.env, send=fake_send, notify=fake_notify)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        del os.environ["SAGAK_STATE_DIR"]
        self.dir.cleanup()

    def req(self, path, body=None, token="tok", host=None):
        r = urllib.request.Request("http://127.0.0.1:{}{}".format(self.port, path),
                                   data=json.dumps(body).encode() if body is not None else None,
                                   headers={"X-Sagak-Token": token, "Content-Type": "application/json"})
        if host:
            r.add_header("Host", host)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_page_has_token_and_state_lists_unsent(self):
        code, html = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn('const TOKEN="tok"', html)
        code, body = self.req("/api/state")
        data = json.loads(body)
        self.assertEqual(data["users"], 2)
        self.assertTrue(data["lines"])  # 레포 CHANGES.md의 안 보낸 줄
        self.assertIn("admin", data)
        self.assertIn("others", data)

    def test_send_requires_token(self):
        self.assertEqual(self.req("/api/send", {"text": "- 안내"}, token="bad")[0], 403)
        self.assertEqual(self.calls, [])

    def test_rejects_foreign_host(self):
        self.assertEqual(self.req("/api/state", host="evil.example:{}".format(self.port))[0], 403)

    def test_send_and_dry_run(self):
        code, body = self.req("/api/send", {"text": "- 안내", "dry_run": True})
        self.assertEqual(json.loads(body)["sent"], 0)
        code, body = self.req("/api/send", {"text": "- 안내", "to": "admin"})
        self.assertEqual(json.loads(body)["sent"], 2)
        self.assertEqual([c["dry_run"] for c in self.calls], [True, False])
        self.assertEqual(self.calls[1]["to"], "admin")
        self.assertEqual(self.calls[1]["text"], "- 안내")

    def test_notify(self):
        self.assertEqual(self.req("/api/notify", {"text": "부탁"}, token="bad")[0], 403)
        code, body = self.req("/api/notify", {"text": "부탁드려요", "dry_run": True})
        self.assertEqual(json.loads(body)["count"], 1)
        code, body = self.req("/api/notify", {"text": "부탁드려요"})
        self.assertEqual(json.loads(body)["sent"], 1)
        self.assertEqual(self.notes[1], {"text": "부탁드려요", "to": "others", "dry_run": False})
        self.assertEqual(self.calls, [])  # 변경 안내 발송과 무관
        code, html = self.req("/")
        self.assertIn("요청·공지 보내기", html)


if __name__ == "__main__":
    unittest.main()
