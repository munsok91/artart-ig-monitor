# -*- coding: utf-8 -*-
"""에이밍(@aim___ing) 카드뉴스 인스타 자동 발행.

artart-cardnews-automation 의 인스타 발행 모듈(ig_api)을 재사용하되,
에이밍 전용 계정 설정(config/instagram.json — 이 키트 안)을 쓴다.

사용법:
  python3 scripts/publish_aiming.py                       # 최신 에피소드 발행 (확인 질문 있음)
  python3 scripts/publish_aiming.py episodes/ep05_주제     # 특정 에피소드
  python3 scripts/publish_aiming.py --yes                  # 무인 발행 (launchd 자동화용)
  python3 scripts/publish_aiming.py episodes/ep05 --force  # 이미 발행된 회차 재발행
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = KIT_ROOT / "config" / "instagram.json"
LOG_PATH = KIT_ROOT / "logs" / "publish.log"

# ig_api 는 import 시점에 IG_CONFIG 를 읽으므로 import 전에 지정해야 한다.
os.environ["IG_CONFIG"] = str(CONFIG_PATH)
sys.path.insert(0, str(Path.home() / "code" / "artart-cardnews-automation" / "src" / "publish"))
from ig_api import (IgError, delete_temp_image, load_config,  # noqa: E402
                    publish_carousel, refresh_token_if_needed, upload_temp_image)


def log(msg):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {msg}\n")
    print(msg)


def latest_episode():
    eps = sorted(
        [d for d in (KIT_ROOT / "episodes").iterdir()
         if d.is_dir() and re.match(r"ep\d+", d.name)],
        key=lambda d: d.name,
    )
    return eps[-1] if eps else None


def to_jpeg(png_path, out_dir):
    out = Path(out_dir) / (png_path.stem + ".jpg")
    r = subprocess.run(
        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "92",
         str(png_path), "--out", str(out)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not out.exists():
        raise IgError(f"이미지 변환 실패 ({png_path.name}): {r.stderr.strip()[:200]}")
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    auto_yes = "--yes" in sys.argv
    force = "--force" in sys.argv

    folder = Path(args[0]).expanduser().resolve() if args else latest_episode()
    if not folder or not folder.is_dir():
        log("❌ 발행할 에피소드 폴더가 없어요.")
        sys.exit(1)

    lock = folder / ".published.json"
    if lock.exists() and not force:
        info = json.loads(lock.read_text(encoding="utf-8"))
        log(f"⏭️  {folder.name} 은 이미 발행됨({info.get('published_at', '?')}) — 건너뜀. 재발행은 --force.")
        sys.exit(0)

    slides = sorted((folder / "out").glob("slide_*.png"))
    if not slides:
        log(f"❌ {folder.name}/out/ 에 슬라이드 PNG가 없어요. 렌더부터 해주세요.")
        sys.exit(1)
    if len(slides) > 10:
        slides = slides[:10]

    caption_file = folder / "caption.md"
    if not caption_file.exists():
        log(f"❌ {folder.name}/caption.md 가 없어요. 캡션 없이는 올리지 않습니다.")
        sys.exit(1)
    caption = caption_file.read_text(encoding="utf-8").strip()
    # "## 발행 캡션" 섹션이 있으면 그 부분만, 없으면 파일 전체.
    m = re.search(r"^##\s*발행 캡션.*?\n(.*?)(?=^##\s|\Z)", caption, re.M | re.S)
    if m:
        caption = m.group(1).strip()

    try:
        cfg = load_config()
    except IgError:
        log("⏸️  에이밍 인스타 계정이 아직 연결 안 됨 — 발행 건너뜀 (제작본은 폴더에 있음).")
        log("    연결: '에이밍 인스타 계정 연결.command' 더블클릭 후 토큰 붙여넣기.")
        sys.exit(0)
    cfg = refresh_token_if_needed(cfg)

    log(f"📂 발행 대상: {folder.name} ({len(slides)}장) → @{cfg.get('username', '?')}")
    if not auto_yes:
        ok = input("이대로 발행할까요? y 입력 → ").strip().lower()
        if ok != "y":
            print("취소했어요.")
            sys.exit(0)

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-aim-" + uuid.uuid4().hex[:6]
    uploaded = []
    try:
        urls = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, png in enumerate(slides, 1):
                jpg = to_jpeg(png, tmp)
                remote = f"{run_id}/{jpg.name}"
                url, sha = upload_temp_image(jpg, remote)
                uploaded.append((remote, sha))
                urls.append(url)
        media_id, link = publish_carousel(cfg, urls, caption, on_progress=log)
        lock.write_text(json.dumps({
            "media_id": media_id, "link": link,
            "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"✅ 발행 완료: {link or media_id}")
    except IgError as e:
        log(f"❌ 발행 실패: {e}")
        sys.exit(1)
    finally:
        for remote, sha in uploaded:
            delete_temp_image(remote, sha)


if __name__ == "__main__":
    main()
