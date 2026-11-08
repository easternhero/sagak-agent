import json
import os
import tempfile
import unittest
from unittest import mock

from tests.helpers import load
from sagak import clips
from sagak.record import InputError, build_record
from sagak.transcribe import load_segments, save_result
from sagak.normalize import is_test


SEGS = [{"start": 0.0, "end": 4.0, "speaker": "A", "text": "안녕하세요"},
        {"start": 65.2, "end": 70.5, "speaker": "B", "text": "21일 3시로 할게요"},
        {"start": 71.0, "end": 140.0, "speaker": "A", "text": "긴 설명"}]


class SpanTest(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(clips.seconds("01:05"), 65.0)
        self.assertEqual(clips.seconds("1:01:05"), 3665.0)
        self.assertIsNone(clips.seconds("저녁"))

    def test_span_uses_segment(self):
        start, length = clips.span(65.0, SEGS)
        self.assertAlmostEqual(start, 64.2)
        self.assertAlmostEqual(length, 7.3)

    def test_span_capped(self):
        start, length = clips.span(71.0, SEGS)
        self.assertEqual(length, clips.MAX_LEN)

    def test_span_without_segments(self):
        self.assertEqual(clips.span(65.0, []), (63.0, 10.0))


def fake_cut(audio, start, length, out, ffmpeg):
    with open(out, "wb") as f:
        f.write(b"x")
    return True


class Store:
    def __init__(self):
        self.uploads = []

    def upload_file(self, name, data, ctype):
        self.uploads.append((name, ctype))
        return "up{}".format(len(self.uploads))


class AttachTest(unittest.TestCase):
    def record(self, audio):
        return {"audio_file": audio, "transcript_file": None, "evidence": [
            {"field": "희망 일시", "quote": "3시로 할게요", "time": "01:05"},
            {"field": "예약금", "quote": "계좌 [번호 가림]", "time": "02:00"},
            {"field": "장소", "quote": "그랜드호텔", "time": None}]}

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SAGAK_AUDIO_CLIPS", None)
            self.assertEqual(clips.attach(self.record("/x.m4a"), Store()), {"clips": 0})

    def test_attach_skips_masked_and_untimed(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a") as f, \
                mock.patch.dict(os.environ, {"SAGAK_AUDIO_CLIPS": "1"}), \
                mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(clips, "cut", side_effect=fake_cut):
            rec, store = self.record(f.name), Store()
            out = clips.attach(rec, store)
        self.assertEqual(out, {"clips": 1})
        self.assertEqual(rec["evidence"][0]["clip"], "up1")
        self.assertNotIn("clip", rec["evidence"][1])
        self.assertEqual(store.uploads[0][1], "audio/mp4")


class TranscriptFileTest(unittest.TestCase):
    def test_file_read_verbatim_and_masked(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "chat.txt")
            body = "\n".join("2026-11-05 19:{:02d}:00, 고객 : 줄 {}".format(i % 60, i) for i in range(400))
            with open(path, "w", encoding="cp949") as f:
                f.write(body + "\n계좌 110-123-456789")
            data = load("s02")
            data["transcript"] = "모델이 줄인 원문"
            data["transcript_file"] = path
            rec = build_record(data)
        self.assertEqual(len(rec["transcript"].splitlines()), 401)
        self.assertTrue(rec["transcript"].endswith("계좌 [번호 가림]"))

    def test_bad_extension_rejected(self):
        data = load("s02")
        data["transcript_file"] = "/etc/passwd"
        with self.assertRaises(InputError):
            build_record(data)

    def test_save_and_load_segments(self):
        with tempfile.TemporaryDirectory() as d:
            files = save_result({"lines": ["[00:00] A: 안녕"], "segments": SEGS}, "/tmp/voice.ogg", outdir=d)
            self.assertTrue(files["transcript_file"].endswith(".sagak.txt"))
            with open(files["transcript_file"], encoding="utf-8") as f:
                self.assertEqual(f.read(), "[00:00] A: 안녕\n")
            self.assertEqual(load_segments(files["transcript_file"]), SEGS)


class TestMarkTest(unittest.TestCase):
    def test_is_test(self):
        self.assertTrue(is_test("[테스트] 박서준", "010-1234-5678"))
        self.assertTrue(is_test("박서준", "010-0000-0001"))
        self.assertFalse(is_test("박서준", "010-1234-5678"))


if __name__ == "__main__":
    unittest.main()
