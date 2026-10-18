"""Command line: voicestudio clean | speak | analyze | voices | serve"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _settings_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--preset", default="standard", choices=["light", "standard", "strong"])
    for name in ("ai-clean", "dereverb", "demetal", "deharsh", "warmth", "denoise", "room-tone"):
        p.add_argument(f"--{name}", type=float, help="0..1, overrides the preset")
    p.add_argument("--loudness", type=float, help="target LUFS (default -16)")


def _settings(a):
    from .humanize import get_settings

    return get_settings(
        a.preset,
        ai_clean=a.ai_clean,
        dereverb=a.dereverb,
        demetal=a.demetal,
        deharsh=a.deharsh,
        warmth=a.warmth,
        denoise=a.denoise,
        room_tone=a.room_tone,
        loudness=a.loudness,
    )


def clean_file(src: str, dst: str, settings, progress=None) -> dict:
    from . import audio, analyze
    from .humanize import humanize

    data, sr = audio.load(src)
    before = analyze.report(data, sr)
    out = humanize(data, sr, settings, progress)
    if audio.is_video(src) and audio.is_video(dst):
        audio.remux_video(src, out, sr, dst)
    else:
        audio.save(dst, out, sr)
    return {"before": before, "after": analyze.report(out, sr), "output": str(dst)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="voicestudio", description="Make AI voices sound human: no metallic tone, no echo."
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clean", help="clean an existing audio or video file")
    c.add_argument("input")
    c.add_argument("-o", "--output", help="output file (default: <name>.natural.<ext>)")
    _settings_args(c)

    s = sub.add_parser("speak", help="turn text into a natural voice")
    s.add_argument("text", help="text, or @file.txt to read from a file")
    s.add_argument("-o", "--output", default="speech.wav")
    s.add_argument("--voice", default="af_heart")
    s.add_argument("--speed", type=float, default=1.0)
    s.add_argument("--engine", default="kokoro", choices=["kokoro", "clone", "elevenlabs", "openai"])
    s.add_argument("--raw", action="store_true", help="skip the humanize chain (for comparison)")

    an = sub.add_parser("analyze", help="measure echo / metallic / harshness of a file")
    an.add_argument("input")

    vo = sub.add_parser("voices", help="list voices: stock plus your custom and cloned voices")
    vo.add_argument("--json", action="store_true", help="full records as JSON")
    vo.add_argument("--starred", action="store_true", help="only starred voices")

    b = sub.add_parser("bench", help="benchmark the cleanup on known-damaged speech")
    b.add_argument("--out", default="bench")
    b.add_argument("--quick", action="store_true", help="one voice instead of three")

    sv = sub.add_parser("serve", help="start the web app")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--open", action="store_true", help="open it in the browser")

    r = sub.add_parser("render", help="render a Studio project file (JSON) to mix, captions, stems")
    r.add_argument("project")
    r.add_argument("-o", "--out", default=None, help="output folder (default: <project>-render)")
    r.add_argument("--target", choices=["podcast", "youtube", "broadcast", "acx", "raw"], default="podcast")
    r.add_argument("--format", choices=["wav", "flac", "mp3"], default="wav")
    r.add_argument("--rate", type=int, choices=[24000, 44100, 48000], default=None)
    r.add_argument("--stems", action="store_true")
    r.add_argument("--video", default=None, help="video to dub (mp4/mov/webm/mkv)")
    r.add_argument("--video-audio", choices=["replace", "duck"], default="replace")

    d = sub.add_parser("dub", help="voice a .srt/.vtt in timed mode with one voice (optionally onto a video)")
    d.add_argument("subtitles")
    d.add_argument("--voice", required=True)
    d.add_argument("--video", default=None)
    d.add_argument("--video-audio", choices=["replace", "duck"], default="replace")
    d.add_argument("--target", choices=["podcast", "youtube", "broadcast", "acx", "raw"], default="youtube")
    d.add_argument("--format", choices=["wav", "flac", "mp3"], default="wav")
    d.add_argument("-o", "--out", default=None)

    a = ap.parse_args(argv)

    if a.cmd in {"render", "dub"}:
        from . import studio

        try:
            res = studio.cli_render(a)
        except (studio.StudioError, ValueError, FileNotFoundError, RuntimeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(json.dumps(res, indent=2))
        return 0 if not res["errors"] else 1

    if a.cmd == "clean":
        src = Path(a.input)
        dst = a.output or str(src.with_name(f"{src.stem}.natural{src.suffix}"))
        res = clean_file(
            str(src), dst, _settings(a), progress=lambda name, f: print(f"[{int(f * 100):3d}%] {name}", file=sys.stderr)
        )
        print(json.dumps(res, indent=2))
    elif a.cmd == "speak":
        from . import audio, tts

        text = Path(a.text[1:]).read_text() if a.text.startswith("@") else a.text
        out, sr = tts.speak(text, a.voice, a.speed, a.engine, humanize=not a.raw)
        audio.save(a.output, out, sr)
        print(a.output)
    elif a.cmd == "analyze":
        from . import audio, analyze

        data, sr = audio.load(a.input)
        print(json.dumps(analyze.report(data, sr), indent=2))
    elif a.cmd == "voices":
        from . import voices as vlib

        cat = [v for v in vlib.catalog() if v.get("starred") or not a.starred]
        if a.json:
            print(json.dumps(cat, indent=2))
        else:
            for v in cat:
                print(f"{'*' if v.get('starred') else ' '} {v['id']:<22} {v.get('kind', ''):<7} {v.get('name', '')}")
    elif a.cmd == "bench":
        from . import bench

        results = bench.run(a.out, quick=a.quick, log=lambda m: print(m, file=sys.stderr))
        print(bench.render(results))
    elif a.cmd == "serve":
        import uvicorn

        if a.open:
            import threading
            import webbrowser

            threading.Timer(1.5, lambda: webbrowser.open(f"http://{a.host}:{a.port}")).start()
        uvicorn.run("naturalvoice.server:app", host=a.host, port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
