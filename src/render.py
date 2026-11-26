"""FFmpeg ile sahne render, çapraz geçiş ve ses miksajı."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from util import WORK, info, run

DIRECTIONS = ["in", "pan_right", "out", "pan_left"]  # sahneler arasında dönüşümlü kullanılır
SS_W, SS_H = 3840, 2160                              # titremeyi önlemek için 4K kaynaktan çalışılır


def _file_hash(*paths):
    h = hashlib.sha1()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]


def _zoompan(direction, n, z):
    if direction == "in":
        return f"1+{z}*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if direction == "out":
        return f"1+{z}*(1-on/{n})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if direction == "pan_right":
        return f"1+{z}", f"(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"
    return f"1+{z}", f"(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"   # pan_left


def _transition(V, i):
    """Geçiş türü: config.video.transitions listesinden sırayla (varsayılan: yumuşak çapraz geçiş + hafif kayma)."""
    cyc = V.get("transitions") or ["fade"]
    return cyc[(i - 1) % len(cyc)]


def render_scene(sc, V, first, last):
    W, H, fps = V["width"], V["height"], V["fps"]
    D = sc["dur"]
    n = round(D * fps)
    video_bg = sc["bg_kind"] == "office_video"
    src = sc["bg_video"] if video_bg else sc["bg"]
    key = hashlib.sha1(repr(("filtre-v2", sc["bg_kind"], sc["direction"], round(D, 3), sc.get("zoom", V["ken_burns_zoom"]), first, last,
                             W, H, fps, _file_hash(src, sc["overlay"]))).encode()).hexdigest()[:12]
    out = WORK / f"{sc['id']}-{key}.mp4"
    sc["video"] = out
    if out.exists():
        info(f"  sahne önbellekte: {sc['id']}")
        return
    tmp = out.with_name(out.stem + ".part.mp4")

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if video_bg:
        cmd += ["-stream_loop", "-1", "-i", src]
        bg = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},"
              f"setsar=1,format=yuv420p,trim=duration={D:.3f},setpts=PTS-STARTPTS[bg]")
    else:
        z, x, y = _zoompan(sc["direction"], n, sc.get("zoom", V["ken_burns_zoom"]))
        cmd += ["-i", src]
        bg = (f"[0:v]scale={SS_W}:{SS_H},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={fps},"
              f"setsar=1,format=yuv420p[bg]")
    cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{D:.3f}", "-i", sc["overlay"]]

    t0, dur_in = 0.35, 0.6   # yazı katmanı: fade-in + hafif yukarı kayma
    # Renk düzeltme + hafif vinyet yalnızca arka plana uygulanır (yazı ve logolar tam parlaklıkta kalır).
    # FFmpeg vignette: açı küçüldükçe kararma AZALIR; PI/8 çok hafiftir.
    chain = [
        bg,
        "[bg]eq=contrast=1.03:saturation=1.06,vignette=angle=PI/8,format=yuv420p[bgg]",
        f"[1:v]format=rgba,fade=t=in:st={t0}:d={dur_in}:alpha=1[ov]",
        f"[bgg][ov]overlay=x=0:y='24*pow(1-min(1,max(0,(t-{t0})/{dur_in})),2)':eval=frame:format=auto,"
        f"format=yuv420p"
        + (",fade=t=in:st=0:d=0.6" if first else "")
        + (f",fade=t=out:st={D - 1.0:.3f}:d=1.0" if last else "")
        + "[v]",
    ]
    cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-frames:v", str(n), "-r", str(fps),
            "-c:v", "libx264", "-crf", "12", "-preset", V["preset"], "-pix_fmt", "yuv420p", tmp]
    run(cmd, f"sahne render ({sc['id']})")
    os.replace(tmp, out)
    info(f"  sahne hazır: {sc['id']} ({D:.1f} sn)")


def render_scenes(scenes, V, workers=2):
    total = len(scenes)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(render_scene, sc, V, i == 0, i == total - 1) for i, sc in enumerate(scenes)]
        for f in futs:
            f.result()


def build_audio(scenes, cfg, total, silent, out):
    a = cfg["audio"]
    n = len(scenes)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    f = []
    for i, sc in enumerate(scenes):
        cmd += ["-i", sc["audio"]]
        ms = round(sc["narr_start"] * 1000)
        f.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
    f.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest[nar0]")
    cur = "nar0"
    if not silent:
        if a.get("room_reverb"):
            f.append(f"[{cur}]aecho=0.8:0.7:35:0.10[rv]")
            cur = "rv"
        f.append(f"[{cur}]loudnorm=I={a['target_lufs']}:TP=-1.5:LRA=11,aresample=44100[ln]")
        cur = "ln"
    f.append(f"[{cur}]apad=whole_dur={total:.3f}[nar]")

    music = Path(__file__).resolve().parent.parent / "assets" / a["music_file"] if a.get("music_file") else None
    if music and music.exists():
        cmd += ["-stream_loop", "-1", "-i", music]
        f += [f"[{n}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={a['music_volume']}[m]",
              "[nar]asplit=2[n1][n2]",
              "[m][n1]sidechaincompress=threshold=0.02:ratio=10:attack=30:release=500[duck]",
              "[n2][duck]amix=inputs=2:normalize=0:duration=first[mx]"]
        cur = "mx"
        info("  arka plan müziği eklendi (konuşma sırasında otomatik kısılır).")
    else:
        cur = "nar"
    f.append(f"[{cur}]atrim=0:{total:.3f},afade=t=out:st={total - 1.2:.3f}:d=1.2[aout]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[aout]", "-c:a", "pcm_s16le", out]
    run(cmd, "ses miksajı")


def assemble(scenes, V, audio, out):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for sc in scenes:
        cmd += ["-i", sc["video"]]
    cmd += ["-i", audio]
    n = len(scenes)
    xf = V["crossfade"]
    parts, prev = [], "[0:v]"
    for i in range(1, n):
        lbl = f"[x{i}]"
        parts.append(f"{prev}[{i}:v]xfade=transition={_transition(V, i)}:duration={xf}:offset={scenes[i]['start']:.4f}{lbl}")
        prev = lbl
    vmap = prev if n > 1 else "0:v"
    cmd += (["-filter_complex", ";".join(parts)] if parts else [])
    tmp = Path(str(out) + ".part.mp4")
    cmd += ["-map", vmap, "-map", f"{n}:a", "-c:v", "libx264", "-crf", str(V["crf"]), "-preset", V["preset"],
            "-pix_fmt", "yuv420p", "-r", str(V["fps"]), "-c:a", "aac", "-b:a", V["audio_bitrate"],
            "-movflags", "+faststart", "-shortest", tmp]
    run(cmd, "son birleştirme")
    os.replace(tmp, out)
