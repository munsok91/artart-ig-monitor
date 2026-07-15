#!/bin/bash
# 에이밍 완성본을 main.artart 소유 팀 검수함에 업로드하고 Slack에 알린다.
#
# 집맥에는 Google Drive 앱이 없으므로 기존 rclone 자격을 사용하되,
# 개인 드라이브 루트가 아니라 main.artart 팀 폴더의 고정 ID를 루트로 삼는다.
# 사용법: bash scripts/upload_drive.sh <회차폴더> "<드라이브폴더명>"
set -uo pipefail

SRC="${1:?회차 폴더 경로 필요}"
DEST_NAME="${2:?드라이브 폴더명 필요}"
RCLONE_REMOTE="${RCLONE_REMOTE:-artartdrive}"
TEAM_ROOT_ID="${AIMING_TEAM_DRIVE_ROOT_ID:-1DbTQXgU5-AloY1nRLOPmjjeJQDcr21UW}"
SLACK_WEBHOOK="${SLACK_AIMING_WEBHOOK_URL:-${SLACK_ECON_WEBHOOK_URL:-}}"

EP="$(basename "$SRC" | grep -oE '^ep[0-9]+' || true)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp "$SRC"/out/slide_*.png "$STAGE/" 2>/dev/null || true
cp "$SRC"/caption.md "$STAGE/캡션.md" 2>/dev/null || true

SLIDE_COUNT="$(find "$STAGE" -maxdepth 1 -type f -name 'slide_*.png' | wc -l | tr -d ' ')"
EMPTY_SLIDE="$(find "$STAGE" -maxdepth 1 -type f -name 'slide_*.png' -size 0 -print -quit)"
if [ "$SLIDE_COUNT" -lt 6 ] || [ -n "$EMPTY_SLIDE" ] || [ ! -s "$STAGE/캡션.md" ]; then
  echo "[drive] ❌ 올릴 PNG/캡션이 불완전합니다: $SRC" >&2
  exit 2
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "[drive] ❌ rclone이 없어 main.artart 팀 검수함에 올릴 수 없습니다" >&2
  exit 3
fi
if ! rclone listremotes 2>/dev/null | grep -Fqx "${RCLONE_REMOTE}:"; then
  echo "[drive] ❌ rclone 연결 '${RCLONE_REMOTE}'을 찾지 못했습니다" >&2
  exit 3
fi
if [ -z "$SLACK_WEBHOOK" ]; then
  echo "[slack] ❌ 알림 연결이 없어 팀 전달 완료로 처리할 수 없습니다" >&2
  exit 3
fi

notify_slack() {
  local folder_link="$1"
  local display_name="${TARGET_NAME:-$DEST_NAME}"
  python3 - "$SLACK_WEBHOOK" "$display_name" "$SLIDE_COUNT" "$folder_link" <<'PY'
import json
import sys
import urllib.request

webhook, name, count, link = sys.argv[1:]
text = (
    f"✅ *에이밍 검수본 업로드 완료*\n"
    f"▶ {name}\n"
    f"▶ 슬라이드 {count}장 + 캡션\n"
    f"▶ 아트아트 투데이 드라이브: {link}"
)
request = urllib.request.Request(
    webhook,
    data=json.dumps({"text": text, "unfurl_links": False, "unfurl_media": False}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=30) as response:
    body = response.read().decode().strip()
if body != "ok":
    raise SystemExit(f"Slack webhook 응답 오류: {body}")
PY
}

# 폴더 공개 권한을 만들지 않고, 이름과 Google Drive ID를 함께 찾는다.
find_folder() {
  local needle="$1"
  rclone lsf "${RCLONE_REMOTE}:" --drive-root-folder-id "$TEAM_ROOT_ID" \
    --dirs-only --dir-slash=false --format ip --separator $'\t' 2>/dev/null \
    | awk -F '\t' -v needle="$needle" 'index($2, needle) { print; exit }'
}

# 같은 회차가 있으면 그 폴더를 보충 업로드하고, 파일까지 다시 검증한다.
ENTRY=""
if [ -n "$EP" ]; then
  ENTRY="$(find_folder "_${EP}_")"
fi
TARGET_NAME="$DEST_NAME"
FOLDER_ID=""
if [ -n "$ENTRY" ]; then
  FOLDER_ID="${ENTRY%%$'\t'*}"
  TARGET_NAME="${ENTRY#*$'\t'}"
  echo "[drive] 기존 $EP 폴더를 보충하고 다시 검증합니다"
fi

if ! rclone copy "$STAGE" "${RCLONE_REMOTE}:$TARGET_NAME" \
    --drive-root-folder-id "$TEAM_ROOT_ID" --drive-chunk-size 32M -q; then
  echo "[drive] ❌ main.artart 팀 검수함 업로드 실패" >&2
  exit 4
fi

REMOTE_FILES="$(rclone lsf "${RCLONE_REMOTE}:$TARGET_NAME" \
  --drive-root-folder-id "$TEAM_ROOT_ID" --files-only 2>/dev/null || true)"
REMOTE_SLIDES="$(printf '%s\n' "$REMOTE_FILES" | grep -c '^slide_[0-9][0-9]*\.png$' || true)"
if [ "$REMOTE_SLIDES" -ne "$SLIDE_COUNT" ] || \
   ! printf '%s\n' "$REMOTE_FILES" | grep -Fqx '캡션.md'; then
  echo "[drive] ❌ 업로드 후 파일 검증 실패 (로컬 ${SLIDE_COUNT}장 / 원격 ${REMOTE_SLIDES}장)" >&2
  exit 4
fi

if [ -z "$FOLDER_ID" ]; then
  ENTRY="$(find_folder "$TARGET_NAME")"
  FOLDER_ID="${ENTRY%%$'\t'*}"
fi
if [ -z "$FOLDER_ID" ]; then
  echo "[drive] ❌ 업로드 폴더의 Drive ID 확인 실패" >&2
  exit 4
fi
# 기존 검수함과 같은 방식으로, 링크를 받은 팀원이 별도 로그인 없이 읽을 수 있게 한다.
# 루트 전체가 아니라 이 회차 폴더 하나에만 읽기 권한을 연다.
LINK="$(rclone link "${RCLONE_REMOTE}:$TARGET_NAME" \
  --drive-root-folder-id "$TEAM_ROOT_ID" 2>/dev/null || true)"
if [ -z "$LINK" ]; then
  echo "[drive] ❌ 팀 검수 링크 생성 실패" >&2
  exit 4
fi
echo "[drive] ✅ main.artart 팀 검수함 업로드: $TARGET_NAME"
echo "[drive] 🔗 $LINK"

if ! notify_slack "$LINK"; then
  echo "[slack] ❌ 팀 알림 실패 (Drive 업로드는 완료)" >&2
  exit 5
fi
printf '%s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" > "$STAGE/.slack_notified"
if ! rclone copyto "$STAGE/.slack_notified" \
    "${RCLONE_REMOTE}:$TARGET_NAME/.slack_notified" \
    --drive-root-folder-id "$TEAM_ROOT_ID" -q; then
  echo "[slack] ❌ 알림 성공 표시 저장 실패" >&2
  exit 5
fi
echo "[slack] ✅ #02_경제채널_운영에 검수 링크 알림 완료"
