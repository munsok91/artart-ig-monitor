"""에이밍 배경사진용 아트아트 그레이니 필름 필터.

artart-cardnews-automation/src/render/cover_filter.py와 동일 계열
(채도↓, 대비↑, 블랙 리프트, 필름 그레인, 비네트).
커버는 strength 27(아트아트 확정값), 본문은 16(텍스트 가독 우선).

사용:
    python3 scripts/artart_grain.py episodes/epNN_주제/assets/
    → 폴더 안 모든 jpg에 적용, 원본은 *_원본.jpg로 백업.
      파일명이 cover*로 시작하면 27, 아니면 16.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

COVER_STRENGTH = 27
BODY_STRENGTH = 16


def film_grain(img: Image.Image, strength: float) -> Image.Image:
    arr = np.array(img).astype(np.int16)
    noise = np.random.normal(0, strength, arr.shape[:2])
    n_img = Image.fromarray(np.clip(noise + 128, 0, 255).astype(np.uint8))
    n_img = n_img.filter(ImageFilter.GaussianBlur(0.5))
    noise = np.array(n_img).astype(np.int16) - 128
    arr = arr + noise[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_grainy(src: pathlib.Path, dst: pathlib.Path, strength: float) -> pathlib.Path:
    im = Image.open(src).convert("RGB")

    im = ImageEnhance.Color(im).enhance(0.78)
    im = ImageEnhance.Contrast(im).enhance(1.10)
    arr = np.array(im).astype(np.float32)
    arr = arr * (230 / 255) + 16  # 블랙 리프트 + 하이라이트 소프트
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    im = film_grain(im, strength)

    w, h = im.size
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    vig = 1 - 0.18 * np.clip(d - 0.55, 0, 1) / 0.85
    arr = np.array(im).astype(np.float32) * vig[:, :, None]
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    im.save(dst, quality=92)
    return dst


def main():
    folder = pathlib.Path(sys.argv[1])
    for p in sorted(folder.glob("*.jpg")):
        if p.stem.endswith("_원본"):
            continue
        backup = p.with_name(p.stem + "_원본.jpg")
        if not backup.exists():
            p.rename(backup)
        strength = COVER_STRENGTH if p.stem.startswith("cover") else BODY_STRENGTH
        apply_grainy(backup, p, strength)
        print(f"✓ {p.name} (strength {strength})")


if __name__ == "__main__":
    main()
