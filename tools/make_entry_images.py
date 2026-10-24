"""會員通（LINE Member Kit）：產生「我的課程」上方入口（🧭 課程入口）的底圖，輸出到 assets/entries/。

入口是選單功能，畫面刻意簡單：鮮豔的霓虹漸層＋一個發光圖示，左下留給頁面疊上的文字（圖裡不放字）。
1280 × 720（16:9）；單數個入口時最後一格會變成整排寬，頁面會裁掉上下，所以圖示放在右上（下方留給放大的標題），整排寬那格頁面會取圖的上半部（object-position）。
Notion「🧭 課程入口」的「圖片」貼這些檔案在 GitHub Pages 的網址。換客戶時改 ENTRIES。執行：python3 tools/make_entry_images.py
"""
import math

from PIL import Image, ImageDraw, ImageFilter

from make_richmenus import ROOT

W, H = 1280, 720
# 檔名、漸層（左上 → 右下）、圖示、圖示顏色
ENTRIES = [
    ("free", ("#2B0A5E", "#E0249A"), "play", "#FFD6F5"),
    ("member", ("#06225E", "#1E9BFF"), "cap", "#C9F1FF"),
    ("premium", ("#3A0A4F", "#FF8A00"), "crown", "#FFF1B8"),
    ("ebook", ("#003B4F", "#00D1C1"), "book", "#D9FFF9"),
    ("tools", ("#1A0B5E", "#8A3CFF"), "spark", "#F0E2FF"),
]


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def gradient(c1, c2):
    a, b = rgb(c1), rgb(c2)
    g = Image.new("RGB", (W, H))
    px = g.load()
    for y in range(H):
        for x in range(0, W, 4):
            t = min(1, max(0, (x / W) * 0.8 + (y / H) * 0.2)) ** 1.4
            col = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            for dx in range(4):
                px[x + dx, y] = col
    return g


def icon(kind, cx, cy, s, d):
    """白色實心圖示，畫在單獨圖層上，之後加光暈"""
    if kind == "play":
        d.ellipse([cx - s, cy - s, cx + s, cy + s], outline=255, width=int(s * 0.12))
        r = s * 0.5
        d.polygon([(cx - r * 0.6, cy - r), (cx - r * 0.6, cy + r), (cx + r, cy)], fill=255)
    elif kind == "cap":
        d.polygon([(cx - s, cy - s * 0.2), (cx, cy - s * 0.7), (cx + s, cy - s * 0.2), (cx, cy + s * 0.3)], fill=255)
        d.rectangle([cx - s * 0.55, cy + s * 0.05, cx + s * 0.55, cy + s * 0.55], fill=255)
        d.line([(cx + s * 0.8, cy - s * 0.1), (cx + s * 0.8, cy + s * 0.6)], fill=255, width=int(s * 0.08))
    elif kind == "crown":
        pts = [(cx - s, cy + s * 0.5), (cx - s, cy - s * 0.5), (cx - s * 0.5, cy), (cx, cy - s * 0.75),
               (cx + s * 0.5, cy), (cx + s, cy - s * 0.5), (cx + s, cy + s * 0.5)]
        d.polygon(pts, fill=255)
        for x in (cx - s, cx, cx + s):
            y = cy - s * (0.75 if x == cx else 0.5)
            d.ellipse([x - s * 0.12, y - s * 0.12, x + s * 0.12, y + s * 0.12], fill=255)
    elif kind == "book":
        w = int(s * 0.1)
        d.polygon([(cx, cy - s * 0.45), (cx - s, cy - s * 0.7), (cx - s, cy + s * 0.55), (cx, cy + s * 0.75)], outline=255, width=w)
        d.polygon([(cx, cy - s * 0.45), (cx + s, cy - s * 0.7), (cx + s, cy + s * 0.55), (cx, cy + s * 0.75)], outline=255, width=w)
        for i in range(3):
            y = cy - s * 0.25 + i * s * 0.28
            d.line([(cx - s * 0.75, y - s * 0.12), (cx - s * 0.2, y)], fill=255, width=w // 2)
            d.line([(cx + s * 0.2, y), (cx + s * 0.75, y - s * 0.12)], fill=255, width=w // 2)
    elif kind == "spark":
        def star(x, y, r):
            k = r * 0.22
            d.polygon([(x, y - r), (x + k, y - k), (x + r, y), (x + k, y + k), (x, y + r), (x - k, y + k), (x - r, y), (x - k, y - k)], fill=255)
        star(cx - s * 0.15, cy + s * 0.1, s * 0.85)
        star(cx + s * 0.75, cy - s * 0.6, s * 0.35)
        star(cx + s * 0.8, cy + s * 0.65, s * 0.22)


def draw(colors, kind, tint):
    img = gradient(*colors)
    # 圖示後面一團同色系的光，讓背景有層次（不用白色，顏色才不會被洗淡）
    blob = Image.new("L", (W, H), 0)
    ImageDraw.Draw(blob).ellipse([W * 0.5, H * 0.05, W * 0.95, H * 0.95], fill=150)
    img.paste(Image.new("RGB", (W, H), rgb(colors[1])), (0, 0), blob.filter(ImageFilter.GaussianBlur(120)))
    # 細的光線
    lines = Image.new("L", (W, H), 0)
    ld = ImageDraw.Draw(lines)
    for i in range(7):
        y0 = H * (0.15 + i * 0.12)
        ld.line([(0, y0 + 120), (W, y0 - 120)], fill=60, width=2)
    img.paste(Image.new("RGB", (W, H), rgb(tint)), (0, 0), lines.filter(ImageFilter.GaussianBlur(1.5)))
    # 圖示＋光暈
    cx, cy, s = W * 0.84, H * 0.36, H * 0.18
    mask = Image.new("L", (W, H), 0)
    icon(kind, cx, cy, s, ImageDraw.Draw(mask))
    glow_col = Image.new("RGB", (W, H), rgb(tint))
    for r, a in ((60, 0.9), (25, 0.9), (8, 1.0)):
        g = mask.filter(ImageFilter.GaussianBlur(r)).point(lambda v, a=a: int(min(255, v * a * 1.6)))
        img.paste(glow_col, (0, 0), g)
    img.paste(Image.new("RGB", (W, H), (255, 255, 255)), (0, 0), mask)
    return img


if __name__ == "__main__":
    out = ROOT / "assets" / "entries"
    out.mkdir(parents=True, exist_ok=True)
    for name, colors, kind, tint in ENTRIES:
        p = out / f"{name}.jpg"
        draw(colors, kind, tint).save(p, quality=85)
        print(p.relative_to(ROOT), p.stat().st_size)
