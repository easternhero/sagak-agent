import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ["SAGAK_BUSINESS_FILE"] = os.path.join(ROOT, "tests", "fixtures", "business.json")  # 가상 업체 설정


def load(name):
    with open(os.path.join(ROOT, "tests", "fixtures", "extractions", name + ".json"), encoding="utf-8") as f:
        return json.load(f)
