"""會員通（LINE Member Kit）：產生三張圖文選單圖片（2500 × 1686，上排三格、下排一整塊），輸出到 assets/richmenu/。

- guest.png：訪客選單（非會員、審核中、已到期、停權）  上排：最新消息｜課程介紹｜AI 小幫手　下排：申請加入
- member.png：會員選單（一般會員、高級會員）          上排：最新消息｜我的課程｜AI 小幫手　下排：會員專區
- admin.png：管理者選單（名冊「角色」勾管理者）         上排：和會員相同　　　　　　　　　 下排：管理會員

主色與標誌文字讀 tools/config.local.json 的 brand（和 Notion「前台設定」的主色、標誌文字一致）。
產生後推上 GitHub，Notion「前台設定」的三個選單圖欄位指向這些圖；要換成自己設計的圖，直接在 Notion 換掉即可，
再到 Make 執行一次「{專案}｜會員：建立圖文選單（手動執行）」。格子位置寫在 tools/make_blueprints.py 的 COLS、ROW，兩邊要一致。

執行：python3 tools/make_richmenus.py
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tools" / "config.local.json").read_text(encoding="utf-8"))
BRAND = CFG.get("brand", {})
W, H, ROW = 2500, 1686, 843
COLS = [0, 833, 1667, 2500]   # 三欄的邊界，和 make_blueprints.py 的 COLS 一致


def first_font(*faces):
    """回傳第一個存在的字型（檔案, 第幾個字體）；Windows 用微軟正黑體，Mac 用冬青黑體"""
    return next((f for f in faces if Path(f[0]).exists()), faces[0])


def font(face, size):
    return ImageFont.truetype(face[0], size, index=face[1])


MAC_FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"   # 0＝W3、2＝W6
FONT = first_font((r"C:\Windows\Fonts\msjhbd.ttc", 0), (MAC_FONT, 2))   # 粗體
FONT_REG = first_font((r"C:\Windows\Fonts\msjh.ttc", 0), (MAC_FONT, 0))


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ---- 圖示：用線條畫，不依賴 emoji 字型 ----
def news(d, cx, cy, s, col):
    lw = int(s * 0.09)
    w, h = s * 1.3, s * 1.0
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=s * 0.12, outline=col, width=lw)
    d.rectangle([cx - w / 2 + s * 0.18, cy - h / 2 + s * 0.18, cx - s * 0.05, cy], fill=col)
    for i, y in enumerate((-0.28, -0.1, 0.12, 0.3)):
        x0 = cx + s * 0.08 if i < 2 else cx - w / 2 + s * 0.18
        d.line([(x0, cy + y * s), (cx + w / 2 - s * 0.18, cy + y * s)], fill=col, width=int(lw * 0.8))


def play(d, cx, cy, s, col):
    lw = int(s * 0.09)
    w, h = s * 1.4, s * 0.95
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=s * 0.16, outline=col, width=lw)
    r = s * 0.26
    d.polygon([(cx - r * 0.6, cy - r), (cx - r * 0.6, cy + r), (cx + r, cy)], fill=col)


def sparkle(d, cx, cy, s, col):
    def star(x, y, r):
        k = r * 0.22
        d.polygon([(x, y - r), (x + k, y - k), (x + r, y), (x + k, y + k), (x, y + r), (x - k, y + k), (x - r, y), (x - k, y - k)], fill=col)
    star(cx - s * 0.1, cy + s * 0.05, s * 0.55)
    star(cx + s * 0.45, cy - s * 0.4, s * 0.24)
    star(cx + s * 0.42, cy + s * 0.48, s * 0.14)


def person_plus(d, cx, cy, s, col):
    lw = int(s * 0.1)
    d.ellipse([cx - s * 0.5, cy - s * 0.62, cx - s * 0.02, cy - s * 0.14], outline=col, width=lw)
    d.arc([cx - s * 0.78, cy - s * 0.02, cx + s * 0.26, cy + s * 1.0], 180, 360, fill=col, width=lw)
    d.line([(cx + s * 0.5, cy - s * 0.42), (cx + s * 0.5, cy + s * 0.02)], fill=col, width=lw)
    d.line([(cx + s * 0.28, cy - s * 0.2), (cx + s * 0.72, cy - s * 0.2)], fill=col, width=lw)


def card(d, cx, cy, s, col):
    lw = int(s * 0.09)
    w, h = s * 1.5, s * 1.0
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=s * 0.14, outline=col, width=lw)
    d.ellipse([cx - w / 2 + s * 0.2, cy - s * 0.25, cx - w / 2 + s * 0.55, cy + s * 0.1], outline=col, width=lw)
    for y in (-0.15, 0.05, 0.25):
        d.line([(cx - s * 0.05, cy + y * s), (cx + w / 2 - s * 0.2, cy + y * s)], fill=col, width=int(lw * 0.8))


def people_gear(d, cx, cy, s, col):
    lw = int(s * 0.09)
    for dx, k in ((-0.38, 0.8), (0.0, 1.0)):
        x, hr = cx + dx * s, s * 0.2 * k
        hy = cy - s * 0.25 * k
        d.ellipse([x - hr, hy - hr, x + hr, hy + hr], outline=col, width=lw)
        bw = s * 0.42 * k
        d.arc([x - bw, cy + s * 0.05, x + bw, cy + s * 0.05 + bw * 1.6], 180, 360, fill=col, width=lw)
    gx, gy, r = cx + s * 0.55, cy + s * 0.25, s * 0.22
    for i in range(8):
        import math
        a = math.pi * i / 4
        d.line([(gx + math.cos(a) * r * 0.6, gy + math.sin(a) * r * 0.6), (gx + math.cos(a) * r * 1.35, gy + math.sin(a) * r * 1.35)], fill=col, width=lw)
    d.ellipse([gx - r, gy - r, gx + r, gy + r], outline=col, width=lw)


TOP = {
    "guest": [("最新消息", "公告與活動", news), ("課程介紹", "免費試看・會員課程", play), ("AI 小幫手", "有問題就問", sparkle)],
    "member": [("最新消息", "公告與活動", news), ("我的課程", "影片與數位產品", play), ("AI 小幫手", "有問題就問", sparkle)],
}
TOP["admin"] = TOP["member"]
BOTTOM = {
    "guest": ("申請加入", "選擇方案、完成匯款，送出申請", person_plus),
    "member": ("會員專區", "會籍・到期日・我的資料", card),
    "admin": ("管理會員", "核准・升級・停權・恢復", people_gear),
}


def draw(kind):
    primary = hex_rgb(BRAND.get("color", "#3B5BDB"))
    white = (255, 255, 255)
    pale = mix(primary, white, 0.93)
    sub_top = mix(primary, (60, 64, 80), 0.55)
    img = Image.new("RGB", (W, H), pale)
    d = ImageDraw.Draw(img)
    # 上排：淡底、主色圖示與字
    for i, (title, sub, icon) in enumerate(TOP[kind]):
        x0, x1 = COLS[i], COLS[i + 1]
        cx, cy = (x0 + x1) / 2, ROW / 2
        icon(d, cx, cy - 150, 160, primary)
        d.text((cx, cy + 110), title, font=font(FONT, 108), fill=primary, anchor="mm")
        d.text((cx, cy + 235), sub, font=font(FONT_REG, 54), fill=sub_top, anchor="mm")
    line = mix(primary, white, 0.75)
    for x in COLS[1:-1]:
        d.line([(x, 80), (x, ROW - 80)], fill=line, width=4)
    # 下排：主色整塊、白字；左邊放標誌文字
    d.rectangle([0, ROW, W, H], fill=primary)
    title, sub, icon = BOTTOM[kind]
    mark = BRAND.get("mark", "")
    if mark:
        mx, my, mr = 360, ROW + ROW / 2, 210
        d.rounded_rectangle([mx - mr, my - mr, mx + mr, my + mr], radius=90, fill=mix(primary, white, 0.18))
        d.text((mx, my), mark, font=font(FONT, 190 if len(mark) <= 2 else 120), fill=white, anchor="mm")
    tx = 1400
    icon(d, tx - 560, ROW + ROW / 2, 170, white)
    d.text((tx + 40, ROW + 350), title, font=font(FONT, 170), fill=white, anchor="mm")
    d.text((tx + 40, ROW + 560), sub, font=font(FONT_REG, 64), fill=mix(primary, white, 0.8), anchor="mm")
    out = ROOT / "assets" / "richmenu" / f"{kind}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    print(out.relative_to(ROOT), out.stat().st_size)


if __name__ == "__main__":
    for k in ("guest", "member", "admin"):
        draw(k)
