# -*- coding: utf-8 -*-
"""에이밍(@aim___ing) 인스타 계정 연결 — 메타 토큰 붙여넣으면 끝."""
import os
import sys
import time
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
os.environ["IG_CONFIG"] = str(KIT_ROOT / "config" / "instagram.json")
sys.path.insert(0, str(Path.home() / "code" / "artart-cardnews-automation" / "src" / "publish"))
from ig_api import IgError, api_get, save_config  # noqa: E402


def main():
    print("=" * 46)
    print("  에이밍(@aim___ing) 인스타 계정 연결")
    print("=" * 46)
    print()
    print("⚠️ 꼭 '에이밍' 계정으로 발급받은 토큰을 넣어 주세요.")
    print("   (아트아트 토큰을 넣으면 아트아트 계정에 올라갑니다!)")
    print()
    token = input("토큰 붙여넣기 → ").strip()
    if len(token) < 30:
        print("\n❌ 토큰이 너무 짧아요. 다시 복사해서 실행해 주세요.")
        sys.exit(1)

    cfg = {"host": "graph.instagram.com", "access_token": token, "refreshed_at": time.time()}
    print("\n연결 확인 중...")
    try:
        me = api_get(cfg, "me", {"fields": "user_id,username"})
    except IgError as e:
        print(f"\n❌ 연결 실패: {e}")
        sys.exit(1)

    cfg["ig_user_id"] = str(me.get("user_id") or me.get("id"))
    cfg["username"] = me.get("username", "")
    print()
    if "aim" not in cfg["username"].lower():
        print(f"⚠️ 연결된 계정이 @{cfg['username']} 인데, 에이밍 계정이 아닌 것 같아요.")
        ok = input("   그래도 이 계정으로 저장할까요? y 입력 → ").strip().lower()
        if ok != "y":
            print("저장하지 않았어요.")
            sys.exit(0)
    save_config(cfg)
    print(f"✅ 연결 완료! → @{cfg['username']}")
    print("이제 매일 아침 자동 발행이 실제로 올라갑니다.")


if __name__ == "__main__":
    main()
