#!/usr/bin/env python3
"""Generate the desktop shell icons into desktop/assets.

Pillow ships with AstrBot's dependencies, so this needs nothing extra.

Usage:
    uv run python desktop/scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIZE = 512


def build() -> Image.Image:
    """Draw the app icon: rounded square, speech bubble, lorebook spine.

    Returns:
        RGBA image at :data:`SIZE`.
    """
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = SIZE // 6
    draw.rounded_rectangle(
        (0, 0, SIZE - 1, SIZE - 1), radius=radius, fill=(16, 20, 24, 255)
    )
    draw.rounded_rectangle(
        (64, 96, SIZE - 176, 336),
        radius=44,
        fill=(47, 129, 247, 255),
    )
    draw.polygon([(128, 330), (128, 402), (206, 336)], fill=(47, 129, 247, 255))
    for y in (160, 216, 272):
        draw.rounded_rectangle((112, y, 300, y + 28), radius=14, fill=(230, 237, 243, 255))
    draw.rounded_rectangle((336, 176, 448, 400), radius=24, fill=(35, 134, 54, 255))
    draw.rectangle((336, 176, 366, 400), fill=(23, 89, 38, 255))
    for y in (216, 264, 312):
        draw.rounded_rectangle((388, y, 428, y + 16), radius=8, fill=(230, 237, 243, 210))
    return img


def main() -> int:
    """Write PNG and ICO assets.

    Returns:
        Process exit code.
    """
    ASSETS.mkdir(parents=True, exist_ok=True)
    img = build()
    png = ASSETS / "icon.png"
    img.save(png)
    img.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon-256.png")
    img.save(ASSETS / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    print(f"wrote {png.name}, icon-256.png, icon.ico -> {ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
