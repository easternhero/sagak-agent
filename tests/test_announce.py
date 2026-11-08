import io
import json
import os
import tempfile
import unittest

from tests.helpers import load  # noqa: F401
from sagak import announce as an


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class AnnounceTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        os.environ["SAGAK_STATE_DIR"] = d
        self.changes = os.path.join(d, "CHANGES.md")
        self.env = os.path.join(d, ".env")
        with open(self.env, "w") as f:
            f.write("TELEGRAM_BOT_TOKEN=secret\nTELEGRAM_ALLOWED_USERS=111,222\n")
        self.write(["새 기능 B", "새 기능 A"])
        self.sent = []

    def tearDown(self):
        del os.environ["SAGAK_STATE_DIR"]
        self.dir.cleanup()

    def write(self, lines):
        with open(self.changes, "w", encoding="utf-8") as f:
            f.write("# 안내\n\n## 날짜\n" + "".join("- " + l + "\n" for l in lines))

    def opener(self, req, timeout=None):
        self.sent.append(json.loads(req.data.decode("utf-8")))
        return FakeResp(b'{"ok": true}')

    def run_announce(self, **kw):
        return an.announce(env_path=self.env, opener=self.opener, changes=self.changes, **kw)

    def test_sends_new_button_to_everyone_once(self):
        out = self.run_announce()
        self.assertEqual(out["sent"], 2)
        self.assertEqual([m["chat_id"] for m in self.sent], ["111", "222"])
        self.assertEqual(self.sent[0]["reply_markup"]["keyboard"], [[{"text": "/new"}]])
        self.assertIn("새 기능 B", self.sent[0]["text"])
        self.assertEqual(self.run_announce()["sent"], 0)  # 이미 보낸 줄은 다시 안 보냄

    def test_only_newer_lines_after_update(self):
        self.run_announce()
        self.write(["새 기능 C", "새 기능 B", "새 기능 A"])
        self.sent.clear()
        out = self.run_announce()
        self.assertEqual(out["lines"], ["새 기능 C"])
        self.assertNotIn("새 기능 B", self.sent[0]["text"])

    def test_restart_button_only_for_admin(self):
        self.write(["설정 바뀜 [restart]"])
        self.run_announce()
        self.assertEqual(self.sent[0]["reply_markup"]["keyboard"], [[{"text": "/restart"}], [{"text": "/new"}]])
        self.assertEqual(self.sent[1]["reply_markup"]["keyboard"], [[{"text": "/new"}]])
        self.assertNotIn("[restart]", self.sent[1]["text"])

    def test_dry_run_sends_nothing_and_keeps_state(self):
        out = self.run_announce(dry_run=True)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(out["preview"]), 2)
        self.assertEqual(self.run_announce()["sent"], 2)

    def test_edited_text_sent_and_changes_marked(self):
        out = self.run_announce(text="- 고친 안내 하나\n• 고친 안내 둘 [restart]\n")
        self.assertEqual(out["lines"], ["고친 안내 하나", "고친 안내 둘 [restart]"])
        self.assertIn("고친 안내 하나", self.sent[0]["text"])
        self.assertEqual(self.sent[0]["reply_markup"]["keyboard"][0], [{"text": "/restart"}])
        self.sent.clear()
        self.assertEqual(self.run_announce()["sent"], 0)  # CHANGES의 새 줄은 보낸 것으로 처리됨

    def test_admin_first_then_others(self):
        out = self.run_announce(to="admin")
        self.assertEqual([m["chat_id"] for m in self.sent], ["111"])
        self.assertEqual(an.pending_for(self.env, self.changes),
                         {"admin": [], "others": ["새 기능 B", "새 기능 A"]})
        self.sent.clear()
        self.run_announce(to="others")
        self.assertEqual([m["chat_id"] for m in self.sent], ["222"])
        self.assertEqual(an.pending_for(self.env, self.changes), {"admin": [], "others": []})

    def test_old_state_format_counts_for_both(self):
        with open(os.path.join(self.dir.name, "sagak_announced.json"), "w", encoding="utf-8") as f:
            json.dump({"top": "새 기능 A"}, f, ensure_ascii=False)
        self.assertEqual(an.pending_for(self.env, self.changes), {"admin": ["새 기능 B"], "others": ["새 기능 B"]})

    def test_repo_changes_file_parses(self):
        self.assertTrue(an.read_lines())


if __name__ == "__main__":
    unittest.main()


class NotifyTest(unittest.TestCase):
    def test_notify_others_plain(self):
        import json as _j
        from sagak import announce as A
        sent = []

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": true}'

        def op(req, timeout=None):
            sent.append(_j.loads(req.data))
            return R()
        with tempfile.TemporaryDirectory() as d:
            env = os.path.join(d, ".env")
            with open(env, "w") as f:
                f.write("TELEGRAM_BOT_TOKEN=t\nTELEGRAM_ALLOWED_USERS=1,2,3\n")
            out = A.notify("링크 부탁드려요", to="others", env_path=env, opener=op)
        self.assertEqual(out["sent"], 2)
        self.assertEqual([m["chat_id"] for m in sent], ["2", "3"])
        self.assertNotIn("reply_markup", sent[0])
