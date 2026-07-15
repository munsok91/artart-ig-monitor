#!/bin/bash
###############################################################################
#  에이밍 데일리 카드뉴스 — 집맥(항상 켜진 맥) 설치 스크립트
#
#  사용법 (집맥 터미널 / OpenClaw):
#    curl -fsSL https://raw.githubusercontent.com/munsok91/artart-ig-monitor/main/aiming/install_aiming.sh | APIFY_TOKEN=xxxx bash
#
#  하는 일: 최신 킷 설치 → 폰트 → 렌더환경 → 하루 3개 quota-aware launchd 등록
#  비밀키는 이 저장소에 없음. APIFY_TOKEN 은 환경변수로 받는다.
###############################################################################
set -uo pipefail

RAW="https://raw.githubusercontent.com/munsok91/artart-ig-monitor/main/aiming"
KIT_REPO="https://github.com/munsok91/aiming-cardnews-kit.git"
KIT="$HOME/code/aiming-cardnews-kit"
ARTART="$HOME/code/artart-cardnews-automation"

echo ""
echo "================================================================"
echo "  에이밍 데일리 카드뉴스 설치 (매일 3개 자동 제작·팀 전달)"
echo "================================================================"

# ---------- 1) 공식 킷 설치·업데이트 ----------
mkdir -p "$KIT" "$ARTART"/src/{econ,publish} "$ARTART"/outputs/econ
mkdir -p "$HOME/.claude/skills/aiming-cardnews"

if [ -d "$KIT/.git" ]; then
  echo "· 공식 킷 업데이트 중..."
  GIT_TERMINAL_PROMPT=0 git -C "$KIT" pull --rebase --autostash -q \
    || { echo "❌ 공식 킷 업데이트 실패"; exit 1; }
else
  echo "· 기존 설치를 자동 업데이트 가능한 공식 킷으로 전환 중..."
  TMP_KIT="$(mktemp -d)"
  OLD_COVERED="$TMP_KIT/covered.old.json"
  [ -f "$KIT/episodes/.covered_topics.json" ] \
    && cp "$KIT/episodes/.covered_topics.json" "$OLD_COVERED"
  GIT_TERMINAL_PROMPT=0 git clone --depth 1 -q "$KIT_REPO" "$TMP_KIT/repo" \
    || { rm -rf "$TMP_KIT"; echo "❌ 공식 킷 다운로드 실패"; exit 1; }
  rsync -a "$TMP_KIT/repo/" "$KIT/"
  if [ -s "$OLD_COVERED" ]; then
    python3 - "$OLD_COVERED" "$KIT/episodes/.covered_topics.json" <<'PY'
import json
import sys

old_path, new_path = sys.argv[1:]
try:
    old = json.load(open(old_path, encoding="utf-8"))
except Exception:
    old = []
try:
    new = json.load(open(new_path, encoding="utf-8"))
except Exception:
    new = []
merged = {}
for item in new + old:
    if isinstance(item, dict):
        key = item.get("episode") or (item.get("date"), item.get("topic"))
        merged[str(key)] = item
