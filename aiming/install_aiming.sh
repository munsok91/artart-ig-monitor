#!/bin/bash
###############################################################################
#  에이밍 데일리 카드뉴스 — 집맥(항상 켜진 맥) 설치 스크립트
#
#  사용법 (집맥 터미널 / OpenClaw):
#    curl -fsSL https://raw.githubusercontent.com/munsok91/artart-ig-monitor/main/aiming/install_aiming.sh | APIFY_TOKEN=xxxx bash
#
#  하는 일: 킷 설치 → 폰트 → 렌더환경(playwright) → 매일 07:20 launchd 등록
#  비밀키는 이 저장소에 없음. APIFY_TOKEN 은 환경변수로 받는다.
###############################################################################
set -uo pipefail

RAW="https://raw.githubusercontent.com/munsok91/artart-ig-monitor/main/aiming"
KIT="$HOME/code/aiming-cardnews-kit"
ARTART="$HOME/code/artart-cardnews-automation"

echo ""
echo "================================================================"
echo "  에이밍 데일리 카드뉴스 설치 (매일 아침 7:20 이 맥에서 자동 제작)"
echo "================================================================"

# ---------- 1) 킷 파일 내려받기 ----------
mkdir -p "$KIT"/{scripts,templates,docs,auto,assets,episodes,logs,config}
mkdir -p "$ARTART"/src/{econ,publish} "$ARTART"/outputs/econ
mkdir -p "$HOME/.claude/skills/aiming-cardnews"

fetch() { # fetch <원격경로> <로컬경로>
  curl -fsSL "$RAW/$1" -o "$2" || { echo "❌ 다운로드 실패: $1"; exit 1; }
}
echo "· 킷 파일 받는 중..."
for f in render.py artart_grain.py publish_aiming.py setup_token_aiming.py; do
  fetch "scripts/$f" "$KIT/scripts/$f"
done
fetch "templates/base.html"          "$KIT/templates/base.html"
fetch "docs/CONTENT_PLAYBOOK.md"     "$KIT/docs/CONTENT_PLAYBOOK.md"
fetch "auto/aiming_daily_prompt.md"  "$KIT/auto/aiming_daily_prompt.md"
fetch "auto/run_aiming_daily.sh"     "$KIT/auto/run_aiming_daily.sh"
fetch "assets/aim-cta-official.jpg"  "$KIT/assets/aim-cta-official.jpg"
fetch "assets/aim-app-card.png"      "$KIT/assets/aim-app-card.png"
fetch "assets/design-system.css"     "$KIT/assets/design-system.css"
fetch "skill/SKILL.md"               "$HOME/.claude/skills/aiming-cardnews/SKILL.md"
fetch "scripts/scrape_ig.py"         "$ARTART/src/econ/scrape_ig.py"
fetch "scripts/ig_api.py"            "$ARTART/src/publish/ig_api.py"
chmod +x "$KIT/auto/run_aiming_daily.sh"
echo "✓ 킷 설치 완료"

# ---------- 2) 토큰(.env) ----------
if [ -n "${APIFY_TOKEN:-}" ]; then
  touch "$ARTART/.env"
  grep -q "^APIFY_TOKEN=" "$ARTART/.env" 2>/dev/null \
    && sed -i '' "s|^APIFY_TOKEN=.*|APIFY_TOKEN=$APIFY_TOKEN|" "$ARTART/.env" \
    || echo "APIFY_TOKEN=$APIFY_TOKEN" >> "$ARTART/.env"
  chmod 600 "$ARTART/.env"
  echo "✓ 소재 수집 열쇠(APIFY) 저장"
elif [ -f "$ARTART/.env" ] && grep -q "^APIFY_TOKEN=" "$ARTART/.env"; then
  echo "✓ 소재 수집 열쇠(APIFY) 이미 있음"
else
  echo "⚠️ APIFY_TOKEN 이 없어요. 소재 수집이 안 됩니다."
  echo "   다시 실행: curl -fsSL $RAW/install_aiming.sh | APIFY_TOKEN=<토큰> bash"
fi

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

# ---------- 4) 렌더 환경 (playwright + chromium) ----------
VENV="$HOME/code/wellha-wellness-kit/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "· 렌더 환경 설치 중... (5~10분 걸려요)"
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv "$VENV" && \
  "$VENV/bin/pip" -q install playwright && \
  "$VENV/bin/playwright" install chromium
fi
if [ -x "$VENV/bin/python" ]; then echo "✓ 렌더 환경 준비 완료"; else echo "❌ 렌더 환경 설치 실패"; fi

# ---------- 5) 매일 07:20 자동 실행 등록 ----------
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
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>20</integer></dict>
    <key>StandardOutPath</key><string>$KIT/logs/.launchd.log</string>
    <key>StandardErrorPath</key><string>$KIT/logs/.launchd.err.log</string>
</dict>
</plist>
XML
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" 2>/dev/null
launchctl list | grep -q com.aiming.daily && echo "✓ 매일 아침 7:20 자동 실행 등록" || echo "⚠️ launchd 등록 실패"

# ---------- 6) 점검 ----------
echo ""
echo "----------------------------------------------------------------"
NEED=0
command -v claude >/dev/null 2>&1 || { NEED=1; echo "⚠️ claude 없음 →  curl -fsSL https://claude.ai/install.sh | bash   후 'claude' 로그인"; }
[ -f "$HOME/.claude/.credentials.json" ] || [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || echo "ℹ️  무인실행 열쇠 필요시:  claude setup-token  → 결과를 $ARTART/.env 에 CLAUDE_CODE_OAUTH_TOKEN=... 로 추가"
ls -d "$HOME/Library/CloudStorage/GoogleDrive-"* >/dev/null 2>&1 \
  && echo "✓ 구글 드라이브 앱 감지 — 팀 검수함 업로드 됨" \
  || { NEED=1; echo "⚠️ 구글 드라이브 앱 없음 → google.com/drive/download 설치 후 main.artart@gmail.com 로그인 (팀 검수함 업로드용)"; }

if [ "$NEED" = "0" ]; then
  echo "✅ 설치 끝! 내일 아침 7:20부터 이 맥이 알아서 만들고 올립니다."
else
  echo "위 ⚠️ 를 해결한 뒤 이 스크립트를 한 번 더 실행하면 확인됩니다."
fi
echo ""
echo "지금 바로 테스트:  bash $KIT/auto/run_aiming_daily.sh"
echo "끄기:              launchctl unload $PLIST"
echo "로그:              $KIT/logs/auto.log"
echo "----------------------------------------------------------------"
