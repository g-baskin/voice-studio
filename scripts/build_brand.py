#!/usr/bin/env python3
"""Generate Voice Studio's logo artwork (SVG). PNG/ICNS are rendered from these by scripts/render_brand.cjs.

The mark tells the product's story in one line: a coarse, stair-stepped, echoing "robotic" waveform
(grey, digital, low resolution) whose steps shrink until it flows into a smooth, warm "human" wave (green).

    uv run python scripts/build_brand.py     # writes docs/assets/*.svg and src/naturalvoice/web/icon*.svg
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GREY_A, GREY_B = "#d3dae0", "#7f8b95"  # cold steel
GREEN_A, GREEN_B = "#8af0bd", "#2fa36b"  # warm, living green
BG_A, BG_B = "#0b1310", "#18271f"


def wave_path(x0, x1, cy, amp, cycles, step0, t_flat, t_smooth, env=None):
    """One continuous path: quantised steps of width step0 that ease to zero between t_flat and t_smooth."""

    def f(x):
        t = (x - x0) / (x1 - x0)
        e = 1.0 if env is None else env(t)
        return cy - amp * e * math.sin(2 * math.pi * cycles * t)

    def step(x):
        t = (x - x0) / (x1 - x0)
        if t <= t_flat:
            return step0
        if t >= t_smooth:
            return 0.0
        u = (t - t_flat) / (t_smooth - t_flat)
        return step0 * (1 - u * u * (3 - 2 * u))  # smoothstep: steps melt away

    pts, x = [], x0
    while x < x1:
        s = step(x)
        if s < 2.2:
            pts.append((x, f(x)))
            x += 1.5
        else:
            y = f(x + s / 2)  # sample-and-hold, like a low-bit-rate converter
            pts += [(x, y), (min(x + s, x1), y)]
            x += s
    pts.append((x1, f(x1)))
    return "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)


def defs(prefix, x_grey, x_green, x0, x1, ghost_end):
    return f"""
    <linearGradient id="{prefix}wave" gradientUnits="userSpaceOnUse" x1="{x_grey}" y1="0" x2="{x_green}" y2="0">
      <stop offset="0" stop-color="{GREY_A}"/><stop offset="0.35" stop-color="{GREY_B}"/>
      <stop offset="0.55" stop-color="{GREEN_A}"/><stop offset="1" stop-color="{GREEN_B}"/>
    </linearGradient>
    <linearGradient id="{prefix}ghost" gradientUnits="userSpaceOnUse" x1="{x0}" y1="0" x2="{ghost_end}" y2="0">
      <stop offset="0" stop-color="{GREY_A}" stop-opacity="0.55"/><stop offset="1" stop-color="{GREY_A}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="{prefix}glow" gradientUnits="userSpaceOnUse" x1="{x_grey}" y1="0" x2="{x_green}" y2="0">
      <stop offset="0.45" stop-color="{GREEN_A}" stop-opacity="0"/><stop offset="0.75" stop-color="{GREEN_A}" stop-opacity="0.9"/>
      <stop offset="1" stop-color="{GREEN_B}" stop-opacity="0.9"/>
    </linearGradient>
    <filter id="{prefix}blur" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="9"/></filter>"""


def wave_group(prefix, d, stroke, echo_dx, echo_dy=0, end_cap=None, echoes_k=(2, 1)):
    echoes = "".join(
        f'<path d="{d}" transform="translate({echo_dx * k} {echo_dy * k})" stroke="url(#{prefix}ghost)" '
        f'stroke-width="{stroke}" opacity="{0.55 / k:.2f}" fill="none" stroke-linejoin="miter"/>'
        for k in echoes_k
    )
    cap = f'<circle cx="{end_cap[0]}" cy="{end_cap[1]}" r="{stroke / 2:.1f}" fill="{GREEN_B}"/>' if end_cap else ""
    return (
        f'{echoes}<path d="{d}" stroke="url(#{prefix}glow)" stroke-width="{stroke * 1.9:.0f}" fill="none" '
        f'filter="url(#{prefix}blur)" stroke-linejoin="round"/>'
        f'<path d="{d}" stroke="url(#{prefix}wave)" stroke-width="{stroke}" fill="none" '
        f'stroke-linejoin="miter" stroke-miterlimit="3" stroke-linecap="butt"/>{cap}'
    )


def icon_svg(inset=0.0, rounded=True, canvas=512):
    """The app icon. inset shrinks the artwork inside the canvas (for maskable / macOS safe zones)."""
    # Few, wide steps then a smooth peak: still reads as 'robotic to human' at 32 px.
    d = wave_path(72, 440, 256, 124, 1.25, 46, 0.30, 0.60)
    pad = canvas * inset
    scale = (canvas - 2 * pad) / canvas
    rx = 112 if rounded else 0
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}" width="{canvas}" height="{canvas}" role="img" aria-label="Voice Studio">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.9" y2="1"><stop offset="0" stop-color="{BG_B}"/><stop offset="1" stop-color="{BG_A}"/></linearGradient>
    <radialGradient id="halo" cx="0.72" cy="0.5" r="0.55"><stop offset="0" stop-color="{GREEN_B}" stop-opacity="0.35"/><stop offset="1" stop-color="{GREEN_B}" stop-opacity="0"/></radialGradient>{defs("i", 72, 330, 72, 440, 260)}
  </defs>
  <rect width="{canvas}" height="{canvas}" rx="{rx}" fill="url(#bg)"/>
  <rect width="{canvas}" height="{canvas}" rx="{rx}" fill="url(#halo)"/>
  <g transform="translate({pad:.1f} {pad:.1f}) scale({scale:.4f})">{wave_group("i", d, 28, 16, end_cap=(440, 132), echoes_k=(1,))}</g>
</svg>
"""


