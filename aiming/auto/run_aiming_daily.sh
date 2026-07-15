#!/bin/bash
# 에이밍 데일리 카드뉴스 — 무인 제작·드라이브 업로드 러너 (launchd 진입점)
set -Eeuo pipefail
: "${HOME:=$(eval echo ~$(id -un))}"
export HOME
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
KIT="$HOME/code/aiming-cardnews-kit"
ARTART="$HOME/code/artart-cardnews-automation"
LOG_DIR="$KIT/logs"
LOG_FILE="$LOG_DIR/auto.log"
LOCK_DIR="$LOG_DIR/.daily.lock"
mkdir -p "$LOG_DIR" || exit 70
START_EPOCH="$(date +%s)"
RUN_ID="$(date '+%Y%m%d-%H%M%S')-$$"
STAGE="bootstrap"
FINAL_STATUS="FAILED"
LOCKED=0
EPISODE=""
log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*" >> "$LOG_FILE"
}

cleanup() {
  [ "$LOCKED" -eq 1 ] || return 0
  rm -f "$LOCK_DIR/pid" "$LOCK_DIR"/episodes.* "$LOCK_DIR"/drive.* \
    "$LOCK_DIR/slides" 2>/dev/null || true
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
finish() {
  local rc="$?" duration
  trap - EXIT ERR
  if [ "$FINAL_STATUS" = "FAILED" ] && [ "$rc" -eq 0 ]; then rc=1; fi
  duration=$(( $(date +%s) - START_EPOCH ))
  log "===== aiming daily 종료 | status=$FINAL_STATUS | exit=$rc | stage=$STAGE | duration=${duration}s | episode=${EPISODE:-none} | run_id=$RUN_ID ====="
  if [ "$FINAL_STATUS" = "FAILED" ]; then
    notify_failure "$rc" "$duration" || log "[warn] Slack 실패 알림을 보내지 못했습니다"
  fi
  cleanup
  exit "$rc"
}
notify_failure() {
  local rc="$1" duration="$2"
  local webhook="${SLACK_AIMING_WEBHOOK_URL:-${SLACK_ECON_WEBHOOK_URL:-}}"
  [ -n "$webhook" ] || return 0
  python3 - "$webhook" "$STAGE" "$rc" "$duration" "$EPISODE" <<'PY' >> "$LOG_FILE" 2>&1
import json
import sys
import urllib.request

webhook, stage, code, duration, episode = sys.argv[1:]
text = (
    "❌ *에이밍 자동 작업 실패*\n"
    f"▶ 멈춘 단계: {stage}\n"
    f"▶ 회차: {episode or '생성 전'}\n"
    f"▶ 종료 코드: {code} / {duration}초"
)
request = urllib.request.Request(
    webhook,
    data=json.dumps({"text": text}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=30) as response:
    if response.read().decode().strip() != "ok":
        raise SystemExit(1)
PY
}
fail() {
  local rc="$1"
  shift
  log "[error] stage=$STAGE exit=$rc $*"
  exit "$rc"
}
timed() {
  local seconds="$1"
  shift
  /usr/bin/perl -e 'alarm shift; exec @ARGV' "$seconds" "$@"
}
snapshot_episodes() {
  find "$KIT/episodes" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; \
    | LC_ALL=C sort > "$1"
}

refresh_drive_count() {
  local dirs_file="$LOCK_DIR/drive.dirs"
  local files_file="$LOCK_DIR/drive.files"
  local success_file="$LOCK_DIR/drive.success"
  local folder suffix episode_key remote_slides remote_caption remote_notified

  : > "$success_file"
  if ! timed 180 rclone lsf "${RCLONE_REMOTE}:" \
      --drive-root-folder-id "$TEAM_ROOT_ID" --dirs-only \
      --dir-slash=false --format p > "$dirs_file" 2>> "$LOG_FILE"; then
    fail 41 "팀 드라이브의 오늘 업로드 수 확인 실패"
  fi

  while IFS= read -r folder; do
    case "$folder" in
      "$TODAY_PREFIX"*) ;;
      *) continue ;;
    esac
    suffix="${folder#"$TODAY_PREFIX"}"
    episode_key="$(printf '%s\n' "$suffix" | sed -nE 's/^(ep[0-9]+)_.*/\1/p')"
    [ -n "$episode_key" ] || continue
    if ! timed 180 rclone lsf "${RCLONE_REMOTE}:$folder" \
        --drive-root-folder-id "$TEAM_ROOT_ID" --files-only \
        --format sp --separator $'\t' > "$files_file" 2>> "$LOG_FILE"; then
      fail 41 "팀 드라이브 파일 검증 실패: $folder"
    fi
    remote_slides="$(awk -F '\t' '$1 + 0 > 0 && $2 ~ /^slide_[0-9]+[.]png$/ { n++ } END { print n + 0 }' "$files_file")"
    remote_caption="$(awk -F '\t' '$1 + 0 > 0 && $2 == "캡션.md" { n++ } END { print n + 0 }' "$files_file")"
    remote_notified="$(awk -F '\t' '$1 + 0 > 0 && $2 == ".slack_notified" { n++ } END { print n + 0 }' "$files_file")"
    if [ "$remote_slides" -ge 6 ] && [ "$remote_caption" -ge 1 ] && [ "$remote_notified" -ge 1 ]; then
      if grep -Fqx "$episode_key" "$success_file"; then
        log "[warn] 오늘 같은 회차 폴더가 중복돼 1개로 계산: $episode_key"
      else
        printf '%s\n' "$episode_key" >> "$success_file"
      fi
    else
      log "[warn] 오늘 폴더가 불완전해 완료 수에서 제외: $folder (PNG=${remote_slides}, caption=${remote_caption}, Slack=${remote_notified})"
    fi
  done < "$dirs_file"
  DRIVE_TODAY_COUNT="$(awk 'END { print NR + 0 }' "$success_file")"
}

