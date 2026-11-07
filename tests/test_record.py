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
        self.assertEqual(product_of("프리미엄 룸"), "호텔패키지 프리미엄")

    def test_unknown_product_is_empty(self):
        from sagak.record import product_of
        self.assertIsNone(product_of("요트 프로포즈"))


class StaffTest(unittest.TestCase):
    STAFF = ["박서준", "최하늘", "김도윤", "정유나"]

    def test_given_name_maps_to_full_name(self):
        from sagak.normalize import match_staff
        self.assertEqual(match_staff("서준", self.STAFF), "박서준")
        self.assertEqual(match_staff("서준님", self.STAFF), "박서준")
        self.assertEqual(match_staff("박 서준", self.STAFF), "박서준")

    def test_unknown_kept_as_is(self):
        from sagak.normalize import match_staff
        self.assertEqual(match_staff("춘자", self.STAFF), "춘자")
        self.assertEqual(match_staff("민", self.STAFF), "민")

    def test_ambiguous_kept_as_is(self):
        from sagak.normalize import match_staff
        self.assertEqual(match_staff("동현", ["김도윤", "이동현"]), "동현")


class MaskTest(unittest.TestCase):
    def test_account_and_card_masked_phone_kept(self):
        from sagak.normalize import mask_numbers
        t = "국민 123456-01-234567 로 입금, 카드 1234 5678 9012 3456, 연락처 010-1234-5678, 사무실 02-123-4567"
        out = mask_numbers(t)
        self.assertNotIn("123456-01-234567", out)
        self.assertNotIn("9012", out)
        self.assertIn("010-1234-5678", out)
        self.assertIn("02-123-4567", out)
        self.assertEqual(out.count("[번호 가림]"), 2)

    def test_chat_timestamps_untouched(self):
        from sagak.normalize import mask_numbers
        t = "2026-11-05 19:46:42, 박서준 : 예약금 입금 확인했습니다 2026-11-06"
        self.assertEqual(mask_numbers(t), t)

    def test_payment_talk_kept_in_record(self):
        data = load("s01")
        data["consultation"]["summary"] = "카드 결제 희망. 예약금 30% 안내, 계좌 110-123-456789 전달."
        data["transcript"] = "B: 신한 110-123-456789 로 예약금 보내 주세요"
        rec = build_record(data)
        self.assertIn("카드 결제 희망", rec["consultation"]["summary"])
        self.assertNotIn("110-123-456789", rec["consultation"]["summary"] + rec["transcript"])


class NameNoteTest(unittest.TestCase):
    def test_paren_is_not_part_of_name(self):
        data = load("s01")
        data["customer"]["name"] = "김민수(그랜드호텔)"
        rec = build_record(data)
        self.assertEqual(rec["customer"]["name"], "김민수")
        self.assertIn("접수 표기(괄호): 그랜드호텔", rec["event"]["request"])

    def test_only_paren_means_no_name(self):
        from sagak.normalize import split_name
        self.assertEqual(split_name("(그랜드호텔)"), (None, "그랜드호텔"))


class VenueTest(unittest.TestCase):
    def test_note_moves_to_questions_and_staff_url_kept(self):
        data = load("s01")
        data["event"]["venue"] = "용산 그랜드호텔 호텔 (정확한 호텔명 확인 필요)"
        data["event"]["venue_url"] = "https://naver.me/abcd1234"
        rec = build_record(data)
        self.assertEqual(rec["event"]["venue"], "용산 그랜드호텔 호텔")
        self.assertEqual(rec["event"]["map_url"], "https://naver.me/abcd1234")
        self.assertIn("희망 장소 확인: 정확한 호텔명 확인 필요", rec["consultation"]["questions"])

    def test_search_link_only_for_confirmed_exact_place(self):
        data = load("s01")
        data["event"].update(venue="용산 그랜드호텔 호텔", venue_exact=True, venue_url="https://example.com/x")
        rec = build_record(data)
        self.assertTrue(rec["event"]["map_url"].startswith("https://map.naver.com/p/search/"))
        data["event"].update(venue="부산 해운대 바다 보이는 실내", venue_exact=False)
        self.assertIsNone(build_record(data)["event"]["map_url"])

    def test_date_only_gets_midnight_and_check(self):
        data = load("s01")
        data["event"].update(desired_at=None, desired_date="2026-12-24", desired_at_text="크리스마스 이브")
        rec = build_record(data)
        self.assertEqual(rec["event"]["desired_at"], "2026-12-24T00:00:00+09:00")
        self.assertIn("희망 일시", rec["consultation"]["needs_check"])

    def test_deposit_recorded_and_flagged(self):
        data = load("s01")
        data["event"]["deposit"] = "100,000"
        rec = build_record(data)
        self.assertEqual(rec["event"]["deposit"], 100000)
        self.assertIn("예약금", rec["consultation"]["needs_check"])


if __name__ == "__main__":
    unittest.main()
