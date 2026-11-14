import json
import os
import tempfile
import unittest

from tests.helpers import load
from sagak import demo_mode
from sagak.notion import reviewer_cleanup_plan
from sagak.record import InputError, build_record


def page(pid, title_prop, title, consultant=None, **rels):
    props = {title_prop: {"type": "title", "title": [{"plain_text": title, "text": {"content": title}}]}}
    if consultant:
        props["상담자"] = {"type": "select", "select": {"name": consultant}}
    for name, ids in rels.items():
        props[name.replace("_", " ")] = {"type": "relation", "relation": [{"id": i} for i in ids]}
    return {"id": pid, "properties": props}


class DemoModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state.json")
        with open(self.state, "w", encoding="utf-8") as f:
            json.dump({"next": 4, "requests": {
                "3": {"user_id": "333", "status": "approved"}, "2": {"user_id": "222", "status": "pending"}}}, f)
        os.environ.update(SAGAK_DEMO="1", SAGAK_DEMO_STATE=self.state)

    def tearDown(self):
        for k in ("SAGAK_DEMO", "SAGAK_DEMO_STATE", "HERMES_SESSION_USER_ID", "HERMES_SESSION_ACTOR_ID"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_real_phone_refused_in_demo(self):
        with self.assertRaises(InputError) as e:
            build_record(load("s01"))  # 010-1000-1111
        self.assertEqual(e.exception.code, "DEMO_FAKE_PHONE")

    def test_reviewer_becomes_consultant(self):
        data = load("s01")
        data["caption"] = "김민수 / 010-0000-8003"
        os.environ["HERMES_SESSION_USER_ID"] = "333"
        self.assertEqual(build_record(data)["consultation"]["consultant"], "리뷰어 #3")
        os.environ["HERMES_SESSION_USER_ID"] = "222"  # 아직 승인 전
        self.assertNotEqual(build_record(data)["consultation"]["consultant"], "리뷰어 #2")
        os.environ.pop("SAGAK_DEMO")
        os.environ["HERMES_SESSION_USER_ID"] = "333"
        self.assertIsNone(demo_mode.reviewer_label())  # 데모가 아니면 표시 안 함

    def test_cleanup_keeps_seed_records(self):
        pages = {
            # 리뷰어만 만든 고객 c1 → 이벤트 e1 → 상담 s1
            "s1": page("s1", "제목", "리뷰어 상담", "리뷰어 #3", 이벤트=["e1"]),
            "e1": page("e1", "제목", "리뷰어 이벤트", 상담_이력=["s1"], 고객=["c1"]),
            "c1": page("c1", "의뢰인", "서도윤", 이벤트=["e1"]),
            # 기본 예시 고객 c2 → 이벤트 e2 (직원 상담 s2 + 리뷰어 상담 s3)
            "s2": page("s2", "제목", "직원 상담", "김하늘", 이벤트=["e2"]),
            "s3": page("s3", "제목", "리뷰어 덧붙임", "리뷰어 #4", 이벤트=["e2"]),
            "e2": page("e2", "제목", "기본 이벤트", 상담_이력=["s2", "s3"], 고객=["c2"]),
            "c2": page("c2", "의뢰인", "김민수", 이벤트=["e2"]),
        }
        out = reviewer_cleanup_plan([pages["s1"], pages["s2"], pages["s3"]], pages.__getitem__,
                                    demo_mode.is_reviewer_label)
        self.assertEqual(set(out["consultations"]), {"s1", "s3"})
        self.assertEqual(set(out["events"]), {"e1"})
        self.assertEqual(set(out["customers"]), {"c1"})


if __name__ == "__main__":
    unittest.main()
