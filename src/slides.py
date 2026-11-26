"""Slayt görselleri: 4K arka planlar (PIL/NumPy) + şeffaf yazı katmanları (HTML → Playwright)."""
import html
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from util import ROOT, WORK, warn

BG_W, BG_H = 3840, 2160


def _rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _finish(arr, path, grain=1.4):
    """Bantlaşmayı önlemek için hafif tane ekleyip JPEG olarak kaydeder."""
    rng = np.random.default_rng(7)
    arr = arr + rng.normal(0, grain, arr.shape[:2] + (1,)).astype(np.float32)
    Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).save(path, quality=96, subsampling=0)


def _gradient(c1, c2, glow_color=None, glow_xy=(0.75, 0.4), glow_strength=0.0):
    w, h = BG_W // 4, BG_H // 4
    xs, ys = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    t = np.clip(xs * 0.35 + ys * 0.65, 0, 1)[..., None]
    img = c1 * (1 - t) + c2 * t
    if glow_color is not None and glow_strength > 0:
        d = np.sqrt((xs - glow_xy[0]) ** 2 + ((ys - glow_xy[1]) * 0.6) ** 2)
        g = np.clip(1 - d / 0.75, 0, 1)[..., None] ** 2 * glow_strength
        img = img * (1 - g) + glow_color * g
    return cv2.resize(img.astype(np.float32), (BG_W, BG_H), interpolation=cv2.INTER_CUBIC)


def dark_bg(theme, path):
    arr = _gradient(_rgb(theme["dark"]), _rgb(theme["primary"]) * 0.8,
                    _rgb(theme["accent"]), (0.8, 0.35), 0.22)
    _finish(arr, path)


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def photo_bg(src, path, shade="bottom"):
    img = Image.open(src).convert("RGB")
    if img.width < 1920:
        warn(f"{Path(src).name} düşük çözünürlüklü ({img.width}px); en az 1920px genişlik önerilir.")
    arr = np.asarray(cover(img, BG_W, BG_H), dtype=np.float32)
    y = np.linspace(0, 1, BG_H, dtype=np.float32)[:, None, None]
    if shade == "bottom":
        k = 1 - 0.62 * np.clip((y - 0.45) / 0.55, 0, 1) ** 1.4
    else:  # tüm görseli karart (marka hero)
        k = np.full_like(y, 0.45)
    _finish(arr * k, path, grain=0.6)


# ------------------------------------------------------------------ ürün
def load_product(path):
    """Ürünü şeffaf arka planlı RGBA olarak yükler. Şeffaflık yoksa ve köşeler beyaza yakınsa
    arka plan otomatik temizlenir (basit yöntem; en iyisi şeffaf PNG vermektir)."""
    im = Image.open(path)
    if max(im.size) < 1000:
        warn(f"{Path(path).name} düşük çözünürlüklü ({im.width}x{im.height}); en az 1500px önerilir.")
    has_alpha = im.mode in ("RGBA", "LA") and np.asarray(im.convert("RGBA"))[..., 3].min() < 250
    if has_alpha:
        rgba = im.convert("RGBA")
    else:
        rgb = np.asarray(im.convert("RGB")).copy()
        h, w = rgb.shape[:2]
        mask = np.zeros((h + 2, w + 2), np.uint8)
        seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
        light = [s for s in seeds if rgb[s[1], s[0]].mean() > 235]
        if not light:
            warn(f"{Path(path).name}: şeffaf arka plan yok ve köşeler beyaz değil; görsel olduğu gibi kullanılıyor.")
        for s in light:
            cv2.floodFill(rgb.copy(), mask, s, 0, (14, 14, 14), (14, 14, 14),
                          cv2.FLOODFILL_MASK_ONLY | (255 << 8))
        alpha = 255 - mask[1:-1, 1:-1]
        alpha = cv2.GaussianBlur(cv2.erode(alpha, np.ones((3, 3), np.uint8)), (0, 0), 1.2)
        rgba = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    bbox = rgba.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
    return rgba.crop(bbox) if bbox else rgba


