#!/usr/bin/env python3
"""Anıl Telekomünikasyon tanıtım videosu üreticisi.

Kullanım:
    python src/build.py                 # tam video
    python src/build.py --audio-only    # yalnızca seslendirmeleri üret ve sürelerini göster
    python src/build.py --provider edge # sağlayıcıyı bu çalıştırma için zorla
"""
import argparse
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

from util import ROOT, WORK, asset, info, load_json, probe_duration, warn  # noqa: E402

load_dotenv(ROOT / ".env")

import placeholders  # noqa: E402
import render  # noqa: E402
import slides  # noqa: E402
import tts  # noqa: E402


def plan_scenes(content, cfg):
    co = content["company"]
    logo = placeholders.ensure(co["logo"], "logo", "Anıl Telekom")
    scenes = []

    it = content["intro"]
    scenes.append(dict(id="01-intro", type="intro", template="intro.html", bg_kind="dark",
                       narration=it["narration"],
                       tokens=dict(title=it["title"], subtitle=it["subtitle"], company=co["name"])))

    for bi, b in enumerate(content["brands"], 1):
        lp = asset(b["logo"])
        if lp is not None and not lp.exists() and lp.with_suffix(".png").exists():
            lp = lp.with_suffix(".png")
        has_logo = lp is not None and lp.exists()
        if not has_logo:
            warn(f"{b['name']}: logo dosyası yok (assets/{b['logo']}) → marka adı yazı olarak gösterilecek. "
                 "Logo UYDURULMAZ; gerçek logoyu assets/ altına koyun.")
        big_logo = (f'<div class="logo-pill"><img src="{lp.resolve().as_uri()}"></div>' if has_logo else "")
        tag_logo = (f'<div class="logo-pill brandtag"><img src="{lp.resolve().as_uri()}"></div>' if has_logo else "")
        hero = asset(b.get("hero")) if b.get("hero") else None
        if hero and not hero.exists():
            warn(f"Marka hero görseli yok: {hero.name} → koyu arka plan kullanılacak.")
            hero = None
        scenes.append(dict(id=f"{len(scenes) + 1:02d}-marka-{bi}", type="brand", template="brand.html",
                           bg_kind="hero" if hero else "dark", bg_image=hero, narration=b["narration"],
                           tokens=dict(brand=b["name"], intro=b["intro"], raw_brand_logo=big_logo)))
        for pi, p in enumerate(b["products"], 1):
            ip = asset(p["image"])
            if ip is None or not ip.exists():
                warn(f"{b['name']} – {p['name']}: ürün görseli yok (assets/{p['image']}) → bu ürün slaytı ATLANDI. "
                     "Sahte görsel üretilmez; gerçek fotoğrafı assets/ altına koyun.")
                continue
            img = ip
            scenes.append(dict(id=f"{len(scenes) + 1:02d}-urun-{bi}-{pi}", type="product",
                               template="product.html", bg_kind="product", bg_image=img,
                               narration=p["narration"],
                               tokens=dict(brand=b["name"], product=p["name"], description=p["description"],
                                           raw_brand_logo=tag_logo)))

    of = content["office"]
    video = asset(of.get("video")) if of.get("video") else None
    if video and video.exists():
        kind, extra = "office_video", dict(bg_video=video)
    elif of.get("image"):
        kind, extra = "office", dict(bg_image=placeholders.ensure(of["image"], "office"))
    else:
        kind, extra = "dark", {}
    scenes.append(dict(id=f"{len(scenes) + 1:02d}-ofis", type="office", template="office.html", bg_kind=kind,
                       narration=of["narration"], tokens=dict(caption=of["caption"]), **extra))

    ct = content["contact"]
    scenes.append(dict(id=f"{len(scenes) + 1:02d}-iletisim", type="outro", template="outro.html", bg_kind="dark",
                       narration=ct["narration"],
                       tokens=dict(company=co["name"], tagline=co.get("tagline", ""),
                                   raw_rows=slides.contact_rows(ct))))

    for i, sc in enumerate(scenes):
        sc["direction"] = render.DIRECTIONS[i % len(render.DIRECTIONS)]
        if sc["type"] == "office":                       # dış cephe: yavaş yaklaşan kamera
            sc["direction"], sc["zoom"] = "in", cfg["video"].get("office_zoom", 0.14)
    return scenes, logo


def plan_timeline(scenes, V):
    """Her sahnenin süresini, başlangıcını ve konuşmanın başlama anını hesaplar.
    Görsel geçiş, konuşma bittikten ~0,4 sn sonra başlar; ses bitmeden slayt değişmez."""
    fps, xf, lead, tail = V["fps"], V["crossfade"], 0.1, 0.4
    snap = lambda s: math.ceil(s * fps) / fps  # kare sınırına yuvarla
    t = 0.0
    for i, sc in enumerate(scenes):
        last = i == len(scenes) - 1
        sc["start"] = t
        sc["narr_start"] = t + xf + lead
        sc["dur"] = snap(xf + lead + sc["audio_len"] + tail + (1.0 if last else xf))
        t += sc["dur"] - xf
    return scenes[-1]["start"] + scenes[-1]["dur"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--provider")
    args = ap.parse_args()
    if args.provider:
        os.environ["TTS_PROVIDER"] = args.provider

    t0 = time.time()
    cfg, content = load_json("config.json"), load_json("content.json")
    V = cfg["video"]
    WORK.mkdir(parents=True, exist_ok=True)

    info("1/5 Sahneler planlanıyor…")
    scenes, logo = plan_scenes(content, cfg)

    info("2/5 Seslendirme üretiliyor…")
    provider = tts.synthesize(scenes, cfg["tts"])
    total = plan_timeline(scenes, V)
    info(f"  toplam süre ≈ {total:.1f} sn, {len(scenes)} sahne")
    if args.audio_only:
        for sc in scenes:
            info(f"  {sc['id']}: ses {sc['audio_len']:.1f} sn → {sc['audio']}")
        return

    info("3/5 Slaytlar çiziliyor…")
    slides.compose_backgrounds(scenes, cfg["theme"])
    slides.render_overlays(scenes, cfg["theme"], logo)

    info("4/5 Sahneler render ediliyor…")
    render.render_scenes(scenes, V, workers=max(1, min(2, os.cpu_count() or 1)))

    info("5/5 Birleştirme ve ses miksajı…")
    mix = WORK / "mix.wav"
    render.build_audio(scenes, cfg, total, provider == "mock", mix)
    out = ROOT / V["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    render.assemble(scenes, V, mix, out)

    info(f"\nHazır: {out}  ({probe_duration(out):.1f} sn, {out.stat().st_size / 1e6:.1f} MB, "
         f"{time.time() - t0:.0f} sn sürdü)")
    if provider == "mock":
        warn("Bu videoda SES YOK (mock sağlayıcı). Gerçek seslendirme için .env dosyasını doldurun.")


if __name__ == "__main__":
    main()
