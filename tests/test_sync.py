import copy
import unittest

from tests.helpers import load
from sagak.record import build_record
from sagak.sync import OPEN_STATUSES, apply, plan


class MemoryStore:
    """Notion 대신 쓰는 메모리 저장소. NotionStore와 같은 인터페이스."""

    def __init__(self):
        self.customers, self.events, self.consultations = {}, {}, {}
        self.n = 0

    def _id(self, prefix):
        self.n += 1
        return "{}{}".format(prefix, self.n)

    def find_customers(self, phone):
        return [copy.deepcopy(c) for c in self.customers.values() if c.get("phone") == phone]

    def open_events(self, customer_id):
        out = []
        for e in self.events.values():
            if e["customer_id"] == customer_id and e.get("status") in OPEN_STATUSES:
                e = copy.deepcopy(e)
                e["consult_count"] = sum(1 for c in self.consultations.values() if c["event_id"] == e["id"])
                out.append(e)
        return out

    def create_customer(self, fields):
        i = self._id("c")
        self.customers[i] = dict(fields, id=i, url="notion://" + i)
        return {"id": i, "url": "notion://" + i}

    def update_customer(self, page_id, fields):
        self.customers[page_id].update(fields)

    def create_event(self, fields, customer_id):
        i = self._id("e")
        self.events[i] = dict(fields, id=i, url="notion://" + i, customer_id=customer_id)
        return {"id": i, "url": "notion://" + i}

    def update_event(self, page_id, fields):
        self.events[page_id].update(fields)

    def create_consultation(self, fields, event_id, sections):
        i = self._id("s")
        self.consultations[i] = dict(fields, id=i, event_id=event_id, sections=sections)
        return {"id": i, "url": "notion://" + i}


def run(store, name, mutate=None):
    data = load(name)
    if mutate:
        mutate(data)
    record = build_record(data)
    return apply(record, plan(record, store), store)


class SyncTest(unittest.TestCase):
    def test_s01_creates_customer_event_consultation(self):
        store = MemoryStore()
        out = run(store, "s01")
        self.assertEqual((out["customer"]["action"], out["event"]["action"]), ("create", "create"))
        self.assertEqual(out["consultation"]["round"], 1)
        self.assertEqual(out["review"], "확인 대기")
        event = next(iter(store.events.values()))
        self.assertEqual(event["status"], "상담진행중")
        self.assertEqual(event["requested_on"], "2026-11-05")
        self.assertEqual(event["title"], "김민수 · 프로포즈 · 12월 12일 저녁")
        consult = next(iter(store.consultations.values()))
        self.assertEqual(consult["title"], "11/05 김민수 · 1차 상담")
        headings = [h for h, _ in consult["sections"]]
        self.assertEqual(headings, ["근거", "고객에게 물어볼 것", "전사 원문"])

    def test_s02_links_as_second_round_without_overwriting(self):
        store = MemoryStore()
        run(store, "s01")
        out = run(store, "s02")
        self.assertEqual((out["customer"]["action"], out["event"]["action"]), ("link", "link"))
        self.assertEqual(out["consultation"]["round"], 2)
        self.assertEqual(len(store.customers), 1)
        self.assertEqual(len(store.events), 1)
        event = next(iter(store.events.values()))
        self.assertEqual(event["venue"], "부산, 실내")           # 덮어쓰지 않음
        self.assertEqual(event["budget"], 1000000)              # 새 입력에 없다고 지우지 않음
        self.assertEqual([d["field"] for d in out["diffs"]], ["희망 장소"])
        self.assertIn("기존 정보와 다름", out["needs_check"])
        consult = list(store.consultations.values())[-1]
        self.assertIn("기존 정보와 다른 내용 (덮어쓰지 않음)", [h for h, _ in consult["sections"]])

    def test_empty_existing_value_is_filled(self):
        store = MemoryStore()
        run(store, "s01")
        run(store, "s02", lambda d: d["event"].update(product="호텔패키지"))
        self.assertEqual(next(iter(store.events.values()))["product"], "호텔패키지")

    def test_same_phone_different_name_needs_person(self):
        store = MemoryStore()
        run(store, "s01")
        out = run(store, "s02", lambda d: d.update(caption="김민지 / 010-0000-1111"))
        self.assertIsNone(out["customer"])
        self.assertIsNone(out["event"])
        self.assertIsNone(out["consultation"]["round"])
        self.assertEqual(out["review"], "고객 확인 필요")
        self.assertIn("고객 연결", out["needs_check"])
        self.assertEqual(len(store.customers), 1)
        self.assertEqual(out["consultation"]["title"], "11/06 김민지 · 연결 확인 필요")

    def test_two_open_events_needs_person(self):
        store = MemoryStore()
        run(store, "s01")
        cid = next(iter(store.customers))
        store.create_event({"title": "다른 의뢰", "status": "추후연락"}, cid)
        out = run(store, "s02")
        self.assertEqual(out["customer"]["action"], "link")
        self.assertIsNone(out["event"])
        self.assertEqual(out["review"], "고객 확인 필요")
        self.assertEqual(len(out["candidates"]), 2)

    def test_finished_event_starts_new_event(self):
        store = MemoryStore()
        run(store, "s01")
        next(iter(store.events.values()))["status"] = "이벤트완료"
        out = run(store, "s02")
        self.assertEqual(out["event"]["action"], "create")
        self.assertEqual(out["consultation"]["round"], 1)
        self.assertEqual(len(store.events), 2)

    def test_s03_business_customer(self):
        store = MemoryStore()
        run(store, "s03")
        cust = next(iter(store.customers.values()))
        self.assertEqual((cust["customer_type"], cust["company"]), ("기업", "하늘상사"))
        event = next(iter(store.events.values()))
        self.assertEqual(event["title"], "이지은 · 기타 · 12/19")


if __name__ == "__main__":
    unittest.main()