trap 'rc=$?; cmd=$BASH_COMMAND; log "[error] stage=$STAGE line=$LINENO exit=$rc command=$cmd"; exit "$rc"' ERR
trap finish EXIT
log "===== aiming daily 시작 | run_id=$RUN_ID | pid=$$ ====="
STAGE="lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OWNER_PID="$(sed -n '1p' "$LOCK_DIR/pid" 2>/dev/null || true)"
  OWNER_COMMAND="$(ps -p "$OWNER_PID" -o command= 2>/dev/null || true)"
  if [ -n "$OWNER_PID" ] && kill -0 "$OWNER_PID" 2>/dev/null \
      && printf '%s' "$OWNER_COMMAND" | grep -Fq 'run_aiming_daily.sh'; then
    FINAL_STATUS="SKIPPED"
    log "[skip] 이미 실행 중입니다 (pid=$OWNER_PID)"
    exit 0
  fi
  log "[warn] 오래된 실행 잠금을 제거합니다"
  rm -f "$LOCK_DIR/pid" "$LOCK_DIR"/episodes.* "$LOCK_DIR"/drive.* \
    "$LOCK_DIR/slides" 2>/dev/null || true
  rmdir "$LOCK_DIR" 2>/dev/null || fail 73 "오래된 잠금 제거 실패"
  mkdir "$LOCK_DIR" 2>/dev/null || fail 73 "실행 잠금 획득 실패"
