"""메모리 저장소: Notion 대신 쓰는 NotionStore와 같은 인터페이스. 테스트와 `sagak demo`(키 없이 체험)에서 쓴다."""
import copy

from .sync import OPEN_STATUSES


class MemoryStore:
    """Notion 대신 쓰는 메모리 저장소. NotionStore와 같은 인터페이스."""

    def __init__(self):
        self.customers, self.events, self.consultations = {}, {}, {}
        self.n = 0
        self.staff_names = []

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

    def get_customer(self, page_id):
        return copy.deepcopy(self.customers[page_id])

    def get_event(self, page_id):
        e = copy.deepcopy(self.events[page_id])
        e["consult_count"] = sum(1 for c in self.consultations.values() if c["event_id"] == page_id)
        return e

    def update_consultation(self, page_id, fields, event_id, sections):
        c = self.consultations[page_id]
        c.update(fields)
        c["event_id"] = event_id
        c["sections"] = c["sections"] + sections


    # 점검(sweep)과 직원 명단 — NotionStore와 같은 이름
    def staff(self):
        return list(self.staff_names)

    def all_events(self):
        return [self.get_event(i) for i in self.events]

    def append_event_note(self, page_id, heading, lines):
        self.events[page_id].setdefault("notes", []).append((heading, list(lines)))