items = sorted(merged.values(), key=lambda x: (x.get("date", ""), x.get("episode", "")))[-60:]
with open(new_path, "w", encoding="utf-8") as fh:
    json.dump(items, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY
  fi
  rm -rf "$TMP_KIT"
fi

mkdir -p "$ARTART"/src/{econ,publish} "$ARTART"/outputs/econ

fetch() { # fetch <원격경로> <로컬경로>
  curl -fsSL "$RAW/$1" -o "$2" || { echo "❌ 다운로드 실패: $1"; exit 1; }
}
fetch "skill/SKILL.md"               "$HOME/.claude/skills/aiming-cardnews/SKILL.md"
fetch "scripts/scrape_ig.py"         "$ARTART/src/econ/scrape_ig.py"
fetch "scripts/list_used.py"         "$ARTART/src/econ/list_used.py"
fetch "scripts/mark_used.py"         "$ARTART/src/econ/mark_used.py"
fetch "scripts/ig_api.py"            "$ARTART/src/publish/ig_api.py"
chmod +x "$KIT/auto/run_aiming_daily.sh"
echo "✓ 공식 킷 설치·업데이트 완료"

# ---------- 2) 토큰(.env) ----------
save_env() {
  local key="$1" value="$2"
  touch "$ARTART/.env"
  grep -q "^${key}=" "$ARTART/.env" 2>/dev/null \
    && sed -i '' "s|^${key}=.*|${key}=${value}|" "$ARTART/.env" \
    || printf '%s=%s\n' "$key" "$value" >> "$ARTART/.env"
}
if [ -n "${APIFY_TOKEN:-}" ]; then
  save_env APIFY_TOKEN "$APIFY_TOKEN"
  chmod 600 "$ARTART/.env"
  echo "✓ 소재 수집 열쇠(APIFY) 저장"
elif [ -f "$ARTART/.env" ] && grep -q "^APIFY_TOKEN=" "$ARTART/.env"; then
  echo "✓ 소재 수집 열쇠(APIFY) 이미 있음"
else
  echo "⚠️ APIFY_TOKEN 이 없어요. 소재 수집이 안 됩니다."
  echo "   다시 실행: curl -fsSL $RAW/install_aiming.sh | APIFY_TOKEN=<토큰> bash"
fi
[ -z "${SLACK_ECON_WEBHOOK_URL:-}" ] || save_env SLACK_ECON_WEBHOOK_URL "$SLACK_ECON_WEBHOOK_URL"
[ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || save_env CLAUDE_CODE_OAUTH_TOKEN "$CLAUDE_CODE_OAUTH_TOKEN"

# ---------- 3) 한글 폰트 (프리텐다드) ----------
if ! ls "$HOME/Library/Fonts/"Pretendard-*.ttf >/dev/null 2>&1; then
  echo "· 프리텐다드 폰트 설치 중..."
  TMP=$(mktemp -d)
  if curl -fsSL -o "$TMP/p.zip" "https://github.com/orioncactus/pretendard/releases/download/v1.3.9/Pretendard-1.3.9.zip"; then
    unzip -qo "$TMP/p.zip" -d "$TMP" && \
    find "$TMP" -name "Pretendard-*.ttf" -exec cp {} "$HOME/Library/Fonts/" \; && \
    echo "✓ 폰트 설치 완료"
  else
    echo "⚠️ 폰트 다운로드 실패 — 한글이 깨질 수 있어요. 수동 설치 필요."
  fi
  rm -rf "$TMP"
else
  echo "✓ 프리텐다드 폰트 이미 있음"
fi

# ---------- 4) 에이밍 전용 렌더 환경 ----------
VENV="$KIT/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "· 렌더 환경 설치 중... (5~10분 걸려요)"
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv "$VENV" && \
  "$VENV/bin/pip" -q install playwright pillow && \
  "$VENV/bin/playwright" install chromium
fi
if [ -x "$VENV/bin/python" ]; then echo "✓ 렌더 환경 준비 완료"; else echo "❌ 렌더 환경 설치 실패"; fi

# ---------- 5) 하루 3개 + 실패 시 재시도 일정 등록 ----------
PLIST="$HOME/Library/LaunchAgents/com.aiming.daily.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.aiming.daily</string>
    <key>ProgramArguments</key>
    <array><string>/bin/bash</string><string>$KIT/auto/run_aiming_daily.sh</string></array>
    <key>StartCalendarInterval</key>
    <array>
      <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>20</integer></dict>
      <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer></dict>
      <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
      <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    </array>
    <key>StandardOutPath</key><string>$KIT/logs/.launchd.log</string>
    <key>StandardErrorPath</key><string>$KIT/logs/.launchd.err.log</string>
</dict>
</plist>
XML
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" 2>/dev/null
launchctl list | grep -q com.aiming.daily && echo "✓ 매일 07:20 제작 + 10:30·14:00·18:00 부족분 재시도 등록" || echo "⚠️ launchd 등록 실패"

# ---------- 6) 점검 ----------
echo ""
echo "----------------------------------------------------------------"
NEED=0
command -v claude >/dev/null 2>&1 || { NEED=1; echo "⚠️ claude 없음 →  curl -fsSL https://claude.ai/install.sh | bash   후 'claude' 로그인"; }
[ -f "$HOME/.claude/.credentials.json" ] || [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || echo "ℹ️  무인실행 열쇠 필요시:  claude setup-token  → 결과를 $ARTART/.env 에 CLAUDE_CODE_OAUTH_TOKEN=... 로 추가"
command -v rclone >/dev/null 2>&1 \
  && rclone listremotes 2>/dev/null | grep -Fqx 'artartdrive:' \
  && echo "✓ 아트아트 투데이 드라이브 연결 확인" \
  || { NEED=1; echo "⚠️ artartdrive 연결 없음 — 기존 rclone 설정을 이 맥에 넣어야 합니다"; }
grep -q '^SLACK_ECON_WEBHOOK_URL=.' "$ARTART/.env" 2>/dev/null \
  && echo "✓ Slack 완료·실패 알림 연결 확인" \
  || { NEED=1; echo "⚠️ Slack 알림 연결이 없습니다"; }

if [ "$NEED" = "0" ]; then
  echo "✅ 설치 끝! 매일 카드뉴스가 3개가 될 때까지 만들고 팀에 알립니다."
else
  echo "위 ⚠️ 를 해결한 뒤 이 스크립트를 한 번 더 실행하면 확인됩니다."
fi
echo ""
echo "지금 바로 테스트:  bash $KIT/auto/run_aiming_daily.sh"
echo "끄기:              launchctl unload $PLIST"
echo "로그:              $KIT/logs/auto.log"
echo "----------------------------------------------------------------"
