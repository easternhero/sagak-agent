#!/bin/bash
# 데모용 가상 상담 통화 녹음 만들기 (macOS). 상담·고객 두 목소리로 읽어 demo/call-recording.m4a를 만든다.
# 필요: macOS say (한국어 음성), ffmpeg. 쓰는 법: bash demo/make-call-audio.sh
set -euo pipefail
cd "$(dirname "$0")"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FMT="-ar 22050 -ac 1 -c:a pcm_s16le"   # 모든 조각을 같은 형식(WAV 22kHz 모노)으로 맞춰 합친다

# 파일로 저장했을 때 실제로 소리가 나는지 (일부 음성은 스피커로는 읽어도 파일로는 무음을 씀)
loud() {  # $1 = wav, 최대 음량이 -50dB보다 크면 소리 있음
  local max
  max=$(ffmpeg -nostdin -i "$1" -af volumedetect -f null - 2>&1 | awk '/max_volume/ {print $5}')
  awk -v m="${max:--999}" 'BEGIN { exit !(m > -50) }'
}

echo "한국어 음성 확인 중…"
GOOD=()
while IFS= read -r v; do
  [ -z "$v" ] && continue
  if say -v "$v" -o "$TMP/try.aiff" "안녕하세요" 2>/dev/null \
     && ffmpeg -nostdin -loglevel error -y -i "$TMP/try.aiff" $FMT "$TMP/try.wav" && loud "$TMP/try.wav"; then
    GOOD+=("$v"); echo "  ✓ $v"
  else
    echo "  ✗ $v (파일로 저장하면 소리가 없음)"
  fi
done < <(say -v '?' | grep 'ko_KR' | sed -E 's/ +ko_KR.*//')
if [ ${#GOOD[@]} -eq 0 ]; then
  echo "파일로 저장되는 한국어 음성이 없어요. 시스템 설정 → 손쉬운 사용 → 음성 콘텐츠 → 시스템 음성 → 음성 관리에서"
  echo "'Yuna'(또는 다른 한국어 음성)를 내려받은 뒤 다시 실행해 주세요."
  exit 1
fi
STAFF="${GOOD[0]}"; CUST="${GOOD[1]:-${GOOD[0]}}"
echo "상담 목소리: $STAFF / 고객 목소리: $CUST"

ffmpeg -nostdin -loglevel error -f lavfi -i anullsrc=r=22050:cl=mono -t 0.4 $FMT "$TMP/gap.wav"
i=0
while IFS='|' read -r who line; do
  [ -z "${line:-}" ] && continue
  i=$((i+1)); n=$(printf %02d $i)
  if [ "$who" = "상담" ]; then V="$STAFF"; R=185; else V="$CUST"; R=170; fi
  say -v "$V" -r "$R" -o "$TMP/$n.aiff" "$line"
  ffmpeg -nostdin -loglevel error -i "$TMP/$n.aiff" $FMT "$TMP/$n.wav"
  printf "file '%s'\nfile '%s'\n" "$TMP/$n.wav" "$TMP/gap.wav" >> "$TMP/list.txt"
done < call-script.txt
ffmpeg -nostdin -loglevel error -y -f concat -safe 0 -i "$TMP/list.txt" -c:a aac -b:a 64k call-recording.m4a
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 call-recording.m4a)
echo "만들었어요: $(pwd)/call-recording.m4a (${DUR%.*}초, ${i}줄)"
if [ "${DUR%.*}" -lt 15 ]; then echo "⚠️ 너무 짧아요 (${i}줄). 이 출력을 그대로 알려 주세요."; exit 1; fi
