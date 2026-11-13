import unittest

from tests.helpers import load  # noqa: F401  (sys.path·가상 업체 설정)
from sagak.demo import run


class DemoTest(unittest.TestCase):
    def test_demo_runs_without_keys(self):
        out = []
        result = run(echo=out.append)
        self.assertEqual((result["customers"], result["events"], result["consultations"]), (3, 3, 5))
        self.assertEqual(result["results"][-1]["refused"], "MISSING_CUSTOMER")  # 관계없는 녹음은 기록 안 함
        text = "\n".join(out)
        self.assertIn("같은 사람인가요?", text)
        self.assertIn("이벤트진행예정", text)


if __name__ == "__main__":
    unittest.main()
