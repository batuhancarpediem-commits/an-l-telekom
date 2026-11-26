"""Ortak yardımcılar."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CACHE = ROOT / "cache"
WORK = CACHE / "work"

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    str(ASSETS / "fonts" / "Poppins-Bold.ttf"),
    str(ASSETS / "fonts" / "Inter-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def load_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def warn(msg):
    print(f"UYARI: {msg}", file=sys.stderr, flush=True)


def info(msg):
    print(msg, flush=True)


def run(cmd, what="komut"):
    """Alt süreç çalıştırır; hata olursa ffmpeg çıktısını göstererek durur."""
    res = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{what} başarısız (kod {res.returncode}):\n{res.stderr[-2500:]}")
    return res


def probe_duration(path):
    res = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", path], "ffprobe")
    return float(res.stdout.strip())


def bold_font(size):
    from PIL import ImageFont
    for p in FONT_CANDIDATES_BOLD:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def asset(rel):
    """content.json'daki göreli yolu (assets/ altı) mutlak yola çevirir."""
    return ASSETS / rel if rel else None
