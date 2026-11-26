#!/usr/bin/env python3
"""Marka logolarını ve ürün fotoğraflarını GERÇEK kaynaklarından indirip assets/ altına koyar.

Kullanım:   make assets        (internet erişimi olan bilgisayarda veya GitHub Actions'ta)

Her görsel için sırayla:
  1) dosya zaten assets/ altındaysa dokunulmaz (elle koyduğunuz görsel her zaman önceliklidir),
  2) content.json'da açık adres varsa (logo_url / image_url) o indirilir,
  3) yoksa sayfa adresinden (marka için 'url', ürün için 'page') otomatik aranır:
       logo   -> sayfadaki logo görseli (JSON-LD, <img ... logo ...>, apple-touch-icon)
       ürün   -> sayfanın ana görseli (og:image, JSON-LD image, <img>)
     Banner/slayt/paylaşım görselleri, uygun olmayan oranlar ve çok küçük görseller elenir.
  4) hiçbiri bulunamazsa görsel EKSİK sayılır: video o ürün slaytını atlar, eksik logoda marka adı
     yazı olarak gösterilir. Sahte / yer tutucu görsel ÜRETİLMEZ.

Rapor: cache/asset-report.md  (GitHub Actions'ta çalışma özetine eklenir).
"""
import base64
import io
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from util import CACHE, asset, info, load_json, warn  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
           "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7"}
BAD_PRODUCT = re.compile(r"banner|hero|slide|slider|background|bg[-_]|share|sprite|icon|favicon|avatar|flag|payment|"
                         r"social|placeholder|loading|blank", re.I)
BAD_LOGO = re.compile(r"sprite|flag|payment|social|facebook|twitter|instagram|youtube|linkedin|whatsapp|partner|"
                      r"customer|client|certificate|award", re.I)
MIN_PRODUCT_SIDE = 700      # altı: "düşük çözünürlük" uyarısı
REJECT_PRODUCT_SIDE = 400   # altı: kabul edilmez
REPORT = []


def http_get(url, binary=True):
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.content if binary else r.text


def is_svg(url, data):
    return url.split("?")[0].lower().endswith(".svg") or b"<svg" in data[:600]


