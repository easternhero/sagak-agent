import io
import json
import unittest
import urllib.error

from sagak import naver

ENV = {"SAGAK_NAVER_CLIENT_ID": "id", "SAGAK_NAVER_CLIENT_SECRET": "secret"}


class Resp(io.BytesIO):
    def __init__(self, body=b"", url="", status=200):
        super().__init__(body)
        self._url, self.status = url, status

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(final=None, items=None, fail=False):
    def op(req, timeout=None):
        if fail:
            raise urllib.error.URLError("down")
        if "openapi.naver.com" in req.full_url:
            return Resp(json.dumps({"items": items or []}).encode())
        return Resp(b"", final or req.full_url)
    return op


def record(url, venue="그랜드호텔"):
    return {"event": {"map_url": url, "venue": venue}, "consultation": {"questions": []}}


class StaffLinkTest(unittest.TestCase):
    def test_short_link_resolving_to_place(self):
        r = record("https://naver.me/abcd")
        st = naver.verify(r, opener_for(final="https://map.naver.com/p/entry/place/1234567?c=15"))
        self.assertEqual((st, r["event"]["map_url"]), ("staff_ok", "https://naver.me/abcd"))

    def test_link_not_reaching_place_is_dropped(self):
        r = record("https://naver.me/broken")
        st = naver.verify(r, opener_for(final="https://map.naver.com/p/"))
        self.assertEqual(st, "staff_failed")
        self.assertIsNone(r["event"]["map_url"])
        self.assertTrue(r["consultation"]["questions"])

    def test_network_error_drops(self):
        r = record("https://naver.me/abcd")
        self.assertEqual(naver.verify(r, opener_for(fail=True)), "staff_failed")


class SearchLinkTest(unittest.TestCase):
    SEARCH = "https://map.naver.com/p/search/x"

    def test_no_key_no_link(self):
        r = record(self.SEARCH)
        self.assertEqual(naver.verify(r, opener_for(), env={}), "search_unsure")
        self.assertIsNone(r["event"]["map_url"])

    def test_single_match_links_name_and_address(self):
        items = [{"title": "<b>그랜드호텔</b>", "roadAddress": "서울 용산구 예시로 1"},
                 {"title": "그랜드호텔 뷔페", "roadAddress": "서울 용산구 예시로 1"}]
        r = record(self.SEARCH)
        self.assertEqual(naver.verify(r, opener_for(items=items), env=ENV), "search_ok")
        self.assertIn("%EC%98%88%EC%8B%9C%EB%A1%9C", r["event"]["map_url"])  # 주소가 들어간 검색

    def test_two_matches_unsure(self):
        items = [{"title": "그랜드호텔 용산점", "roadAddress": "a"}, {"title": "그랜드호텔 부산점", "roadAddress": "b"}]
        r = record(self.SEARCH)
        self.assertEqual(naver.verify(r, opener_for(items=items), env=ENV), "search_unsure")
        self.assertIsNone(r["event"]["map_url"])

    def test_address_venue(self):
        items = [{"title": "어떤빌딩", "roadAddress": "서울특별시 강남구 테헤란로 152"}]
        r = record(self.SEARCH, venue="강남구 테헤란로 152")
        self.assertEqual(naver.verify(r, opener_for(items=items), env=ENV), "search_ok")

    def test_nothing_found(self):
        r = record(self.SEARCH)
        self.assertEqual(naver.verify(r, opener_for(items=[]), env=ENV), "search_unsure")


if __name__ == "__main__":
    unittest.main()
