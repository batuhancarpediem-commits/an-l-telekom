"""Eksik görseller için yer tutucu üretir.

Elle çalıştırırsanız (make placeholders) content.json'daki eksik tüm görseller için
"ÖRNEK" etiketli yer tutucu oluşturur. Mevcut dosyalara asla dokunmaz.
build.py de eksik görsel bulursa uyarı verip aynı yer tutucuyu kullanır.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

try:
    from util import ASSETS, CACHE, asset, bold_font, load_json, info, warn
except ImportError:  # paket olarak çağrılırsa
    from .util import ASSETS, CACHE, asset, bold_font, load_json, info, warn


def _center_text(d, box, text, font, fill):
    x0, y0, x1, y1 = box
    bb = d.textbbox((0, 0), text, font=font)
    d.text(((x0 + x1 - (bb[2] - bb[0])) / 2 - bb[0], (y0 + y1 - (bb[3] - bb[1])) / 2 - bb[1]),
           text, font=font, fill=fill)


def make_logo(path, text, color="#0B3D91", size=(900, 320)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=48, fill=color)
    _center_text(d, (0, 0, size[0], size[1] - 40), text.upper(), bold_font(88), "white")
    _center_text(d, (0, size[1] - 110, size[0], size[1] - 20), "LOGO EKLENECEK", bold_font(32), (255, 255, 255, 170))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def make_product(path, label, hue=0):
    """Şeffaf arka planlı, jenerik cihaz silüeti (gerçek ürün değildir)."""
    W, H = 1800, 1800
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    palette = [("#2B3A55", "#46597F"), ("#1F4E5F", "#3A8399"), ("#4A3B66", "#7A62A6")]
    dark, light = palette[hue % len(palette)]
    d.rounded_rectangle((420, 150, 1380, 1650), radius=130, fill=dark)
    d.rounded_rectangle((470, 210, 1330, 1590), radius=95, fill=light)
    d.rounded_rectangle((830, 175, 970, 195), radius=10, fill=(10, 10, 10, 200))
    _center_text(d, (470, 650, 1330, 900), "ÜRÜN", bold_font(130), (255, 255, 255, 235))
    _center_text(d, (470, 880, 1330, 1060), "GÖRSELİ EKLENECEK", bold_font(70), (255, 255, 255, 200))
    _center_text(d, (470, 1070, 1330, 1170), label, bold_font(54), (255, 255, 255, 170))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def make_office(path):
    """Basit, jenerik bir bina cephesi illüstrasyonu (gerçek ofis değildir)."""
    W, H = 3840, 2160
    y = np.linspace(0, 1, H)[:, None, None]
    top, bot = np.array([120, 170, 220]), np.array([225, 235, 245])
    sky = (top * (1 - y) + bot * y) * np.ones((H, W, 3))
    img = Image.fromarray(sky.astype("uint8"))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 1700, W, H), fill=(88, 92, 100))
    d.rectangle((0, 1640, W, 1700), fill=(170, 172, 176))
    d.rectangle((900, 500, 2940, 1640), fill=(214, 218, 226))
    d.rectangle((900, 500, 2940, 600), fill=(11, 61, 145))
    for r in range(3):
        for c in range(6):
            x0, y0 = 1010 + c * 330, 700 + r * 290
            d.rectangle((x0, y0, x0 + 250, y0 + 210), fill=(120, 160, 200))
    d.rectangle((1760, 1240, 2080, 1640), fill=(70, 100, 140))
    font = bold_font(110)
    _center_text(d, (900, 500, 2940, 600), "ANIL TELEKOMÜNİKASYON", bold_font(70), "white")
    _center_text(d, (0, 120, W, 330), "ÖRNEK GÖRSEL – KENDİ OFİS FOTOĞRAFINIZLA DEĞİŞTİRİN", font, (255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=93)


def ensure(rel, kind, label="", hue=0):
    """Dosya varsa yolunu döner; yoksa yer tutucuyu cache/placeholders/ altına üretip yolunu döner.
    (Yer tutucular assets/ içine yazılmaz; böylece 'make assets' gerçek görselin indirilmesini engellenmez.)"""
    p = asset(rel)
    if p is None:
        return None
    if p.exists():
        return p
    warn(f"Görsel bulunamadı: assets/{rel} → yer tutucu kullanılıyor.")
    ext = ".jpg" if kind == "office" else ".png"
    out = CACHE / "placeholders" / Path(rel).with_suffix(ext)
    if not out.exists():
        if kind == "logo":
            make_logo(out, label)
        elif kind == "product":
            make_product(out, label, hue)
        elif kind == "office":
            make_office(out)
        else:
            raise ValueError(kind)
    return out


def main():
    c = load_json("content.json")
    ensure(c["company"]["logo"], "logo", "Anıl Telekom")
    for bi, b in enumerate(c["brands"]):
        ensure(b["logo"], "logo", b["name"], )
        for pi, p in enumerate(b["products"]):
            ensure(p["image"], "product", p["name"], bi + pi)
    if c["office"].get("image"):
        ensure(c["office"]["image"], "office")
    info("Yer tutucular hazır.")


if __name__ == "__main__":
    main()