def svg_to_png(svg_bytes, out, height=400):
    from playwright.sync_api import sync_playwright
    b64 = base64.b64encode(svg_bytes).decode()
    html = (f'<body style="margin:0;background:transparent"><img id="i" style="height:{height}px;display:block" '
            f'src="data:image/svg+xml;base64,{b64}"></body>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 2400, "height": height})
        pg.set_content(html)
        pg.wait_for_function("document.getElementById('i').complete")
        pg.locator("#i").screenshot(path=str(out), omit_background=True)
        b.close()


def attr(tag, name):
    m = re.search(rf'{name}\s*=\s*["\']([^"\']+)["\']', tag, re.I)
    return m.group(1).strip() if m else None


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def logo_candidates(html, base):
    c = re.findall(r'"logo"\s*:\s*"([^"]+)"', html) + re.findall(r'"logo"\s*:\s*\{[^}]*?"url"\s*:\s*"([^"]+)"', html)
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        if re.search(r"logo", tag, re.I):
            c.append(attr(tag, "data-src") or attr(tag, "src"))
    for tag in re.findall(r"<link\b[^>]*>", html, re.I):
        if re.search(r'rel=["\'][^"\']*apple-touch-icon', tag, re.I):
            c.append(attr(tag, "href"))
    urls = [urljoin(base, u.replace("\\/", "/")) for u in c if u and not u.startswith("data:")]
    urls = [u for u in uniq(urls) if not BAD_LOGO.search(u.rsplit("/", 1)[-1])]
    urls.sort(key=lambda u: 0 if u.split("?")[0].lower().endswith(".svg") else 1 if ".png" in u.lower() else 2)
    return urls[:8]


def product_candidates(html, base):
    c = []
    for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
        if re.search(r'(property|name)=["\'](og:image|twitter:image)["\']', tag, re.I):
            c.append(attr(tag, "content"))
    c += re.findall(r'"image"\s*:\s*"([^"]+)"', html) + re.findall(r'"image"\s*:\s*\[\s*"([^"]+)"', html)
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        c.append(attr(tag, "data-src") or attr(tag, "data-original") or attr(tag, "src"))
    urls = [urljoin(base, u.replace("\\/", "/")) for u in c if u and not u.startswith("data:")]
    ok = [u for u in uniq(urls) if not BAD_PRODUCT.search(u.rsplit("/", 1)[-1]) and re.search(r"\.(jpe?g|png|webp)", u, re.I)]
    return ok[:12]


def note(kind, name, rel, status, detail=""):
    REPORT.append((kind, name, rel, status, detail))


def save_image(data, url, out, kind):
    """Veriyi doğrular ve assets/ altına yazar. (True, açıklama) | (False, neden)"""
    if is_svg(url, data):
        if kind != "logo":
            return False, "ürün için SVG kabul edilmez"
        target = out.with_suffix(".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        svg_to_png(data, target)
        return True, f"SVG → {target.name}"
    im = Image.open(io.BytesIO(data))
    w, h = im.size
    ratio = w / h
    if kind == "logo":
        if not (1.0 <= ratio <= 9.0):
            return False, f"logo oranı uygun değil ({w}x{h})"
        if w < 120:
            return False, f"çok küçük ({w}x{h})"
    else:
        if max(w, h) < REJECT_PRODUCT_SIDE:
            return False, f"çok küçük ({w}x{h})"
        if not (0.5 <= ratio <= 1.9):
            return False, f"oran ürün fotoğrafına benzemiyor ({w}x{h}; banner olabilir)"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        im.convert("RGB").save(out, quality=95)
    else:
        im.convert("RGBA").save(out)
    low = kind == "product" and max(w, h) < MIN_PRODUCT_SIDE
    if low:
        warn(f"{out.name}: düşük çözünürlük ({w}x{h}); daha büyük bir görsel koymanız önerilir.")
    return True, f"{w}x{h}" + (" (düşük çözünürlük!)" if low else "")


def fetch_item(kind, name, rel, explicit_url, page_url):
    out = asset(rel)
    if any(p.exists() for p in [out, out.with_suffix(".png")]):
        note(kind, name, rel, "var", "elle konmuş / önceden indirilmiş")
        info(f"  var, atlandı: {rel}")
        return
    tried, sources = [], []
    if explicit_url:
        sources.append([explicit_url])
    if page_url:
        try:
            html = http_get(page_url, binary=False)
            sources.append(logo_candidates(html, page_url) if kind == "logo" else product_candidates(html, page_url))
        except Exception as e:  # noqa: BLE001
            tried.append(f"sayfa açılamadı ({e})")
    for urls in sources:
        for u in urls:
            try:
                ok, detail = save_image(http_get(u), u, out, kind)
            except Exception as e:  # noqa: BLE001
                tried.append(f"{u[:90]} → {e}")
                continue
            if ok:
                note(kind, name, rel, "indirildi", f"{detail} ← {u[:110]}")
                info(f"  indirildi: {rel} ({detail})")
                return
            tried.append(f"{u[:90]} → {detail}")
    note(kind, name, rel, "EKSİK", "; ".join(tried[:3]) or "kaynak adresi tanımlı değil")
    warn(f"EKSİK: {name} ({kind}) → assets/{rel} dosyasını elle ekleyin.")


def main():
    c = load_json("content.json")
    for b in c["brands"]:
        fetch_item("logo", b["name"], b["logo"], b.get("logo_url"), b.get("url"))
        for p in b["products"]:
            fetch_item("product", f"{b['name']} – {p['name']}", p["image"], p.get("image_url"), p.get("page"))

    lines = ["## Görsel raporu", "", "| Tür | Öğe | Dosya | Durum | Ayrıntı |", "|---|---|---|---|---|"]
    for kind, name, rel, status, detail in REPORT:
        lines.append(f"| {kind} | {name} | `assets/{rel}` | {status} | {detail} |")
    missing = [r for r in REPORT if r[3] == "EKSİK"]
    lines += ["", f"**{len(REPORT) - len(missing)}/{len(REPORT)} görsel hazır.**"]
    if missing:
        lines += ["", "Eksik görseller için dosyayı yukarıdaki yola elle koyun (şeffaf PNG ya da beyaz fonlu, en az 1500 px "
                  "ürün fotoğrafı). Eksik logoda marka adı yazı olarak gösterilir; eksik ürünün slaytı atlanır. "
                  "Sahte görsel üretilmez."]
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "asset-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    info("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
