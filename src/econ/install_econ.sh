#!/bin/bash
# 경제 소재공유방 데일리 발송 — 집맥 설치 스크립트 (원클릭)
#
#   curl -fsSL https://raw.githubusercontent.com/munsok91/artart-ig-monitor/main/src/econ/install_econ.sh \
#     | APIFY_TOKEN=xxx SLACK_ECON_WEBHOOK_URL=https://hooks.slack.com/... bash
#
# 이미 에이밍 설치를 했다면 APIFY_TOKEN 은 .env 에 있으므로 생략 가능.
# 비밀키는 이 저장소에 없다 — 전부 환경변수로 받는다.
#
# 하는 일:
#   1) 코드 내려받기 (src/econ/)
#   2) .env 에 토큰 채우기
#   3) 상태파일(.sent_history.json) 시드 — 이 맥북에서 넘어온 최근 발송 기록
#   4) launchd 2개 등록: 매일 15:00 시의성 / 금요일 15:05 교훈성
set -uo pipefail

RAW="https://raw.githubusercontent.com/munsok91/artart-ig-monitor/main"
ARTART="$HOME/code/artart-cardnews-automation"

echo "▶ 경제 소재공유 설치 시작 (계정: $(id -un), HOME=$HOME)"

# ---------- 1) 코드 ----------
mkdir -p "$ARTART/src/econ" "$ARTART/outputs/econ"
for f in scrape_ig.py econ_prompt.md econ_lesson_prompt.md run_econ.sh; do
  curl -fsSL "$RAW/src/econ/$f" -o "$ARTART/src/econ/$f" || { echo "❌ $f 내려받기 실패"; exit 1; }
done
chmod +x "$ARTART/src/econ/run_econ.sh"
echo "✓ 코드 준비 완료"

# ---------- 2) 토큰(.env) ----------
put_env() {  # put_env KEY VALUE
  local k="$1" v="$2"
  [ -z "$v" ] && return 0
  touch "$ARTART/.env"
  if grep -q "^${k}=" "$ARTART/.env" 2>/dev/null; then
    sed -i '' "s|^${k}=.*|${k}=${v}|" "$ARTART/.env"
  else
    echo "${k}=${v}" >> "$ARTART/.env"
  fi
  chmod 600 "$ARTART/.env"
}
put_env APIFY_TOKEN "${APIFY_TOKEN:-}"
put_env SLACK_ECON_WEBHOOK_URL "${SLACK_ECON_WEBHOOK_URL:-}"

miss=0
for k in APIFY_TOKEN SLACK_ECON_WEBHOOK_URL; do
  grep -q "^${k}=." "$ARTART/.env" 2>/dev/null || { echo "❌ ${k} 없음"; miss=1; }
done
grep -q "^CLAUDE_CODE_OAUTH_TOKEN=." "$ARTART/.env" 2>/dev/null \
  || echo "⚠️ CLAUDE_CODE_OAUTH_TOKEN 없음 — 무인 실행이 401 납니다. tmux 안에서 'claude setup-token' 후 .env 에 추가하세요."
[ "$miss" = 1 ] && { echo "   다시 실행: curl -fsSL $RAW/src/econ/install_econ.sh | APIFY_TOKEN=<토큰> SLACK_ECON_WEBHOOK_URL=<웹후크> bash"; exit 1; }
echo "✓ 토큰 확인 완료"

# ---------- 3) 상태파일 시드 (7일 중복차단 히스토리) ----------
HIST="$ARTART/outputs/econ/.sent_history.json"
if [ ! -f "$HIST" ]; then
  curl -fsSL "$RAW/src/econ/seed_sent_history.json" -o "$HIST" \
    && echo "✓ 발송 히스토리 시드 완료 (이 맥북이 최근 보낸 것과 중복 안 나게)" \
    || echo "⚠️ 시드 실패 — 빈 히스토리로 시작(며칠간 중복 나갈 수 있음)"
else
  echo "✓ 기존 히스토리 유지"
fi

# ---------- 4) launchd ----------
mk_plist() {  # mk_plist LABEL SLOT HOUR MINUTE [WEEKDAY]
  local label="$1" slot="$2" hh="$3" mm="$4" wd="${5:-}"
  local plist="$HOME/Library/LaunchAgents/${label}.plist"
  local cal="        <key>Hour</key><integer>${hh}</integer>
        <key>Minute</key><integer>${mm}</integer>"
  [ -n "$wd" ] && cal="$cal
        <key>Weekday</key><integer>${wd}</integer>"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${ARTART}/src/econ/run_econ.sh</string>
        <string>${slot}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
${cal}
    </dict>
    <key>StandardOutPath</key><string>${ARTART}/outputs/econ/.launchd.log</string>
    <key>StandardErrorPath</key><string>${ARTART}/outputs/econ/.launchd.err.log</string>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
PLIST
  launchctl unload "$plist" 2>/dev/null
  launchctl load "$plist" && echo "✓ 등록: ${label}"
}
mkdir -p "$HOME/Library/LaunchAgents"
mk_plist com.artart.econ.daily  daily  15 0
mk_plist com.artart.econ.lesson lesson 15 5 6   # Weekday 6 = 금요일

echo
echo "───────────────────────────────"
launchctl list | grep -i "artart.econ" || echo "⚠️ 등록 확인 실패"
echo "───────────────────────────────"
echo "✅ 완료. 매일 오후 3시 시의성 발송, 금요일 3시 5분 교훈성 발송."
echo "   지금 한번 테스트:  bash $ARTART/src/econ/run_econ.sh daily"
echo "   로그:              tail -40 $ARTART/outputs/econ/run.log"
