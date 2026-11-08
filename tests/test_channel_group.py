import unittest

from tests.helpers import load
from tests.test_sync import MemoryStore, run
from sagak.normalize import mask_numbers
from sagak.record import build_record

KAKAO_EXPORT = "박서준 님과의 상담\n저장한 날짜 : 2026-11-08 10:00:00\n2026-11-08 10:01:00, 박서준 : 문의드려요"


class GroupTest(unittest.TestCase):
    def test_group_without_kind_left_empty_and_asked(self):
        data = load("s01")
        data["event"]["product"] = "정원 프로포즈"
        r = build_record(data)
        self.assertIsNone(r["event"]["product"])
        self.assertEqual(r["event"]["theme"], "프로포즈")
        self.assertIn("희망 상품", r["consultation"]["needs_check"])
        self.assertTrue(any("정원패키지 꽃장식·정원패키지 풍선장식" in q for q in r["consultation"]["questions"]))

    def test_kind_given_maps(self):
        data = load("s01")
        data["event"]["product"] = "정원 풍선장식"
        r = build_record(data)
        self.assertEqual(r["event"]["product"], "정원패키지 풍선장식")
        self.assertNotIn("희망 상품", r["consultation"]["needs_check"])


class ChannelTest(unittest.TestCase):
    def test_recording_is_phone(self):
        data = load("s01")
        data["input_type"] = "녹음"
        self.assertEqual(build_record(data)["channel"], "전화상담")

    def test_channel_export_is_messenger(self):
        data = load("s02")
        data["input_type"] = "대화"
        data["transcript"] = KAKAO_EXPORT
        self.assertEqual(build_record(data)["channel"], "메신저채널")

    def test_picked_channel_must_be_known(self):
        data = load("s02")
        data["customer"] = dict(data.get("customer") or {}, channel="홈페이지문의")
        self.assertEqual(build_record(data)["channel"], "홈페이지문의")
        data["customer"]["channel"] = "B 블랙리스트"
        self.assertIsNone(build_record(data)["channel"])

    def test_plain_text_no_channel(self):
        self.assertIsNone(build_record(load("s02"))["channel"])

    def test_new_customer_gets_mark_and_existing_marks_kept(self):
        store = MemoryStore()
        run(store, "s01", lambda d: d.update(input_type="녹음"))
        c = next(iter(store.customers.values()))
        self.assertEqual(c["marks"], ["전화상담"])
        c["marks"] = ["B 블랙리스트", "전화상담"]
        out = run(store, "s02", lambda d: d.update(input_type="대화", transcript=KAKAO_EXPORT))
        self.assertEqual(c["marks"], ["B 블랙리스트", "전화상담", "메신저채널"])
        self.assertTrue(out["warnings"])


class FollowUpFlagTest(unittest.TestCase):
    def test_existing_event_fields_not_flagged(self):
        store = MemoryStore()
        run(store, "s01")  # 희망 일시·장소·테마가 채워진 이벤트

        def blank(d):
            d["event"] = {"theme": None, "venue": None, "desired_at": None, "desired_at_text": None}
        e = next(iter(store.events.values()))
        e["desired_at"] = "2026-12-12T19:00+09:00"
        out = run(store, "s02", blank)
        self.assertEqual(out["consultation"]["round"], 2)
        for label in ("희망 일시", "희망 장소", "이벤트 테마"):
            self.assertNotIn(label, out["needs_check"])


class MaskTest(unittest.TestCase):
    def test_spaced_account_and_url(self):
        self.assertEqual(mask_numbers("농협 302 0591 8134 21 입니다"), "농협 [번호 가림] 입니다")
        self.assertEqual(mask_numbers("https://blog.example.com/x/224451085462"), "https://blog.example.com/x/224451085462")
        self.assertEqual(mask_numbers("2026-11-05 20:57:30, 고객 : 010 5098 0975"), "2026-11-05 20:57:30, 고객 : 010 5098 0975")
        self.assertEqual(mask_numbers("110-123-456789 / https://a.b/1234567890"), "[번호 가림] / https://a.b/1234567890")


if __name__ == "__main__":
    unittest.main()


class RefundTest(unittest.TestCase):
    def test_refund_only_when_done(self):
        data = load("s01")
        data["event"]["refund_done"] = True
        data["event"]["refund_amount"] = 150000
        r = build_record(data)
        self.assertEqual((r["event"]["payment_status"], r["event"]["refund_amount"]), ("환불 완료", 150000))
        data["event"]["refund_done"] = None
        r = build_record(data)
        self.assertEqual((r["event"]["payment_status"], r["event"]["refund_amount"]), (None, None))

    def test_refund_replaces_deposit_paid(self):
        store = MemoryStore()
        run(store, "s01")
        e = next(iter(store.events.values()))
        e["payment_status"] = "예약금 입금"
        run(store, "s02", lambda d: d["event"].update(refund_done=True))
        self.assertEqual(e["payment_status"], "환불 완료")

    def test_human_no_refund_kept(self):
        store = MemoryStore()
        run(store, "s01")
        e = next(iter(store.events.values()))
        e["payment_status"] = "환불 없음"
        run(store, "s02", lambda d: d["event"].update(refund_done=True))
        self.assertEqual(e["payment_status"], "환불 없음")
