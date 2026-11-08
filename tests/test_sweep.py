import unittest
from datetime import date, datetime

from sagak import sweep

TODAY = date(2026, 11, 20)


def ev(**kw):
    base = {"id": "e1", "url": "u", "title": "홍길동 · 프로포즈 · 11/21", "status": "상담진행중",
            "payment_status": None, "desired_at": "2026-11-21T15:00:00.000+09:00", "confirmed_at": None,
            "desired_at_text": "21일 3시"}
    base.update(kw)
    return base


class CheckTest(unittest.TestCase):
    def test_deposit_fills_confirmed_and_plans(self):
        fields, why, _ = sweep.check(ev(payment_status="예약금 입금"), TODAY)
        self.assertEqual(fields, {"confirmed_at": "2026-11-21T15:00+09:00", "status": "이벤트진행예정"})
        self.assertEqual(len(why), 2)

    def test_utc_value_kept_in_kst(self):
        fields, _, _ = sweep.check(ev(payment_status="예약금 입금", desired_at="2026-11-21T06:00:00.000Z",
                                      status="이벤트진행예정"), TODAY)
        self.assertEqual(fields, {"confirmed_at": "2026-11-21T15:00+09:00"})

    def test_date_only_desired(self):
        fields, _, _ = sweep.check(ev(payment_status="예약금 입금", desired_at="2026-11-21", status="이벤트진행예정"), TODAY)
        self.assertEqual(fields["confirmed_at"], "2026-11-21")

    def test_existing_confirmed_not_touched(self):
        fields, _, _ = sweep.check(ev(payment_status="예약금 입금", confirmed_at="2026-11-22T12:00:00.000+09:00",
                                      status="이벤트진행예정"), TODAY)
        self.assertEqual(fields, {})

    def test_no_deposit_no_change(self):
        self.assertEqual(sweep.check(ev(), TODAY)[0], {})

    def test_past_confirmed_completes(self):
        fields, why, _ = sweep.check(ev(status="이벤트진행예정", confirmed_at="2026-11-19T18:00:00.000+09:00"), TODAY)
        self.assertEqual(fields, {"status": "이벤트완료"})
        self.assertIn("지남", why[0])

    def test_today_not_completed(self):
        fields, _, _ = sweep.check(ev(status="이벤트진행예정", confirmed_at="2026-11-20T09:00:00.000+09:00"), TODAY)
        self.assertEqual(fields, {})

    def test_cancelled_untouched(self):
        fields, _, _ = sweep.check(ev(status="이벤트취소", payment_status="예약금 입금",
                                      confirmed_at="2026-11-01T18:00:00.000+09:00"), TODAY)
        self.assertEqual(fields, {})

    def test_midnight_with_time_in_text_warns(self):
        _, _, warns = sweep.check(ev(desired_at="2026-12-24T00:00:00.000+09:00", desired_at_text="12월24일 오후 4시"), TODAY)
        self.assertEqual(len(warns), 1)
        self.assertIn("오후 4시", warns[0])

    def test_midnight_without_time_no_warning(self):
        _, _, warns = sweep.check(ev(desired_at="2026-12-24T00:00:00.000+09:00", desired_at_text="12월 24일"), TODAY)
        self.assertEqual(warns, [])


class Store:
    def __init__(self, events):
        self.events, self.updates, self.notes = events, [], []

    def all_events(self):
        return self.events

    def update_event(self, page_id, fields):
        self.updates.append((page_id, fields))

    def append_event_note(self, page_id, heading, lines):
        self.notes.append((page_id, heading, lines))


class RunTest(unittest.TestCase):
    def test_run_updates_and_notes(self):
        s = Store([ev(payment_status="예약금 입금"), ev(id="e2")])
        out = sweep.run(s, now=datetime(2026, 11, 20, 10, 0, tzinfo=sweep.KST))
        self.assertEqual([c["id"] for c in out["changes"]], ["e1"])
        self.assertEqual(s.updates[0][0], "e1")
        self.assertTrue(s.notes[0][1].startswith("자동 정리 (11/20"))

    def test_dry_run_writes_nothing(self):
        s = Store([ev(payment_status="예약금 입금")])
        out = sweep.run(s, now=datetime(2026, 11, 20, tzinfo=sweep.KST), dry_run=True)
        self.assertEqual(len(out["changes"]), 1)
        self.assertEqual((s.updates, s.notes), ([], []))


if __name__ == "__main__":
    unittest.main()
