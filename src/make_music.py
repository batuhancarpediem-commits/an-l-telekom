#!/usr/bin/env python3
"""Telifsiz (tamamen sentezlenmiş, özgün) arka plan müziği üretir: assets/music.mp3

Sakin, kurumsal bir pad + yumuşak arpej. 32 sn'lik kesintisiz döngü; video süresine göre
otomatik tekrarlanır ve konuşma sırasında kısılır (ducking). Üretilen müzik bu projeye aittir.
Kendi müziğinizi kullanmak için assets/music.mp3 dosyasını değiştirmeniz yeterli.
"""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SR, CHORD_S = 44100, 8.0
# Am - F - C - G (her akor 8 sn, toplam 32 sn)
CHORDS = [[110.0, 164.81, 220.0, 261.63, 329.63], [87.31, 130.81, 174.61, 220.0, 261.63],
          [130.81, 196.0, 261.63, 329.63, 392.0], [98.0, 146.83, 196.0, 246.94, 293.66]]


def circ_window(n, total, center, width):
    """Döngüde kesintisiz (sarmalı) yumuşak pencere."""
    t = np.arange(total)
    d = np.minimum(np.abs(t - center), total - np.abs(t - center))
    return np.where(d < width, 0.5 * (1 + np.cos(np.pi * d / width)), 0.0)


def make():
    n = int(SR * CHORD_S * len(CHORDS))
    t = np.arange(n) / SR
    rng = np.random.default_rng(11)
    out = np.zeros((2, n))
    for ci, chord in enumerate(CHORDS):
        win = circ_window(n, n, int((ci + 0.5) * CHORD_S * SR), int(CHORD_S * SR * 0.75))
        for ni, f in enumerate(chord):
            for det, pan in ((-0.8, 0.35), (0.0, 0.5), (0.8, 0.65)):            # hafif detune = koro etkisi
                vib = 1 + 0.0012 * np.sin(2 * np.pi * (0.2 + 0.05 * ni) * t + ni)
                ph = 2 * np.pi * np.cumsum(f * (1 + det * 0.0016) * vib) / SR
                tone = np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
                amp = 0.05 if ni else 0.09                                       # kök nota biraz daha belirgin
                out[0] += tone * win * amp * (1 - pan)
                out[1] += tone * win * amp * pan
    # yumuşak arpej (akor seslerinden), döngüde kuyruklar sarılır
    step = int(SR * 0.5)
    for ci, chord in enumerate(CHORDS):
        for k in range(int(CHORD_S / 0.5)):
            if rng.random() < 0.55:
                continue
            f = chord[1:][rng.integers(0, 4)] * 2
            st = int((ci * CHORD_S) * SR) + k * step
            L = int(SR * 2.2)
            tt = np.arange(L) / SR
            pl = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 3.2) * 0.035
            idx = (st + np.arange(L)) % n
            pan = 0.3 + 0.4 * rng.random()
            out[0, idx] += pl * (1 - pan)
            out[1, idx] += pl * pan
    out /= np.abs(out).max() / 0.5
    return (out.T * 32767).astype("<i2")


def main():
    wav = ROOT / "cache" / "music.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(make().tobytes())
    dst = ROOT / "assets" / "music.mp3"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "160k", str(dst)])
    if r.returncode:
        sys.exit("ffmpeg ile mp3 üretilemedi.")
    print("Hazır:", dst)


if __name__ == "__main__":
    main()