def product_bg(src, theme, path):
    base = _gradient(_rgb(theme["light"]), _rgb("#D3DCEB"), np.array([255, 255, 255], np.float32), (0.72, 0.45), 0.55)
    # zemin: yumuşak gölgelendirme
    floor_y = 1720
    yy = np.arange(BG_H, dtype=np.float32)[:, None, None]
    shade = 1 - 0.07 * np.clip((yy - (floor_y - 80)) / 160, 0, 1)
    base = base * shade
    canvas = Image.fromarray(np.clip(base, 0, 255).astype("uint8")).convert("RGBA")

    prod = load_product(src)
    s = min(1950 / prod.width, 1480 / prod.height)
    prod = prod.resize((max(1, round(prod.width * s)), max(1, round(prod.height * s))), Image.LANCZOS)
    cx = 2680
    px, py = cx - prod.width // 2, floor_y - prod.height

    # temas gölgesi
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - int(prod.width * 0.42), floor_y - 28,
                                cx + int(prod.width * 0.42), floor_y + 46), fill=(10, 20, 40, 120))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(34)))

    # yansıma
    rh = min(prod.height // 2, 460)
    refl = prod.transpose(Image.FLIP_TOP_BOTTOM).crop((0, 0, prod.width, rh))
    fade = Image.fromarray((np.linspace(0.30, 0, rh)[:, None] * np.ones((rh, prod.width)) * 255).astype("uint8"))
    ra = np.minimum(np.asarray(refl.getchannel("A")), np.asarray(fade))
    refl.putalpha(Image.fromarray(ra.astype("uint8")))
    canvas.alpha_composite(refl.filter(ImageFilter.GaussianBlur(2)), (px, floor_y))

    canvas.alpha_composite(prod, (px, py))
    _finish(np.asarray(canvas.convert("RGB"), dtype=np.float32), path, grain=0.8)


# ------------------------------------------------------------------ yazı katmanları
ICONS = {
    "phone": "M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z",
    "place": "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z",
    "mail": "M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z",
    "web": "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95c-.32-1.25-.78-2.45-1.38-3.56 1.84.63 3.37 1.91 4.33 3.56zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56-1.84-.63-3.37-1.9-4.33-3.56zm2.95-8H5.08c.96-1.66 2.49-2.93 4.33-3.56C8.81 5.55 8.35 6.75 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95c-.96 1.65-2.49 2.93-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z",
}


def contact_rows(contact):
    rows = []
    for key, icon in (("phone", "phone"), ("address", "place"), ("email", "mail"), ("website", "web")):
        v = contact.get(key)
        if v:
            rows.append(f'<div class="row"><span class="ico"><svg viewBox="0 0 24 24"><path d="{ICONS[icon]}"/></svg></span>'
                        f'<span class="val">{html.escape(v)}</span></div>')
    if contact.get("social"):
        rows.append(f'<div class="row"><span class="ico at">@</span><span class="val">{html.escape(contact["social"].lstrip("@"))}</span></div>')
    return "\n".join(rows)


def _theme_css(theme):
    return ":root{" + "".join(f"--{k.replace('_', '-')}:{v};" for k, v in theme.items()) + "}"


def compose_backgrounds(scenes, theme):
    WORK.mkdir(parents=True, exist_ok=True)
    for sc in scenes:
        kind = sc["bg_kind"]
        if kind == "office_video":
            continue
        out = WORK / f"{sc['id']}-bg.jpg"
        if kind == "dark":
            dark_bg(theme, out)
        elif kind == "hero":
            photo_bg(sc["bg_image"], out, shade="all")
        elif kind == "office":
            photo_bg(sc["bg_image"], out, shade="bottom")
        elif kind == "product":
            product_bg(sc["bg_image"], theme, out)
        sc["bg"] = out


def render_overlays(scenes, theme, company_logo):
    from playwright.sync_api import sync_playwright
    css = (ROOT / "templates" / "base.css").read_text(encoding="utf-8")
    css = _theme_css(theme) + css
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for sc in scenes:
            tpl = (ROOT / "templates" / sc["template"]).read_text(encoding="utf-8")
            tokens = {"css": css, "footer_logo": Path(company_logo).resolve().as_uri()}
            for k, v in sc["tokens"].items():
                tokens[k] = v if k.startswith("raw_") else html.escape(str(v))
            for k, v in tokens.items():
                tpl = tpl.replace("{{" + k + "}}", v)
            src = WORK / f"{sc['id']}.html"
            src.write_text(tpl, encoding="utf-8")
            page.goto(src.resolve().as_uri())
            page.wait_for_load_state("load")
            out = WORK / f"{sc['id']}-overlay.png"
            page.screenshot(path=str(out), omit_background=True)
            sc["overlay"] = out
        browser.close()
