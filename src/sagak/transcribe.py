"""녹음 파일 → 구간별 시간(·화자)이 있는 전사. OpenAI 음성 인식 API, 표준 라이브러리만 사용.

모델은 SAGAK_STT_MODEL로 바꾼다.
- gpt-4o-transcribe-diarize (기본): 구간 시간 + 화자 구분 (diarized_json)
- whisper-1: 구간 시간 (verbose_json)
- 그 밖의 모델(예: gpt-transcribe): 텍스트만, 시간 없음
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from typing import Optional

API = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_MODEL = "gpt-4o-transcribe-diarize"
SUPPORTED = (".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm")
MAX_BYTES = 25 * 1024 * 1024


class TranscribeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _multipart(fields: dict, file_field: str, filename: str, data: bytes):
    boundary = "----sagak" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append("--{}\r\nContent-Disposition: form-data; name=\"{}\"\r\n\r\n{}\r\n".format(boundary, name, value).encode())
    parts.append("--{}\r\nContent-Disposition: form-data; name=\"{}\"; filename=\"{}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                 .format(boundary, file_field, filename).encode() + data + b"\r\n")
    parts.append("--{}--\r\n".format(boundary).encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def request_fields(model: str) -> dict:
    if model == "gpt-4o-transcribe-diarize":
        return {"model": model, "response_format": "diarized_json", "chunking_strategy": "auto"}
    if model == "whisper-1":
        return {"model": model, "response_format": "verbose_json", "language": "ko"}
    return {"model": model, "response_format": "json"}


def parse_response(body: dict) -> dict:
    """API 응답 → {"text", "segments": [{"start", "end", "speaker", "text"}]}"""
    segments = []
    for seg in body.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append({"start": float(seg.get("start") or 0), "end": float(seg.get("end") or 0),
                         "speaker": seg.get("speaker"), "text": text})
    return {"text": (body.get("text") or " ".join(s["text"] for s in segments)).strip(), "segments": segments}


def mmss(seconds: float) -> str:
    s = int(seconds)
    return "{:02d}:{:02d}".format(s // 60, s % 60)


def to_lines(result: dict) -> list:
    """'[01:23] A: 내용' 형태. 시간 정보가 없으면 전체 텍스트 한 줄."""
    if not result["segments"]:
        return [result["text"]] if result["text"] else []
    lines = []
    for seg in result["segments"]:
        who = "{}: ".format(seg["speaker"]) if seg.get("speaker") else ""
        lines.append("[{}] {}{}".format(mmss(seg["start"]), who, seg["text"]))
    return lines


def prepare(path: str, workdir: str) -> str:
    """API가 받지 않는 형식(ogg, amr, 3gp 등)은 ffmpeg로 m4a로 바꾼다."""
    if not os.path.isfile(path):
        raise TranscribeError("NO_FILE", "녹음 파일을 찾지 못했습니다: " + path)
    if os.path.splitext(path)[1].lower() in SUPPORTED:
        return path
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TranscribeError("UNSUPPORTED_FORMAT", "지원하지 않는 파일 형식이고 ffmpeg가 없습니다: " + path)
    out = os.path.join(workdir, "audio.m4a")
    proc = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", out],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise TranscribeError("BAD_AUDIO", "녹음 파일을 읽지 못했습니다(손상되었거나 지원하지 않는 형식).")
    return out


def transcribe(path: str, model: Optional[str] = None, key: Optional[str] = None, opener=None) -> dict:
    model = model or os.environ.get("SAGAK_STT_MODEL") or DEFAULT_MODEL
    # Hermes는 자체 음성 키(VOICE_TOOLS_OPENAI_KEY)를 외부 명령에 넘기지 않으므로 사각사각 전용 이름을 쓴다
    key = key or os.environ.get("SAGAK_OPENAI_STT_KEY")
    if not key:
        raise TranscribeError("NO_KEY", "환경변수 없음: SAGAK_OPENAI_STT_KEY")
    with tempfile.TemporaryDirectory() as workdir:
        audio = prepare(path, workdir)
        size = os.path.getsize(audio)
        if size > MAX_BYTES:
            raise TranscribeError("FILE_TOO_LARGE", "녹음 파일이 25MB를 넘습니다({:.1f}MB).".format(size / 1048576))
        with open(audio, "rb") as f:
            body, ctype = _multipart(request_fields(model), "file", os.path.basename(audio), f.read())
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": ctype})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=300) as resp:
            result = parse_response(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise TranscribeError("STT_FAILED", "음성 인식 실패 ({}): {}".format(e.code, detail)) from None
    except urllib.error.URLError as e:
        raise TranscribeError("STT_FAILED", "음성 인식 서버 연결 실패: {}".format(e.reason)) from None
    if not result["text"]:
        raise TranscribeError("EMPTY_AUDIO", "녹음에서 말소리를 찾지 못했습니다.")
    result["model"] = model
    result["lines"] = to_lines(result)
    return result
