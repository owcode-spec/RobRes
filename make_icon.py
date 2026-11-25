"""Generate app icon assets: icon.png + icon.ico (multi-size).
Uses Pillow so it works without a Qt display / platform plugin.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

ASSETS = Path(__file__).resolve().parent / "assets"

BLUE = (99, 102, 241, 255)      # #6366F1
PURPLE = (168, 85, 247, 255)    # #A855F7
WHITE = (255, 255, 255, 255)
BORDER_WHITE = (255, 255, 255, 40)


def draw_icon(size: int) -> Image.Image:
    """Draw a single icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    pad = int(size * 0.06)
    r = (pad, pad, size - pad, size - pad)
    radius = int(size * 0.22)

    # Diagonal gradient: blue → purple.
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    maxd = (size * 2) ** 0.5
    for y in range(size):
        for x in range(size):
            t = min(1.0, (x + y) / maxd)
            rr = int(BLUE[0] + (PURPLE[0] - BLUE[0]) * t)
            gg = int(BLUE[1] + (PURPLE[1] - BLUE[1]) * t)
            bb = int(BLUE[2] + (PURPLE[2] - BLUE[2]) * t)
            grad.putpixel((x, y), (rr, gg, bb, 255))

    # Rounded rect mask.
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle(r, radius=radius, fill=255)

    # Composite gradient onto image using the mask.
    img = Image.composite(grad, img, mask)
    draw = ImageDraw.Draw(img)

    # Border stroke.
    draw.rounded_rectangle(r, radius=radius, outline=BORDER_WHITE, width=max(1, int(size * 0.015)))

    # Text "4:3".
    text = "4:3"
    font_size = int(size * 0.40)
    font = None
    for font_path in [
        "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold
        "C:/Windows/Fonts/segoeui.ttf",    # Segoe UI
        "C:/Windows/Fonts/arialbd.ttf",    # Arial Bold
        "C:/Windows/Fonts/arial.ttf",      # Arial
    ]:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Get text bounding box for centering.
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=0)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1]
    draw.text((tx, ty), text, font=font, fill=WHITE)

    return img


def png_bytes(img: Image.Image) -> bytes:
    """Encode an RGBA image as PNG bytes."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_ico(images: dict[int, Image.Image], output_path: Path) -> None:
    """Write a multi-size ICO file with PNG-encoded images."""
    sizes = sorted(images.keys())
    count = len(sizes)

    # Header: reserved(2), type=1(2), count(2)
    header = struct.pack("<HHH", 0, 1, count)

    # Build directory entries and collect image data.
    entries = b""
    image_data = b""
    offset = 6 + 16 * count  # header + directory entries

    for size in sizes:
        data = png_bytes(images[size])
        w = size if size < 256 else 0   # 0 means 256 in ICO
        h = size if size < 256 else 0
        entry = struct.pack("<BBBBHHII",
                            w, h, 0, 0,       # width, height, color count, reserved
                            1, 32,            # planes, bit count
                            len(data), offset) # size in bytes, offset
        entries += entry
        image_data += data
        offset += len(data)

    output_path.write_bytes(header + entries + image_data)


def main() -> None:
    sizes = [16, 20, 24, 32, 48, 64, 128, 256]
    images: dict[int, Image.Image] = {}

    for size in sizes:
        images[size] = draw_icon(size)

    # Save the largest as icon.png (used by app_icon() at runtime).
    png_path = ASSETS / "icon.png"
    images[256].save(png_path, "PNG")
    print(f"Wrote {png_path} (256x256)")

    # Write multi-size ICO (used by PyInstaller --icon).
    ico_path = ASSETS / "icon.ico"
    write_ico(images, ico_path)
    print(f"Wrote {ico_path}")


if __name__ == "__main__":
    main()
