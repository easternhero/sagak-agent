import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.helpers import load  # noqa: F401
from sagak.transcribe import (TranscribeError, parse_response, prepare, request_fields, to_lines,
                              transcribe)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


DIARIZED = {"text": "네 예시이벤트입니다. 12월 12일 저녁에 프로포즈를 하고 싶어서요.", "segments": [
    {"type": "transcript.text.segment", "id": "s1", "start": 0.4, "end": 2.1, "speaker": "A", "text": " 네, 예시이벤트입니다."},
    {"type": "transcript.text.segment", "id": "s2", "start": 65.0, "end": 70.2, "speaker": "B", "text": "12월 12일 저녁에 프로포즈를 하고 싶어서요."},
    {"type": "transcript.text.segment", "id": "s3", "start": 71.0, "end": 71.5, "speaker": "B", "text": "  "}]}


class TranscribeTest(unittest.TestCase):
    def test_lines_with_time_and_speaker(self):
        lines = to_lines(parse_response(DIARIZED))
        self.assertEqual(lines, ["[00:00] A: 네, 예시이벤트입니다.", "[01:05] B: 12월 12일 저녁에 프로포즈를 하고 싶어서요."])

    def test_text_only_model(self):
        r = parse_response({"text": "안녕하세요"})
        self.assertEqual(to_lines(r), ["안녕하세요"])

    def test_request_fields(self):
        self.assertEqual(request_fields("gpt-4o-transcribe-diarize")["response_format"], "diarized_json")
        self.assertEqual(request_fields("whisper-1")["response_format"], "verbose_json")

    def test_request_is_multipart_and_parsed(self):
        calls = []

        def opener(req, timeout=None):
            calls.append(req)
            return FakeResponse(json.dumps(DIARIZED).encode())

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "call.m4a")
            with open(path, "wb") as f:
                f.write(b"fake-audio")
            out = transcribe(path, model="gpt-4o-transcribe-diarize", key="k", opener=opener)
        body = calls[0].data
        self.assertIn(b'name="response_format"\r\n\r\ndiarized_json', body)
        self.assertIn(b'filename="call.m4a"', body)
        self.assertIn(b"fake-audio", body)
        self.assertEqual(out["lines"][1], "[01:05] B: 12월 12일 저녁에 프로포즈를 하고 싶어서요.")

    def test_missing_file(self):
        with self.assertRaises(TranscribeError) as ctx:
            transcribe("/no/such/file.m4a", key="k")
        self.assertEqual(ctx.exception.code, "NO_FILE")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg 없음")
    def test_ogg_is_converted(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "voice.ogg")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                            "-c:a", "libopus", src], check=True)
            out = prepare(src, d)
            self.assertTrue(out.endswith(".m4a") and os.path.getsize(out) > 0)


if __name__ == "__main__":
    unittest.main()
