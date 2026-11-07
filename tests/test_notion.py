import io
import json
import unittest

from tests.helpers import load  # noqa: F401
from sagak.notion import (CONSULT_PROPS, CUSTOMER_PROPS, NotionStore, TEXT_LIMIT, from_properties,
                          to_blocks, to_properties)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, req, timeout=None):
        self.calls.append((req.get_method(), req.full_url, json.loads(req.data) if req.data else None))
        return FakeResponse(json.dumps(self.responses.pop(0)).encode())


class NotionTest(unittest.TestCase):
    def test_none_values_are_not_sent(self):
        props = to_properties({"name": "김민수", "phone": "010-0000-1111", "email": None, "company": ""}, CUSTOMER_PROPS)
        self.assertEqual(set(props), {"의뢰인", "연락처"})

    def test_long_text_is_chunked(self):
        props = to_properties({"summary": "가" * (TEXT_LIMIT + 5), "questions": ["질문1", "질문2"]}, CONSULT_PROPS)
        self.assertEqual(len(props["상담 내역"]["rich_text"]), 2)
        self.assertEqual(props["추가 질문"]["rich_text"][0]["text"]["content"], "질문1\n질문2")

    def test_parse_page(self):
        page = {"id": "p1", "url": "u", "properties": {
            "의뢰인": {"type": "title", "title": [{"plain_text": "김민수"}]},
            "연락처": {"type": "phone_number", "phone_number": "010-0000-1111"},
            "고객 구분": {"type": "select", "select": None}}}
        c = from_properties(page, CUSTOMER_PROPS)
        self.assertEqual((c["name"], c["phone"], c["customer_type"]), ("김민수", "010-0000-1111", None))

    def test_blocks_are_capped(self):
        blocks = to_blocks([("전사 원문", ["줄{}".format(i) for i in range(300)])])
        self.assertLessEqual(len(blocks), 95)

    def test_requests(self):
        opener = FakeOpener([
            {"results": []},
            {"id": "e1", "url": "https://notion.so/e1"},
        ])
        store = NotionStore("tok", "dbc", "dbe", "dbs", opener=opener)
        self.assertEqual(store.find_customers("010-0000-1111"), [])
        store.create_event({"title": "t", "status": "상담진행중", "budget": None}, "c9")
        (m1, url1, body1), (m2, url2, body2) = opener.calls
        self.assertEqual((m1, url1), ("POST", "https://api.notion.com/v1/databases/dbc/query"))
        self.assertEqual(body1["filter"]["phone_number"]["equals"], "010-0000-1111")
        self.assertEqual(body2["parent"], {"database_id": "dbe"})
        self.assertEqual(body2["properties"]["고객"], {"relation": [{"id": "c9"}]})
        self.assertNotIn("예상 금액", body2["properties"])


class MapLinkPropTest(unittest.TestCase):
    def test_map_url_and_deposit_props(self):
        from sagak.notion import EVENT_PROPS, to_properties
        props = to_properties({"map_url": "https://naver.me/x", "deposit": 100000}, EVENT_PROPS)
        self.assertEqual(props["지도 링크"], {"url": "https://naver.me/x"})
        self.assertEqual(props["예약금액"], {"number": 100000})

class DateFormatTest(unittest.TestCase):
    def test_minute_datetime_sent_with_seconds(self):
        from sagak.notion import to_property
        self.assertEqual(to_property("date", "2026-12-12T19:00+09:00"), {"date": {"start": "2026-12-12T19:00:00+09:00"}})
        self.assertEqual(to_property("date", "2026-12-12"), {"date": {"start": "2026-12-12"}})


if __name__ == "__main__":
    unittest.main()