def banner_svg():
    w, h = 1280, 640
    cy, amp = 470, 100
    d = wave_path(
        64, 1216, cy, amp, 5.6, 30, 0.34, 0.56, env=lambda t: 0.55 + 0.45 * math.sin(math.pi * min(1, t * 1.15))
    )
    guides = "".join(
        f'<line x1="0" x2="{w}" y1="{y}" y2="{y}" stroke="#ffffff" stroke-opacity="0.05"/>'
        for y in (cy - amp - 20, cy, cy + amp + 20)
    )
    font = "'SF Pro Display','Helvetica Neue',Inter,'Segoe UI',system-ui,sans-serif"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Voice Studio: make AI voices sound human">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0a110e"/><stop offset="1" stop-color="#14231b"/></linearGradient>
    <radialGradient id="halo" cx="0.78" cy="0.72" r="0.55"><stop offset="0" stop-color="{GREEN_B}" stop-opacity="0.30"/><stop offset="1" stop-color="{GREEN_B}" stop-opacity="0"/></radialGradient>
    <linearGradient id="title" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{GREEN_A}"/><stop offset="1" stop-color="{GREEN_B}"/></linearGradient>{defs("b", 440, 780, 64, 1216, 700)}
  </defs>
  <rect width="{w}" height="{h}" fill="url(#bg)"/>
  <rect width="{w}" height="{h}" fill="url(#halo)"/>
  {guides}
  <g font-family="{font}">
    <text x="80" y="178" font-size="116" font-weight="700" letter-spacing="-3" fill="#f2f6f3">Voice <tspan fill="url(#title)">Studio</tspan></text>
    <text x="84" y="238" font-size="38" font-weight="500" fill="#b6c4bb">Make AI voices sound human.</text>
    <text x="84" y="286" font-size="24" fill="#7f9087">Clean robotic voices  ·  Write voice-overs  ·  Design and clone voices</text>
  </g>
  {wave_group("b", d, 11, 26)}
  <g font-family="{font}" font-size="17" font-weight="600" letter-spacing="3.5">
    <text x="80" y="606" fill="#8c98a1">METALLIC  ·  ECHOEY  ·  ROBOTIC</text>
    <text x="1200" y="606" fill="{GREEN_A}" text-anchor="end">NATURAL</text>
  </g>
</svg>
"""


def main():
    out = {
        ROOT / "src/naturalvoice/web/icon.svg": icon_svg(),
        ROOT / "src/naturalvoice/web/icon-maskable.svg": icon_svg(inset=0.12, rounded=False),
        # macOS app icons keep ~8% transparent margin around the rounded square.
        ROOT / "docs/assets/icon-macos.svg": icon_svg().replace('viewBox="0 0 512 512"', 'viewBox="-48 -48 608 608"'),
        ROOT / "docs/assets/banner.svg": banner_svg(),
    }
    for path, svg in out.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg)
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
