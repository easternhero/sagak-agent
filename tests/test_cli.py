import os
import tempfile
import unittest

from tests.helpers import load  # noqa: F401
from sagak import pending
from sagak.__main__ import main, page_id


class CliTest(unittest.TestCase):
    def test_page_id_from_links(self):
        pid = "41191ad5d4258105b53fc5991e3effad"
        for text in ("https://app.notion.com/p/" + pid + "?pvs=204",
                     "https://www.notion.so/11-07-" + pid,
                     "41191ad5-d425-8105-b53f-c5991e3effad"):
            self.assertEqual(page_id(text), pid)

    def test_pending_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["SAGAK_PENDING_DIR"] = d
            try:
                pending.save("abc-def", {"x": 1}, [])
                self.assertEqual(pending.load("abcdef")["record"], {"x": 1})
                pending.delete("abcdef")
                self.assertIsNone(pending.load("abcdef"))
                # 보류 정보가 없으면 입력 문제(2)로 끝남
                self.assertEqual(main(["resolve", "41191ad5d4258105b53fc5991e3effad", "same"]), 2)
            finally:
                del os.environ["SAGAK_PENDING_DIR"]


if __name__ == "__main__":
    unittest.main()
