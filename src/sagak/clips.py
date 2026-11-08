"""근거 문장마다 녹음 구간을 잘라 상담 이력 페이지에 붙인다 (D43).

고객 음성이 Notion에 저장되므로 SAGAK_AUDIO_CLIPS=1일 때만 동작한다(기본 꺼짐).
계좌·카드번호를 가린 근거([번호 가림])는 자르지 않는다. 실패해도 기록은 계속한다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional

from .transcribe import load_segments

PAD = 1.0        # 구간 앞뒤 여유(초)
MAX_LEN = 30.0   # 클립 최대 길이(초)
FALLBACK = (2.0, 10.0)  # 구간 정보가 없을 때: 말한 시각 2초 전부터 10초


def enabled() -> bool:
    return os.environ.get("SAGAK_AUDIO_CLIPS", "").strip().lower() in ("1", "true", "on", "yes")


def seconds(mmss: Optional[str]) -> Optional[float]:
    m = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*", mmss or "")
    if not m:
        return None
    h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return float(h * 3600 + mi * 60 + s)


def span(t: float, segments: list) -> tuple:
    """근거 시각 t가 들어 있는(또는 직전에 시작한) 구간 → (시작, 길이)."""
    hit = None
    for seg in segments:
        if seg["start"] <= t + 1:
            hit = seg
        else:
            break
    if hit is None or hit.get("end", 0) < t - 1:
        start = max(0.0, t - FALLBACK[0])
        return start, FALLBACK[1]
    start = max(0.0, hit["start"] - PAD)
    return start, min(MAX_LEN, max(3.0, hit["end"] + PAD - start))


def cut(audio: str, start: float, length: float, out: str, ffmpeg: str) -> bool:
    proc = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "{:.2f}".format(start), "-t", "{:.2f}".format(length),
                           "-i", audio, "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "48k", out],
                          capture_output=True, text=True)
    return proc.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0


def attach(record: dict, store) -> dict:
    """record['evidence'][i]['clip']에 업로드 id를 채운다. 결과 요약을 돌려준다."""
    audio = record.get("audio_file")
    if not enabled() or not audio:
        return {"clips": 0}
    ffmpeg = shutil.which("ffmpeg")
    if not os.path.isfile(audio) or not ffmpeg:
        return {"clips": 0, "error": "녹음 파일 또는 ffmpeg 없음"}
    segments = sorted(load_segments(record.get("transcript_file")), key=lambda s: s["start"])
    made, errors = 0, []
    with tempfile.TemporaryDirectory() as tmp:
        for i, e in enumerate(record.get("evidence") or []):
            t = seconds(e.get("time"))
            if t is None or "[번호 가림]" in (e.get("quote") or ""):
                continue
            start, length = span(t, segments)
            out = os.path.join(tmp, "clip{}.m4a".format(i))
            if not cut(audio, start, length, out, ffmpeg):
                errors.append("{} 자르기 실패".format(e.get("time")))
                continue
            try:
                with open(out, "rb") as f:
                    e["clip"] = store.upload_file("근거-{}-{}.m4a".format(i + 1, e["time"].replace(":", "")), f.read(), "audio/mp4")
                made += 1
            except Exception as err:  # 업로드 실패는 기록을 막지 않는다
                errors.append(str(err)[:120])
    out = {"clips": made}
    if errors:
        out["error"] = "; ".join(errors[:3])
    return out
