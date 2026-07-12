#!/bin/bash
# 완성 회차를 구글드라이브 팀 검수함(에이밍 폴더)에 업로드.
# 두 가지 경로를 자동 판별:
#   1) 구글드라이브 데스크톱 앱이 있으면 → 동기화 폴더로 복사
#   2) 없고 rclone 이 설정돼 있으면 → rclone 으로 업로드 (sudo 불필요)
#   3) 둘 다 없으면 조용히 건너뜀 (제작본은 바탕화면에 남음)
#
# 사용법: bash scripts/upload_drive.sh <회차폴더> "<드라이브폴더명>"
#   예:   bash scripts/upload_drive.sh episodes/ep07_주제 "[에이밍] 2026-07-13_ep07_주제"
set -uo pipefail

SRC="${1:?회차 폴더 경로 필요}"
DEST_NAME="${2:?드라이브 폴더명 필요}"
RCLONE_REMOTE="${RCLONE_REMOTE:-artartdrive}"

# 올릴 파일: 슬라이드 PNG + 캡션
STAGE=$(mktemp -d)
cp "$SRC"/out/slide_*.png "$STAGE/" 2>/dev/null
cp "$SRC"/caption.md "$STAGE/캡션.md" 2>/dev/null
if [ -z "$(ls -A "$STAGE" 2>/dev/null)" ]; then
  echo "[drive] 올릴 파일이 없어요 ($SRC)"; rm -rf "$STAGE"; exit 0
fi

# --- 1) 드라이브 데스크톱 앱 ---
GD=$(ls -d "$HOME/Library/CloudStorage/GoogleDrive-"* 2>/dev/null | head -1)
if [ -n "$GD" ] && [ -d "$GD/내 드라이브" ]; then
  TARGET="$GD/내 드라이브/에이밍/$DEST_NAME"
  mkdir -p "$TARGET" && cp "$STAGE"/* "$TARGET/" && \
    echo "[drive] ✅ 드라이브 앱으로 업로드: 에이밍/$DEST_NAME"
  rm -rf "$STAGE"; exit 0
fi

# --- 2) rclone ---
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^${RCLONE_REMOTE}:"; then
  if rclone copy "$STAGE" "${RCLONE_REMOTE}:에이밍/$DEST_NAME" --drive-chunk-size 32M -q; then
    echo "[drive] ✅ rclone 으로 업로드: 에이밍/$DEST_NAME"
    rm -rf "$STAGE"; exit 0
  else
    echo "[drive] ⚠️ rclone 업로드 실패 — 제작본은 바탕화면에 있어요"
  fi
fi

echo "[drive] ℹ️ 드라이브 연결 없음 — 업로드 건너뜀 (제작본은 바탕화면에 있음)"
rm -rf "$STAGE"
exit 0
