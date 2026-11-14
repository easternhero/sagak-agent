import os
import tempfile
import unittest
from unittest import mock

from tests.helpers import load  # noqa: F401
from sagak import setup_notion


class SetupNotionTest(unittest.TestCase):
    def test_writes_ids_and_keeps_other_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 메모\nNOTION_API_KEY=k\nSAGAK_NOTION_EVENTS_DB=old\n")
            found = {"고객": ["a" * 32], "이벤트 (의뢰)": ["b" * 32], "상담 이력": ["c" * 32], "상품": ["d" * 32]}
            with mock.patch.object(setup_notion, "find", return_value=found):
                out = setup_notion.run(p)
            self.assertTrue(out["written"])
            text = open(p, encoding="utf-8").read()
            self.assertIn("# 메모\nNOTION_API_KEY=k\nSAGAK_NOTION_EVENTS_DB=" + "b" * 32, text)
            self.assertIn("SAGAK_NOTION_PRODUCTS_DB=" + "d" * 32, text)

    def test_ambiguous_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            with open(p, "w", encoding="utf-8") as f:
                f.write("NOTION_API_KEY=k\n")
            found = {"고객": ["a" * 32, "e" * 32], "이벤트 (의뢰)": [], "상담 이력": ["c" * 32], "상품": ["d" * 32]}
            with mock.patch.object(setup_notion, "find", return_value=found):
                out = setup_notion.run(p)
            self.assertFalse(out["written"])
            self.assertEqual(len(out["problems"]), 2)
            self.assertEqual(open(p, encoding="utf-8").read(), "NOTION_API_KEY=k\n")


if __name__ == "__main__":
    unittest.main()
