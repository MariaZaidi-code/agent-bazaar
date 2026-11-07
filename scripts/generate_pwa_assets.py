from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "web" / "static" / "pwa"

BLUE = (38, 73, 200, 255)
WHITE = (255, 255, 255, 255)
INK = (16, 17, 19, 255)


def logo(size: int, maskable: bool = False) -> Image.Image:
    image = Image.new("RGBA", (size, size), BLUE if maskable else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    safe = 0.62 if maskable else 0.66
    cell = int(size * safe / 2.55)
    gap = int(size * 0.035)
    left = (size - cell * 2 - gap) // 2
    top = left
    radius = max(2, int(cell * 0.16))
    if not maskable:
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=BLUE)
    for row in range(2):
        for col in range(2):
            x = left + col * (cell + gap)
            y = top + row * (cell + gap)
            draw.rounded_rectangle((x, y, x + cell, y + cell), radius=radius, fill=WHITE)
    return image


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        logo(size).save(TARGET / f"icon-{size}.png", optimize=True)
        logo(size, maskable=True).save(TARGET / f"maskable-{size}.png", optimize=True)
    logo(180).save(TARGET / "apple-touch-icon.png", optimize=True)
    logo(32).save(TARGET / "favicon-32.png", optimize=True)
    print(f"Wrote PWA icons to {TARGET}")


if __name__ == "__main__":
    main()
