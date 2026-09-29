"""Rasterize stroke icons (Lucide-style paths) to transparent PNGs in slides/icons/ using headless Edge.

Usage: python slides/make_icons.py
"""
import subprocess
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent / "icons"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CELL = 200

ICONS = {
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2M15 20v2M2 15h2M2 9h2M20 15h2M20 9h2M9 2v2M9 20v2"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    "plug": '<path d="M12 22v-5"/><path d="M9 8V2M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "cloud": '<path d="M17.5 19H9a7 7 0 1 1 6.7-9h1.8a4.5 4.5 0 1 1 0 9z"/>',
    "trend": '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
    "alert": '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z"/><path d="M12 9v4M12 17h.01"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z"/>',
    "arrow": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "shieldcheck": '<path d="M20 13c0 5-3.5 7.5-7.7 9a1 1 0 0 1-.6 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.2 1.2 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "pin": '<path d="M20 10c0 5-5.5 10.2-7.4 11.8a1 1 0 0 1-1.2 0C9.5 20.2 4 15 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
    "rocket": '<path d="M4.5 16.5c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9a2.2 2.2 0 0 0-2.9-.1z"/><path d="m12 15-3-3a22 22 0 0 1 2-4A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22.4 22.4 0 0 1-4 2z"/><path d="M9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0"/><path d="M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.8 9.8 0 0 1 6.7 2.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.8 9.8 0 0 1-6.7-2.7L3 16"/><path d="M8 16H3v5"/>',
    "code": '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
    "wifioff": '<path d="M12 20h.01M8.5 16.4a5 5 0 0 1 7 0M5 12.9a10 10 0 0 1 5.2-2.8M19 12.9a10 10 0 0 0-2-1.5M2 8.8a15 15 0 0 1 4.2-2.7M22 8.8a15 15 0 0 0-11.3-3.8M2 2l20 20"/>',
    "scale": '<path d="m16 16 3-8 3 8c-.9.7-1.9 1-3 1s-2.1-.3-3-1z"/><path d="m2 16 3-8 3 8c-.9.7-1.9 1-3 1s-2.1-.3-3-1z"/><path d="M7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    "map": '<path d="M14.1 5.1a2 2 0 0 0 1.8 0l3.7-1.9A1 1 0 0 1 21 4.1v12.8a1 1 0 0 1-.6.9l-4.5 2.3a2 2 0 0 1-1.8 0l-4.2-2.1a2 2 0 0 0-1.8 0l-3.7 1.9A1 1 0 0 1 3 19V6.1a1 1 0 0 1 .6-.9l4.5-2.3a2 2 0 0 1 1.8 0z"/><path d="M15 5.8v15M9 3.2v15"/>',
    "timer": '<path d="M10 2h4M12 14l3-3"/><circle cx="12" cy="14" r="8"/>',
}


# coloured variants: name -> (base icon, stroke colour); everything else is white
VARIANTS = {"arrow_navy": ("arrow", "#0B2545"), "arrow_blue": ("arrow", "#1565C0"), "arrow_teal": ("arrow", "#0F8B8D")}


def main():
    OUT.mkdir(exist_ok=True)
    html_path = OUT.parent / "_icons.html"
    png_path = OUT.parent / "_icons.png"
    jobs = [(n, ICONS[n], "#fff") for n in ICONS] + [(n, ICONS[b], c) for n, (b, c) in VARIANTS.items()]
    names = [n for n, _, _ in jobs]
    cells = "".join(f'<div class="c"><svg viewBox="0 0 24 24" style="stroke:{c}">{body}</svg></div>' for _, body, c in jobs)
    html_path.write_text(
        "<!doctype html><html><head><style>html,body{margin:0;background:transparent}"
        f".c{{width:{CELL}px;height:{CELL}px;float:left;display:flex;align-items:center;justify-content:center}}"
        "svg{width:180px;height:180px;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}"
        f"</style></head><body><div style=\"width:{CELL * len(names)}px\">{cells}</div></body></html>",
        encoding="utf8")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000",
                    f"--window-size={CELL * len(names)},{CELL}", f"--screenshot={png_path}", html_path.as_uri()],
                   check=True, capture_output=True)
    sheet = Image.open(png_path).convert("RGBA")
    for k, n in enumerate(names):
        sheet.crop((k * CELL + 10, 10, k * CELL + CELL - 10, CELL - 10)).save(OUT / f"{n}.png")
    html_path.unlink()
    png_path.unlink()
    print(f"wrote {len(names)} icons to {OUT}")


if __name__ == "__main__":
    main()
