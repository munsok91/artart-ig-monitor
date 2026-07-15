"""에이밍 카드뉴스 이미지 중복·품질·커버 카피 검수기.

한 회차 안에서 (1) 같은 사진 파일 두 번 사용, (2) 같은 장면의 다른 프레임
(지각 해시 근접), (3) 지난 회차에서 이미 쓴 사진 재사용, (4) 커버 카피가
렌더에서 3줄로 터지는 것(2줄 초과·줄폭 초과)을 잡는다.
추가로 저해상도(가로 1200px 미만)·과암부(평균 밝기 40 미만) 사진을 경고한다.

사용:
    python3 scripts/check_images.py episodes/epNN_주제
    → FAIL이 하나라도 있으면 종료코드 1. 렌더·배달 전에 반드시 통과시킬 것.

CTA 고정 장표(aim-cta-official.jpg)는 모든 검사에서 제외.
"""
from __future__ import annotations

import pathlib
import re
import sys

from PIL import Image, ImageFont, ImageOps

KIT = pathlib.Path(__file__).resolve().parent.parent
CTA_NAME = "aim-cta-official.jpg"
NEAR_DUP_DISTANCE = 10   # dhash 해밍거리 이하면 같은 장면으로 판정
MIN_WIDTH = 1200
MIN_LUMA = 40

# 커버 카피 (design-system.css .cover .title 실측: 1080 - 72*2 여백)
COVER_MAX_LINES = 2
COVER_LINE_WIDTH = 936        # px
COVER_FONT_SIZE = 78          # px, weight 800
COVER_LETTER_SPACING = -1     # px
COVER_FONT_CANDIDATES = [
    pathlib.Path.home() / "Library/Fonts/Pretendard-ExtraBold.ttf",
    pathlib.Path("/Library/Fonts/Pretendard-ExtraBold.ttf"),
]


def dhash(path: pathlib.Path, size: int = 8) -> int:
    img = ImageOps.exif_transpose(Image.open(path)).convert("L")
    img = img.resize((size + 1, size), Image.LANCZOS)
    px = img.tobytes()
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def source_of(asset: pathlib.Path) -> pathlib.Path:
    """그레인 처리 전 원본이 있으면 원본으로 비교 (노이즈 영향 제거)."""
    orig = asset.with_name(asset.stem + "_원본" + asset.suffix)
    return orig if orig.exists() else asset


def html_image_refs(ep_dir: pathlib.Path) -> list[pathlib.Path]:
    """회차 HTML에서 장표 순서대로 assets/ 이미지 참조를 뽑는다."""
    htmls = sorted(ep_dir.glob("ep*.html"))
    if not htmls:
        sys.exit(f"HTML을 못 찾음: {ep_dir}/epNN.html")
    text = htmls[0].read_text(encoding="utf-8")
    refs = re.findall(r"assets/[^\"'\)\s]+\.(?:jpg|jpeg|png|webp)", text, re.I)
    out = []
    for ref in refs:
        name = pathlib.Path(ref).name
        if name == CTA_NAME or name.endswith("_원본.jpg"):
            continue
        p = ep_dir / "assets" / name
        out.append(p if p.exists() else KIT / ref)
    return out


def text_width(text: str) -> float:
    """커버 폰트(Pretendard ExtraBold 78px, 자간 -1px)로 렌더될 줄 폭 추정."""
    for cand in COVER_FONT_CANDIDATES:
        if cand.exists():
            font = ImageFont.truetype(str(cand), COVER_FONT_SIZE)
            w = font.getlength(text)
            break
    else:
        # 폰트 없는 기기(집맥 등) 폴백: 글자 부류별 폭 추정
        w = 0.0
        for ch in text:
            if ch == " ":
                w += COVER_FONT_SIZE * 0.26
            elif ord(ch) < 0x2000:   # 라틴·숫자·문장부호
                w += COVER_FONT_SIZE * 0.55
            else:                    # 한글 등 전각
                w += COVER_FONT_SIZE * 0.98
    return w + COVER_LETTER_SPACING * max(len(text) - 1, 0)


