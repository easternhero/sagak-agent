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



class CheckLabelTest(unittest.TestCase):
    def test_unknown_labels_become_questions(self):
        data = load("s02")
        data["consultation"]["needs_check"] = ["예산", "빔프로젝터 추가 확정 여부"]
        r = build_record(data)
        self.assertNotIn("빔프로젝터 추가 확정 여부", r["consultation"]["needs_check"])
        self.assertIn("빔프로젝터 추가 확정 여부 확인 필요", r["consultation"]["questions"])
        self.assertIn("예산", r["consultation"]["needs_check"])



class YearTest(unittest.TestCase):
    def test_past_date_without_year_moves_to_next_year(self):
        data = load("s03")
        data["consulted_at"] = "2026-11-20T10:00:00+09:00"
        data["event"]["desired_at"] = "2026-01-05T18:00:00"
        data["event"]["desired_at_text"] = "1월 5일 저녁 6시"
        self.assertEqual(build_record(data)["event"]["desired_at"], "2027-01-05T18:00:00+09:00")

    def test_explicit_year_is_kept(self):
        data = load("s03")
        data["event"]["desired_at"] = "2026-01-05T18:00:00"
        data["event"]["desired_at_text"] = "2026년 1월 5일"
        self.assertEqual(build_record(data)["event"]["desired_at"], "2026-01-05T18:00:00+09:00")

    def test_future_date_unchanged(self):
        self.assertEqual(build_record(load("s03"))["event"]["desired_at"], "2026-12-19T18:00:00+09:00")



class CustomerTypeTest(unittest.TestCase):
    def test_default_personal(self):
        self.assertEqual(build_record(load("s04"))["customer"]["customer_type"], "개인")

    def test_company_means_business(self):
        data = load("s04")
        data["customer"] = {"customer_type": "개인", "company": "하늘상사"}
        self.assertEqual(build_record(data)["customer"]["customer_type"], "기업")


class ProductTest(unittest.TestCase):
    def test_guide_names_map_to_product(self):
        from sagak.record import product_of
        self.assertEqual(product_of("갤러리 프로포즈"), "갤러리패키지")
        self.assertEqual(product_of("호텔/신혼집 프로포즈"), "호텔패키지")
        self.assertEqual(product_of("레스토랑 프로포즈"), "레스토랑패키지")
        self.assertEqual(product_of("출장 렌탈 패키지"), "출장 렌탈")
        self.assertEqual(product_of("레스토랑패키지"), "레스토랑패키지")

    def test_unknown_product_is_empty(self):
        from sagak.record import product_of
        self.assertIsNone(product_of("요트 프로포즈"))


if __name__ == "__main__":
    unittest.main()
