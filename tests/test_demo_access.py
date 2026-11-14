import importlib.util
import os
import tempfile
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "sagak_demo_access", os.path.join(ROOT, "agent", "plugins", "sagak-demo-access", "__init__.py"))
access = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(access)


class FakeStore:
    def __init__(self):
        self.approved = set()

    def generate_code(self, platform, uid, name):
        return "CODE" + uid

    def approve_code(self, platform, code):
        self.approved.add(code[4:])
        return {"user_id": code[4:]}

    def is_approved(self, platform, uid):
        return uid in self.approved


class DemoAccessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SAGAK_DEMO_HOME"] = self.tmp.name
        with open(os.path.join(self.tmp.name, "config.yaml"), "w", encoding="utf-8") as f:
            f.write("platforms:\n  telegram:\n    extra:\n      allow_admin_from:\n        - '999'\n")
        self.sent = []

    def tearDown(self):
        os.environ.pop("SAGAK_DEMO_HOME", None)
        self.tmp.cleanup()

    def send(self, chat, text):
        self.sent.append((chat, text))
        return True

    def test_request_notifies_reviewer_and_admin_once(self):
        self.assertEqual(access.handle_unknown("111", "리뷰어", "111", now=1000, sender=self.send), "new")
        self.assertEqual([c for c, _ in self.sent], ["111", "999"])
        self.assertIn("/demo_approve 1", self.sent[1][1])
        self.assertEqual(access.handle_unknown("111", "리뷰어", "111", now=1100, sender=self.send), "quiet")
        self.assertEqual(access.handle_unknown("111", "리뷰어", "111", now=1000 + 601, sender=self.send), "remind")
        self.assertEqual(len(self.sent), 3)

    def test_approve_and_deny(self):
        access.handle_unknown("111", "가", "111", sender=self.send)
        access.handle_unknown("222", "나", "222", sender=self.send)
        store = FakeStore()
        self.assertIn("여러 개", access.decide("", True, store=store, sender=self.send))
        self.assertIn("승인했어요", access.decide("1", True, store=store, sender=self.send))
        self.assertTrue(store.is_approved("telegram", "111"))
        self.assertIn("승인됐어요", self.sent[-1][1])
        self.assertIn("거절했어요", access.decide("", False, store=store, sender=self.send))  # 남은 1건
        self.assertEqual(self.sent[-1][0], "222")
        self.assertIn("이미", access.decide("2", True, store=store, sender=self.send))
        self.assertIn("#1 승인", access.list_requests())

    def test_non_admin_refused(self):
        self.assertEqual(access.decide("1", True, admin_ok=False), "관리자만 쓸 수 있어요.")
        self.assertFalse(access._is_admin({"source": SimpleNamespace(user_id="111")}))
        self.assertTrue(access._is_admin({"source": SimpleNamespace(user_id="999")}))


if __name__ == "__main__":
    unittest.main()
