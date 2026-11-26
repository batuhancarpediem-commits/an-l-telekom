"""Seslendirme (TTS) sağlayıcıları.

Sağlayıcılar: elevenlabs, google, edge, mock.
"auto" modunda sırayla: ElevenLabs anahtarı varsa ElevenLabs → Google anahtarı varsa Google →
edge-tts kuruluysa Edge → hiçbiri yoksa "mock" (SESSİZ, yalnızca süre testi için).
Üretilen sesler cache/tts/ altında saklanır; metin/ayar değişmedikçe tekrar ücret/istek harcanmaz.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import time
import wave
from pathlib import Path

import requests

from util import CACHE, info, load_json, probe_duration, run, warn

TTS_DIR = CACHE / "tts"


def apply_pronunciation(text, mapping):
    for src in sorted((k for k in mapping if not k.startswith("_")), key=len, reverse=True):
        text = re.sub(re.escape(src), mapping[src], text)
    return text


def pick_provider(cfg_provider):
    prov = (os.getenv("TTS_PROVIDER") or cfg_provider or "auto").lower()
    if prov != "auto":
        return prov
    if os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_VOICE_ID"):
        return "elevenlabs"
    if os.getenv("GOOGLE_TTS_API_KEY"):
        return "google"
    try:
        import edge_tts  # noqa: F401
        return "edge"
    except ImportError:
        return "mock"


# ---------------------------------------------------------------- sağlayıcılar
def _elevenlabs(text, out, cfg):
    key, voice = os.getenv("ELEVENLABS_API_KEY"), os.getenv("ELEVENLABS_VOICE_ID")
    if not key or not voice:
        raise RuntimeError("ELEVENLABS_API_KEY ve ELEVENLABS_VOICE_ID .env içinde tanımlı olmalı.")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": cfg["elevenlabs_model"],
            "voice_settings": {
                "stability": cfg["elevenlabs_stability"],
                "similarity_boost": cfg["elevenlabs_similarity"],
                "style": cfg["elevenlabs_style"],
                "use_speaker_boost": True,
                "speed": cfg.get("elevenlabs_speed", 1.0),
            },
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs hata {r.status_code}: {r.text[:300]}")
    out.write_bytes(r.content)


def _google(text, out, cfg):
    key = os.getenv("GOOGLE_TTS_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_TTS_API_KEY tanımlı olmalı.")
    errors = []
    for voice in [cfg["google_voice"]] + list(cfg.get("google_voice_fallbacks", [])):   # Chirp3-HD -> Wavenet
        r = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            params={"key": key},
            json={
                "input": {"text": text},
                "voice": {"languageCode": "tr-TR", "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": cfg["google_speaking_rate"]},
            },
            timeout=120,
        )
        if r.status_code == 200:
            out.write_bytes(base64.b64decode(r.json()["audioContent"]))
            return
        errors.append(f"{voice}: {r.status_code} {r.text[:160]}")
    raise RuntimeError("Google TTS hata: " + " | ".join(errors))


def _edge(text, out, cfg):
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, cfg["edge_voice"], rate=cfg["edge_rate"]).save(str(out))

    last = None
    for attempt in range(4):                      # geçici ağ/sunucu hatalarına karşı yeniden dene
        try:
            asyncio.run(go())
            if out.exists() and out.stat().st_size > 1000:
                return
            last = RuntimeError("boş ses dosyası döndü")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Edge TTS başarısız: {last}")


def _mock(text, out, cfg):
    """SESSİZ ses dosyası. Gerçek seslendirme değildir; sadece süre planlamasını test eder."""
    seconds = max(2.5, len(text.split()) / 2.4)
    rate = 44100
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


PROVIDERS = {"elevenlabs": (_elevenlabs, "mp3"), "google": (_google, "mp3"),
             "edge": (_edge, "mp3"), "mock": (_mock, "wav")}


def _candidates(first):
    """Seçilen sağlayıcı çalışmazsa denenecek diğer (anahtarı/kurulumu olan) sağlayıcılar."""
    c = [first]
    if os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_VOICE_ID"):
        c.append("elevenlabs")
    if os.getenv("GOOGLE_TTS_API_KEY"):
        c.append("google")
    try:
        import edge_tts  # noqa: F401
        c.append("edge")
    except ImportError:
        pass
    return list(dict.fromkeys(x for x in c if x != "mock"))


def _gen(sc, provider, cfg, pron):
    """Tek sahne için sesi üretir (önbellekte varsa yeniden üretmez)."""
    fn, ext = PROVIDERS[provider]
    voice_id = {"elevenlabs": os.getenv("ELEVENLABS_VOICE_ID", ""), "google": cfg["google_voice"],
                "edge": cfg["edge_voice"], "mock": ""}[provider]
    spoken = apply_pronunciation(sc["narration"], pron)
    key = hashlib.sha1(json.dumps([provider, voice_id, spoken, {k: v for k, v in cfg.items()
                                   if k.startswith(provider)}], ensure_ascii=False).encode()).hexdigest()[:16]
    out = TTS_DIR / f"{provider}-{key}.{ext}"
    if not out.exists():
        tmp = out.with_name(out.stem + ".part" + out.suffix)
        fn(spoken, tmp, cfg)
        tmp.rename(out)
        info(f"  ses üretildi: {sc['id']}")
    else:
        info(f"  ses önbellekte: {sc['id']}")
    sc["audio"] = out
    sc["audio_len"] = probe_duration(out)


def synthesize(scenes, cfg):
    """Her sahne için ses üretir; scene['audio'] ve scene['audio_len'] alanlarını doldurur.
    Kullanılan sağlayıcı adını döner. Seçilen sağlayıcı çalışmazsa diğerleri sırayla denenir;
    hiçbiri çalışmazsa sessiz video üretmek yerine açık bir hata ile durur."""
    provider = pick_provider(cfg.get("provider"))
    if provider not in PROVIDERS:
        raise SystemExit(f"Bilinmeyen TTS sağlayıcı: {provider}")
    pron = load_json("pronunciation.json")
    TTS_DIR.mkdir(parents=True, exist_ok=True)

    if provider == "mock":
        warn("Gerçek ses sağlayıcısı bulunamadı → SESSİZ test sesi kullanılıyor. "
             "Gerçek seslendirme için .env dosyasını doldurun veya 'pip install edge-tts' yapın.")
    else:
        errors = []
        for cand in _candidates(provider):
            try:
                _gen(scenes[0], cand, cfg, pron)      # ilk sahneyle sağlayıcıyı sına
                provider = cand
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"  - {cand}: {e}")
                warn(f"{cand} çalışmadı, sıradaki sağlayıcı deneniyor.")
        else:
            raise SystemExit("Hiçbir seslendirme sağlayıcısı çalışmadı:\n" + "\n".join(errors) +
                             "\nÇözüm: ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID veya GOOGLE_TTS_API_KEY ekleyin "
                             "(GitHub: Settings → Secrets and variables → Actions).")
    info(f"Seslendirme sağlayıcısı: {provider}")

    for sc in scenes:
        _gen(sc, provider, cfg, pron)
    return provider
