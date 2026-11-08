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

    def test_transcript_not_in_page_blocks(self):
        blocks = to_blocks([("근거", ["a"]), ("전사 원문", ["줄{}".format(i) for i in range(300)])])
        self.assertEqual(len(blocks), 2)  # 전사 원문은 따로 붙인다 (D42)

    def test_full_transcript_appended_in_batches(self):
        lines = ["[{:02d}:00] A: ".format(i % 60) + "가" * 300 for i in range(1000)]  # 약 30만 자
        opener = FakeOpener([{"id": "c1", "url": "u"}, {"results": [{"id": "t1"}]}] + [{"results": []}] * 3)
        store = NotionStore("tok", "dbc", "dbe", "dbs", opener=opener)
        store.create_consultation({"title": "t"}, None, [("근거", ["x"]), ("전사 원문", lines)])
        head = opener.calls[1][2]["children"][0]["heading_3"]
        self.assertTrue(head["is_toggleable"])
        self.assertIn("1000줄", head["rich_text"][0]["text"]["content"])
        appended = [c for c in opener.calls[2:]]
        self.assertTrue(all(u.endswith("/blocks/t1/children") for _, u, _ in appended))
        text = "\n".join(b["paragraph"]["rich_text"][0]["text"]["content"] for _, _, body in appended for b in body["children"])
        self.assertEqual(text.splitlines(), lines)  # 한 줄도 빠지지 않음
        self.assertTrue(all(len(body["children"]) <= 100 for _, _, body in appended))

    def test_evidence_clip_under_bullet(self):
        blocks = to_blocks([("근거", [("희망 일시 — “3시”", "up1")])])
        child = blocks[1]["bulleted_list_item"]["children"][0]
        self.assertEqual(child["audio"]["file_upload"]["id"], "up1")

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
        self.assertNotIn("고객 예산", body2["properties"])


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
