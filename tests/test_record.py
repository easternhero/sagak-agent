import unittest

from tests.helpers import load  # noqa: F401  (sys.path 설정)
from sagak.normalize import normalize_phone, parse_caption
from sagak.record import InputError, build_record


class NormalizeTest(unittest.TestCase):
    def test_phone_formats(self):
        for raw in ("01000001111", "010-0000-1111", "010 0000 1111", "010.0000.1111", "연락처: 010-0000-1111"):
            self.assertEqual(normalize_phone(raw), "010-0000-1111")
        self.assertIsNone(normalize_phone("02-123-4567"))

    def test_caption_with_company(self):
        c = parse_caption("이지은 / 하늘상사 / 010-0000-2222 / jieun@example.com")
        self.assertEqual(c, {"name": "이지은", "phone": "010-0000-2222", "email": "jieun@example.com", "company": "하늘상사"})

    def test_caption_with_labels_and_newlines(self):
        c = parse_caption("성함: 김민수\n연락처: 01000001111\n이메일: minsu@example.com")
        self.assertEqual((c["name"], c["phone"], c["email"], c["company"]), ("김민수", "010-0000-1111", "minsu@example.com", None))


class RecordTest(unittest.TestCase):
    def test_s01_new_personal(self):
        r = build_record(load("s01"))
        self.assertEqual(r["customer"]["name"], "김민수")
        self.assertEqual(r["customer"]["customer_type"], "개인")
        self.assertEqual(r["event"]["budget"], 1000000)
        self.assertIsNone(r["event"]["desired_at"])  # 시각이 없으니 추측하지 않음
        self.assertIn("희망 일시", r["consultation"]["needs_check"])
        self.assertNotIn("예산", r["consultation"]["needs_check"])

    def test_s03_company_is_business(self):
        r = build_record(load("s03"))
        self.assertEqual(r["customer"]["company"], "하늘상사")
        self.assertEqual(r["customer"]["customer_type"], "기업")
        self.assertEqual(r["event"]["desired_at"], "2026-12-19T18:00:00+09:00")
        self.assertEqual(r["consultation"]["needs_check"], ["예산"])

    def test_s04_missing_values_flagged_not_guessed(self):
        r = build_record(load("s04"))
        self.assertIsNone(r["event"]["budget"])
        self.assertIsNone(r["event"]["desired_at"])
        self.assertIn("희망 일시", r["consultation"]["needs_check"])
        self.assertIn("예산", r["consultation"]["needs_check"])

    def test_s05_no_customer_info(self):
        with self.assertRaises(InputError) as ctx:
            build_record(load("s05"))
        self.assertEqual(ctx.exception.code, "MISSING_CUSTOMER")

    def test_invalid_values_are_dropped(self):
        data = load("s01")
        data["event"]["theme"] = "결혼식"
        data["event"]["budget"] = "백만원"
        data["event"]["desired_at"] = "12월 12일"
        r = build_record(data)
        self.assertIsNone(r["event"]["theme"])
        self.assertIsNone(r["event"]["budget"])
        self.assertIsNone(r["event"]["desired_at"])
        for label in ("이벤트 테마", "예산", "희망 일시"):
            self.assertIn(label, r["consultation"]["needs_check"])

    def test_default_next_contact(self):
        r = build_record(load("s02"))
        self.assertEqual(r["consultation"]["next_contact"], "미정")


if __name__ == "__main__":
    unittest.main()
