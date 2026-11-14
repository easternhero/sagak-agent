#!/bin/bash
# 데모용 가상 상담 통화 녹음 만들기 (macOS). 상담·고객 두 목소리로 읽어 demo/call-recording.m4a를 만든다.
# 필요: macOS say (한국어 음성), ffmpeg. 쓰는 법: bash demo/make-call-audio.sh
set -euo pipefail
cd "$(dirname "$0")"
VOICES=$(say -v '?' | awk '/ko_KR/ {print $1}')
STAFF=$(echo "$VOICES" | sed -n 1p)
CUST=$(echo "$VOICES" | sed -n 2p)
[ -z "$STAFF" ] && { echo "한국어 음성이 없어요. 시스템 설정 → 손쉬운 사용 → 음성 콘텐츠에서 한국어 음성을 추가해 주세요."; exit 1; }
[ -z "$CUST" ] && CUST="$STAFF"
echo "상담 목소리: $STAFF / 고객 목소리: $CUST"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FMT="-ar 22050 -ac 1 -c:a pcm_s16le"   # 모든 조각을 같은 형식(WAV 22kHz 모노)으로 맞춰야 합칠 때 소리가 빠지지 않음
ffmpeg -loglevel error -f lavfi -i anullsrc=r=22050:cl=mono -t 0.4 $FMT "$TMP/gap.wav"
i=0
while IFS='|' read -r who line; do
  [ -z "${line:-}" ] && continue
  i=$((i+1)); n=$(printf %02d $i)
  if [ "$who" = "상담" ]; then V="$STAFF"; R=185; else V="$CUST"; R=170; fi
  say -v "$V" -r "$R" -o "$TMP/$n.aiff" "$line"
  ffmpeg -loglevel error -i "$TMP/$n.aiff" $FMT "$TMP/$n.wav"
  printf "file '%s'\nfile '%s'\n" "$TMP/$n.wav" "$TMP/gap.wav" >> "$TMP/list.txt"
done < call-script.txt
ffmpeg -loglevel error -y -f concat -safe 0 -i "$TMP/list.txt" -c:a aac -b:a 64k call-recording.m4a
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 call-recording.m4a)
echo "만들었어요: $(pwd)/call-recording.m4a (${DUR%.*}초, ${i}줄)"
if [ "${DUR%.*}" -lt 15 ]; then echo "⚠️ 너무 짧아요. 말소리가 빠졌을 수 있어요 — 결과를 알려 주세요."; exit 1; fi