fi
LOCKED=1
printf '%s\n' "$$" > "$LOCK_DIR/pid"
STAGE="preflight"
[ -d "$ARTART" ] || fail 20 "프로젝트 폴더 없음: $ARTART"
[ -f "$ARTART/.env" ] || fail 20 "환경 파일 없음: $ARTART/.env"
[ -f "$KIT/auto/aiming_daily_prompt.md" ] || fail 20 "자동 제작 지시문 없음"
[ -f "$KIT/scripts/upload_drive.sh" ] || fail 20 "팀 전달 스크립트 없음"
STAGE="environment"
set -a
# shellcheck disable=SC1091
source "$ARTART/.env" || fail 21 "환경 파일 읽기 실패"
set +a
RCLONE_REMOTE="${RCLONE_REMOTE:-artartdrive}"
TEAM_ROOT_ID="${AIMING_TEAM_DRIVE_ROOT_ID:-1DbTQXgU5-AloY1nRLOPmjjeJQDcr21UW}"
DAILY_TARGET=3
RUN_DATE="$(date '+%Y-%m-%d')"
TODAY_PREFIX="[에이밍] ${RUN_DATE}_"
cd "$KIT" || fail 20 "작업 폴더 진입 실패"
command -v rclone >/dev/null 2>&1 || fail 20 "rclone 명령 없음"
STAGE="drive_precheck"
refresh_drive_count
log "[drive] ${RUN_DATE} 정상 전달분: ${DRIVE_TODAY_COUNT}/${DAILY_TARGET}"
if [ "$DRIVE_TODAY_COUNT" -ge "$DAILY_TARGET" ]; then
  [ "$DRIVE_TODAY_COUNT" -eq "$DAILY_TARGET" ] \
    || log "[warn] 오늘 정상 전달분이 목표를 초과했습니다: ${DRIVE_TODAY_COUNT}/${DAILY_TARGET}"
  log "[drive] 오늘 목표 ${DAILY_TARGET}개가 이미 완료돼 추가 제작하지 않습니다"
  STAGE="complete"
  FINAL_STATUS="SUCCESS"
  exit 0
fi
command -v claude >/dev/null 2>&1 || fail 20 "claude 명령 없음"
[ -n "${SLACK_AIMING_WEBHOOK_URL:-${SLACK_ECON_WEBHOOK_URL:-}}" ] \
  || fail 20 "Slack 알림 연결 없음"
STAGE="update_code"
export GIT_TERMINAL_PROMPT=0
timed 180 git -C "$KIT" pull --rebase --autostash -q >> "$LOG_FILE" 2>&1 \
  || log "[warn] 키트 git pull 실패/시간초과 — 기존 사본으로 진행"
timed 180 git -C "$ARTART" pull --rebase --autostash -q >> "$LOG_FILE" 2>&1 \
  || log "[warn] artart git pull 실패/시간초과 — 기존 사본으로 진행"
STAGE="renderer"
if [ ! -x "$KIT/.venv/bin/python" ]; then
  log "[setup] 렌더 환경을 처음 설치합니다"
  timed 180 python3 -m venv "$KIT/.venv" >> "$LOG_FILE" 2>&1 || fail 22 "venv 생성 실패"
  timed 600 "$KIT/.venv/bin/pip" install -q --upgrade pip playwright pillow numpy \
    >> "$LOG_FILE" 2>&1 || fail 22 "렌더 의존성 설치 실패/시간초과"
  timed 900 "$KIT/.venv/bin/playwright" install chromium \
    >> "$LOG_FILE" 2>&1 || fail 22 "Chromium 설치 실패/시간초과"
fi
timed 300 "$KIT/.venv/bin/pip" install -q pillow numpy >> "$LOG_FILE" 2>&1 \
  || fail 22 "이미지 처리 환경(pillow/numpy) 확인 실패"
STAGE="topics"
timed 600 python3 "$ARTART/src/econ/scrape_ig.py" >> "$LOG_FILE" 2>&1 \
  || log "[warn] 소재 갱신 실패/시간초과 — 기존 후보로 진행"
mkdir -p "$KIT/episodes"

