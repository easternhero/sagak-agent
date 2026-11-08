import io
import json
import unittest
import urllib.error
import urllib.parse

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


calls = []


def opener_for(final=None, items=None, fail=False):
    def op(req, timeout=None):
        if fail:
            raise urllib.error.URLError("down")
        if "apigw.ntruss.com" in req.full_url or "openapi.naver.com" in req.full_url:
            calls.append(dict(req.header_items()))
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

    def test_same_building_candidates(self):
        items = [{"title": "<b>그랜드호텔</b> 라운지", "roadAddress": "서울 용산구 예시로 1"},
                 {"title": "<b>그랜드호텔</b> 뷔페", "roadAddress": "서울 용산구 예시로 1"}]
        r = record(self.SEARCH)
        self.assertEqual(naver.verify(r, opener_for(items=items), env=ENV), "search_ok")
        self.assertIn("%EC%98%88%EC%8B%9C%EB%A1%9C", r["event"]["map_url"])

    def test_same_building_with_floor_suffixes(self):
        items = [{"title": "<b>예시 호텔</b> 키친", "roadAddress": "서울특별시 용산구 예시로 322 로비층"},
                 {"title": "<b>예시 호텔</b> 갤러리", "roadAddress": "서울특별시 용산구 예시로 322 예시호텔 로비1층"},
                 {"title": "<b>예시호텔</b> 델리", "roadAddress": "서울특별시 용산구 예시로 322"}]
        r = record(self.SEARCH, venue="예시 호텔")
        self.assertEqual(naver.verify(r, opener_for(items=items), env=ENV), "search_ok")
        self.assertTrue(r["event"]["map_url"].endswith("%EC%98%88%EC%8B%9C%EB%A1%9C%20322"))

    def test_base_address(self):
        self.assertEqual(naver.base_address({"roadAddress": "서울특별시 용산구 예시로 322 로비층"}), "서울특별시 용산구 예시로 322")
        self.assertEqual(naver.base_address({"roadAddress": "", "address": "서울특별시 용산구 예시동 747-7 2층"}), "서울특별시 용산구 예시동 747-7")

    def test_address_venue(self):
        items = [{"title": "어떤빌딩", "roadAddress": "서울특별시 강남구 테헤란로 152"}]
        r = record(self.SEARCH, venue="강남구 테헤란로 152")
        self.assertEqual(naver.verify(r, opener_for(items=items), env=ENV), "search_ok")

    def test_hub_headers_default_and_legacy_option(self):
        calls.clear()
        naver.search_places("그랜드호텔", opener_for(items=[]), env=ENV)
        self.assertIn("X-ncp-apigw-api-key-id", calls[-1])
        naver.search_places("그랜드호텔", opener_for(items=[]),
                            env=dict(ENV, SAGAK_NAVER_LOCAL_URL="https://openapi.naver.com/v1/search/local.json"))
        self.assertIn("X-naver-client-id", calls[-1])

    def test_nothing_found(self):
        r = record(self.SEARCH)
        self.assertEqual(naver.verify(r, opener_for(items=[]), env=ENV), "search_unsure")


if __name__ == "__main__":
    unittest.main()


class RecheckTest(unittest.TestCase):
    class Store:
        def __init__(self, events):
            self.events, self.set = events, []

        def all_events(self):
            return self.events

        def set_map_url(self, pid, url):
            self.set.append((pid, url))

    def test_recheck(self):
        hotel = [{"title": "그랜드호텔", "roadAddress": "서울 용산구 예시로 1 2층"}]
        store = self.Store([
            {"id": "a", "title": "A", "venue": "그랜드호텔", "map_url": "https://map.naver.com/p/search/x", "status": "상담진행중"},
            {"id": "b", "title": "B", "venue": "없는곳", "map_url": "https://map.naver.com/p/search/y", "status": "상담진행중"},
            {"id": "c", "title": "C", "venue": "그랜드호텔", "map_url": "https://map.naver.com/p/search/z", "status": "이벤트취소"},
        ])

        def op(req, timeout=None):
            q = req.full_url
            return Resp(json.dumps({"items": hotel if "%EA%B7%B8%EB%9E%9C%EB%93%9C" in q else []}).encode())
        out = naver.recheck(store, opener=op, env=ENV)
        self.assertEqual([o["title"] for o in out], ["A", "B"])
        self.assertTrue(store.set[0][1].endswith("%EC%98%88%EC%8B%9C%EB%A1%9C%201"))
        self.assertEqual(store.set[1], ("b", None))

    def test_name_dot_address_split(self):
        items = [{"title": "어떤카페", "roadAddress": "서울 강남구 예시로77길 34"}]

        def op(req, timeout=None):
            return Resp(json.dumps({"items": items if "77" in urllib.parse.unquote(req.full_url) else []}).encode())
        link = naver.confirmed_search_link("없는카페 · 서울 강남구 예시로77길 34", op, ENV)
        self.assertIsNotNone(link)


class ProductPlaceTest(unittest.TestCase):
    def test_product_place_link_used(self):
        from tests.helpers import load
        from sagak.record import build_record
        data = load("s01")
        data["event"]["product"] = "레스토랑 프로포즈"
        data["event"]["venue"] = "한강 스카이라운지"
        r = build_record(data)
        self.assertEqual(r["event"]["map_url"], "https://naver.me/example1")
        st = naver.verify(r, opener_for(final="https://map.naver.com/p/entry/place/1234"))
        self.assertEqual((st, r["event"]["map_url"]), ("staff_ok", "https://naver.me/example1"))

    def test_staff_link_beats_product(self):
        from tests.helpers import load
        from sagak.record import build_record
        data = load("s01")
        data["event"]["product"] = "레스토랑 프로포즈"
        data["event"]["venue_url"] = "https://naver.me/staff"
        self.assertEqual(build_record(data)["event"]["map_url"], "https://naver.me/staff")


class NotionPlacesTest(unittest.TestCase):
    def test_notion_places_override(self):
        from sagak import business
        from tests.helpers import load
        from sagak.record import build_record
        business.use_places({"호텔패키지": {"map_url": "https://naver.me/fromnotion", "venue": None}})
        try:
            data = load("s01")
            data["event"]["product"] = "호텔 프로포즈"
            self.assertEqual(build_record(data)["event"]["map_url"], "https://naver.me/fromnotion")
        finally:
            business.load()["map_urls"].pop("호텔패키지", None)