def check_cover_copy(ep_dir: pathlib.Path, fails: list[str]) -> None:
    """커버 .title이 렌더 기준 2줄로 끝나는지 — 3줄 터짐 방지 (2026-07-14 지시)."""
    htmls = sorted(ep_dir.glob("ep*.html"))
    if not htmls:
        return
    text = htmls[0].read_text(encoding="utf-8")
    m = re.search(r'class="title"[^>]*>(.*?)</div>', text, re.S)
    if not m:
        return
    lines = [re.sub(r"<[^>]+>", "", seg).strip()
             for seg in re.split(r"<br\s*/?>", m.group(1))]
    lines = [l for l in lines if l]
    if len(lines) > COVER_MAX_LINES:
        fails.append(f"커버 카피 {len(lines)}줄 — 2줄(흰+민트)로 끝낼 것: {lines}")
    for line in lines:
        w = text_width(line)
        if w > COVER_LINE_WIDTH:
            fails.append(
                f"커버 줄폭 초과: \"{line}\" ≈{w:.0f}px (한도 {COVER_LINE_WIDTH}px) — "
                f"렌더에서 줄바꿈돼 3줄이 됨. 카피를 줄일 것"
            )


def episode_hashes(ep_dir: pathlib.Path) -> dict[str, int]:
    """회차 assets/ 안 배경사진(원본 우선)의 지각 해시."""
    hashes = {}
    assets = ep_dir / "assets"
    if not assets.is_dir():
        return hashes
    for p in sorted(assets.iterdir()):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        if p.name == CTA_NAME or p.stem.endswith("_원본"):
            continue
        try:
            hashes[p.name] = dhash(source_of(p))
        except OSError:
            pass
    return hashes


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("사용법: python3 scripts/check_images.py episodes/epNN_주제")
    ep_dir = pathlib.Path(sys.argv[1]).resolve()
    if not ep_dir.is_dir():
        sys.exit(f"폴더 없음: {ep_dir}")

    fails: list[str] = []
    warns: list[str] = []

    # 1) 한 회차 안에서 같은 파일 두 번 사용
    refs = html_image_refs(ep_dir)
    seen: dict[str, int] = {}
    for i, p in enumerate(refs, start=1):
        if p.name in seen:
            fails.append(
                f"같은 사진 재사용: {p.name} — 장표 {seen[p.name]}번과 {i}번에 중복. "
                f"장표마다 다른 사진을 넣을 것"
            )
        else:
            seen[p.name] = i

    # 2) 같은 장면의 다른 프레임 (지각 해시 근접)
    hashes = episode_hashes(ep_dir)
    names = sorted(hashes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            d = hamming(hashes[a], hashes[b])
            if d <= NEAR_DUP_DISTANCE:
                fails.append(
                    f"사실상 같은 장면: {a} ↔ {b} (해시거리 {d}). "
                    f"같은 촬영 컷의 다른 프레임은 중복으로 침 — 둘 중 하나 교체"
                )

    # 3) 지난 회차에서 쓴 사진 재사용
    episodes_root = ep_dir.parent
    for other in sorted(episodes_root.iterdir()):
        if not other.is_dir() or other == ep_dir:
            continue
        for oname, ohash in episode_hashes(other).items():
            for name, h in hashes.items():
                d = hamming(h, ohash)
                if d <= NEAR_DUP_DISTANCE:
                    fails.append(
                        f"지난 회차 사진 재탕: {name} ↔ {other.name}/{oname} (해시거리 {d})"
                    )

    # 4) 커버 카피 2줄 초과 / 줄폭 초과 (렌더 시 3줄 방지)
    check_cover_copy(ep_dir, fails)

    # 5) 품질 경고: 저해상도·과암부 (원본 기준)
    for p in refs:
        if not p.exists():
            fails.append(f"HTML이 참조하는 파일 없음: {p}")
            continue
        src = source_of(p)
        try:
            img = ImageOps.exif_transpose(Image.open(src))
        except OSError:
            continue
        if img.width < MIN_WIDTH:
            warns.append(f"저해상도: {src.name} 가로 {img.width}px (기준 {MIN_WIDTH}px+)")
        luma = ImageOps.exif_transpose(Image.open(p)).convert("L").resize((64, 64))
        mean = sum(luma.tobytes()) / (64 * 64)
        if mean < MIN_LUMA:
            warns.append(
                f"너무 어두움: {p.name} 평균 밝기 {mean:.0f} (기준 {MIN_LUMA}+) — "
                f"딤 오버레이 겹치면 사진이 안 보임"
            )

    for w in warns:
        print(f"⚠️  WARN {w}")
    for f in fails:
        print(f"❌ FAIL {f}")
    if fails:
        print(f"\n검수 실패 {len(fails)}건 — 사진 교체 후 다시 실행")
        sys.exit(1)
    print(f"✅ 이미지 검수 통과 ({len(refs)}장, 경고 {len(warns)}건)")


if __name__ == "__main__":
    main()