while [ "$DRIVE_TODAY_COUNT" -lt "$DAILY_TARGET" ]; do
  SLOT=$((DRIVE_TODAY_COUNT + 1))
  EPISODE=""
  snapshot_episodes "$LOCK_DIR/episodes.before"

  STAGE="claude_${SLOT}_of_${DAILY_TARGET}"
  log "[make] 오늘 ${SLOT}/${DAILY_TARGET} 제작을 시작합니다"
  if timed 2700 claude -p "$(cat "$KIT/auto/aiming_daily_prompt.md")" \
    --dangerously-skip-permissions >> "$LOG_FILE" 2>&1; then
    CLAUDE_RC=0
  else
    CLAUDE_RC=$?
  fi
  if [ "$CLAUDE_RC" -ne 0 ]; then
    [ "$CLAUDE_RC" -eq 142 ] && fail 124 "Claude 작업이 45분을 넘어 강제 종료됨 (${SLOT}/${DAILY_TARGET})"
    fail "$CLAUDE_RC" "Claude 제작 실패 (${SLOT}/${DAILY_TARGET})"
  fi

  STAGE="verify_${SLOT}_of_${DAILY_TARGET}"
  snapshot_episodes "$LOCK_DIR/episodes.after"
  comm -13 "$LOCK_DIR/episodes.before" "$LOCK_DIR/episodes.after" > "$LOCK_DIR/episodes.new"
  NEW_COUNT="$(awk 'END { print NR + 0 }' "$LOCK_DIR/episodes.new")"
  [ "$NEW_COUNT" -eq 1 ] || fail 31 "새 회차가 정확히 1개가 아님 (발견=$NEW_COUNT, 순서=${SLOT}/${DAILY_TARGET})"
  EPISODE="$(sed -n '1p' "$LOCK_DIR/episodes.new")"
  EPISODE_DIR="$KIT/episodes/$EPISODE"
  [ -s "$EPISODE_DIR/caption.md" ] || fail 32 "캡션 없음: $EPISODE"
  [ -d "$EPISODE_DIR/out" ] || fail 32 "PNG 폴더 없음: $EPISODE"
  find "$EPISODE_DIR/out" -maxdepth 1 -type f -name 'slide_*.png' | LC_ALL=C sort > "$LOCK_DIR/slides"
  SLIDE_COUNT="$(awk 'END { print NR + 0 }' "$LOCK_DIR/slides")"
  [ "$SLIDE_COUNT" -ge 6 ] || fail 32 "PNG 제작 미완료 (발견=${SLIDE_COUNT}장)"
  while IFS= read -r SLIDE; do
    [ -s "$SLIDE" ] || fail 32 "빈 PNG: $SLIDE"
  done < "$LOCK_DIR/slides"
  timed 300 "$KIT/.venv/bin/python" "$KIT/scripts/check_images.py" "$EPISODE_DIR" \
    >> "$LOG_FILE" 2>&1 || fail 33 "이미지·커버 자동 검수 실패"
  log "[verify] 제작 확인: $EPISODE (${SLIDE_COUNT}장 + caption.md)"

  STAGE="deliver_${SLOT}_of_${DAILY_TARGET}"
  COUNT_BEFORE_UPLOAD="$DRIVE_TODAY_COUNT"
  DEST_NAME="${TODAY_PREFIX}${EPISODE}"
  timed 600 bash "$KIT/scripts/upload_drive.sh" "$EPISODE_DIR" "$DEST_NAME" \
    >> "$LOG_FILE" 2>&1 || fail 40 "팀 드라이브 업로드 또는 Slack 알림 실패"

  STAGE="drive_verify_${SLOT}_of_${DAILY_TARGET}"
  refresh_drive_count
  [ "$DRIVE_TODAY_COUNT" -gt "$COUNT_BEFORE_UPLOAD" ] \
    || fail 41 "업로드 뒤 오늘 정상 전달 폴더 수가 늘지 않음 (${COUNT_BEFORE_UPLOAD}→${DRIVE_TODAY_COUNT})"
  log "[drive] 전달 확인: $EPISODE (${DRIVE_TODAY_COUNT}/${DAILY_TARGET})"
done

STAGE="complete"
FINAL_STATUS="SUCCESS"
exit 0
