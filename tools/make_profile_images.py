"""會員通（LINE Member Kit）：產生官方帳號「商業簡介頁」用的圖（1280 × 640，2:1；LINE 這兩個欄位固定裁成 2:1），輸出到 assets/profile/。

- intro.jpg：「學院介紹」區塊（自由填寫）的照片
- notice.jpg：「最新資訊」公告的圖片

主色、標誌文字讀 tools/config.local.json 的 brand；字型和顏色工具跟 make_richmenus.py 共用。
文字是 Phil 的 AI 學院用的，換客戶時改 TEXT。執行：python3 tools/make_profile_images.py
"""
from PIL import Image, ImageDraw

from make_richmenus import BRAND, FONT, FONT_REG, ROOT, font, hex_rgb, mix

W, H = 1280, 640
TEXT = {
    "name": "Phil 的 AI 學院",
    "tagline": "把 AI 用進工作與生活",
    "pillars": ["課程", "實作", "社群交流"],
    "welcome": "歡迎加入",
    "steps": [("申請加入", "選單「申請加入」選方案"), ("完成匯款", "填寫資料，確認入帳"), ("開始學習", "會員課程＋AI 小幫手")],
}


def base():
    primary = hex_rgb(BRAND.get("color", "#3B5BDB"))
    img = Image.new("RGB", (W, H), primary)
    d = ImageDraw.Draw(img)
    # 右上淡色圓，讓畫面不要太平
    light = mix(primary, (255, 255, 255), 0.12)
    d.ellipse([W - 420, -260, W + 260, 420], fill=light)
    d.ellipse([W - 260, H - 200, W + 120, H + 180], fill=light)
    return img, d, primary


def mark(d, primary, x, y, r=70):
    m = BRAND.get("mark", "")
    if not m:
        return
    d.rounded_rectangle([x, y, x + 2 * r, y + 2 * r], radius=r * 0.45, fill=(255, 255, 255))
    d.text((x + r, y + r), m, font=font(FONT, 64 if len(m) <= 2 else 40), fill=primary, anchor="mm")


def intro():
    img, d, primary = base()
    white, soft = (255, 255, 255), mix(primary, (255, 255, 255), 0.75)
    mark(d, primary, 96, 60, r=60)
    d.text((96, 300), TEXT["name"], font=font(FONT, 92), fill=white, anchor="ls")
    d.text((96, 375), TEXT["tagline"], font=font(FONT_REG, 46), fill=soft, anchor="ls")
    x = 96
    for p in TEXT["pillars"]:
        f = font(FONT, 38)
        w = d.textlength(p, font=f) + 64
        d.rounded_rectangle([x, 450, x + w, 526], radius=38, fill=white)
        d.text((x + w / 2, 488), p, font=f, fill=primary, anchor="mm")
        x += w + 24
    return img


def notice():
    img, d, primary = base()
    white, soft = (255, 255, 255), mix(primary, (255, 255, 255), 0.75)
    mark(d, primary, 96, 56, r=44)
    d.text((208, 100), TEXT["name"], font=font(FONT_REG, 38), fill=soft, anchor="lm")
    d.text((96, 250), TEXT["welcome"], font=font(FONT, 100), fill=white, anchor="ls")
    cw, gap, top = 340, 28, 310
    for i, (title, sub) in enumerate(TEXT["steps"]):
        x = 96 + i * (cw + gap)
        d.rounded_rectangle([x, top, x + cw, top + 240], radius=28, fill=white)
        d.ellipse([x + 32, top + 32, x + 96, top + 96], fill=primary)
        d.text((x + 64, top + 64), str(i + 1), font=font(FONT, 38), fill=white, anchor="mm")
        d.text((x + 32, top + 155), title, font=font(FONT, 46), fill=primary, anchor="ls")
        d.text((x + 32, top + 205), sub, font=font(FONT_REG, 26), fill=mix(primary, (60, 64, 80), 0.6), anchor="ls")
    return img


if __name__ == "__main__":
    out = ROOT / "assets" / "profile"
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in (("intro", intro), ("notice", notice)):
        p = out / f"{name}.jpg"
        fn().save(p, quality=90)
        print(p.relative_to(ROOT), p.stat().st_size)
