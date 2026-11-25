"""챙김 아이콘(C 도장)을 그린다: icons/icon.svg, icon-192.png, icon-512.png, maskable-512.png, apple-touch-icon.png
사용: python tools/make_icons.py (Pillow 필요). 4배로 크게 그린 뒤 줄여서 가장자리를 매끄럽게 한다."""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "icons")
PAPER, INK = (247, 246, 243, 255), (31, 78, 140, 255)


def stamp(size, rounded, scale=4):
    s = size * scale
    k = s / 192  # 192 기준 좌표를 늘림
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=44 * k, fill=PAPER)
    else:  # maskable: 꽉 찬 바탕, 그림은 가운데 안전 영역 안
        d.rectangle([0, 0, s, s], fill=PAPER)
    c = 96 * k
    for r, w in ((54, 8), (42, 2.5)):
        d.ellipse([c - r * k, c - r * k, c + r * k, c + r * k], outline=INK, width=round(w * k))
    pts = [(74 * k, 97 * k), (89 * k, 111 * k), (119 * k, 81 * k)]
    w = round(10 * k)
    d.line(pts, fill=INK, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):  # 둥근 끝
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=INK)
    return img.resize((size, size), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192" width="192" height="192">
  <rect width="192" height="192" rx="44" fill="#F7F6F3"/>
  <circle cx="96" cy="96" r="54" fill="none" stroke="#1F4E8C" stroke-width="8"/>
  <circle cx="96" cy="96" r="42" fill="none" stroke="#1F4E8C" stroke-width="2.5"/>
  <path d="M74 97l15 14 30-30" fill="none" stroke="#1F4E8C" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "icon.svg"), "w", encoding="utf-8").write(SVG)
stamp(192, True).save(os.path.join(OUT, "icon-192.png"))
stamp(512, True).save(os.path.join(OUT, "icon-512.png"))
stamp(512, False).save(os.path.join(OUT, "maskable-512.png"))
stamp(180, False).convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"))  # 아이폰은 투명 대신 바탕색
print("icons:", sorted(os.listdir(OUT)))
