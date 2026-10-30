"""Create the bot welcome banner. Requires Pillow; not needed at runtime."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 2400, 1200
OUT = Path(__file__).resolve().parents[1] / "app" / "assets" / "welcome.png"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def add_glow(image: Image.Image, xy, radius: int, color, alpha: int) -> None:
    layer = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(layer)
    x, y = xy
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    image.alpha_composite(layer)


def neon_card(kind: str, angle: float) -> Image.Image:
    card = Image.new("RGBA", (360, 360))
    glow = Image.new("RGBA", card.size)
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle((55, 55, 305, 305), radius=55, outline=(174, 51, 255, 230), width=18)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    card.alpha_composite(glow)
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (55, 55, 305, 305),
        radius=55,
        fill=(22, 8, 43, 235),
        outline=(195, 100, 255, 255),
        width=5,
    )
    draw.rounded_rectangle((72, 72, 288, 288), radius=43, outline=(92, 36, 150, 255), width=3)
    color = (235, 215, 255, 255)
    accent = (196, 91, 255, 255)
    if kind == "camera":
        draw.rounded_rectangle((115, 145, 245, 225), radius=20, outline=color, width=10)
        draw.polygon([(245, 165), (280, 145), (280, 225), (245, 205)], outline=color)
        draw.ellipse((148, 158, 205, 215), outline=accent, width=9)
        draw.rounded_rectangle((140, 125, 190, 148), radius=8, fill=accent)
    elif kind == "chat":
        draw.rounded_rectangle((105, 115, 260, 230), radius=35, outline=color, width=10)
        draw.polygon([(140, 224), (128, 265), (177, 230)], fill=color)
        for x in (145, 182, 219):
            draw.ellipse((x - 8, 166, x + 8, 182), fill=accent)
    else:
        draw.rounded_rectangle((130, 105, 235, 255), radius=20, outline=color, width=9)
        draw.line((155, 145, 212, 145), fill=accent, width=9)
        draw.line((155, 180, 212, 180), fill=accent, width=9)
        draw.line((155, 215, 195, 215), fill=accent, width=9)
    return card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


def paste_center(image: Image.Image, element: Image.Image, center) -> None:
    x = int(center[0] - element.width / 2)
    y = int(center[1] - element.height / 2)
    image.alpha_composite(element, (x, y))


def centered_text(image: Image.Image, text: str, y: int, text_font, fill, glow_color=None) -> None:
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), text, font=text_font, stroke_width=1)
    width = box[2] - box[0]
    x = (W - width) // 2
    if glow_color:
        glow = Image.new("RGBA", image.size)
        gd = ImageDraw.Draw(glow)
        gd.text((x, y), text, font=text_font, fill=glow_color, stroke_width=5, stroke_fill=glow_color)
        glow = glow.filter(ImageFilter.GaussianBlur(22))
        image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)
    draw.text(
        (x, y),
        text,
        font=text_font,
        fill=fill,
        stroke_width=2,
        stroke_fill=(84, 35, 125, 255),
    )


def pill(image: Image.Image, text: str, y: int, text_font) -> None:
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), text, font=text_font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    pad_x, pad_y = 42, 22
    x1 = (W - width) // 2 - pad_x
    x2 = (W + width) // 2 + pad_x
    draw.rounded_rectangle(
        (x1, y, x2, y + height + pad_y * 2),
        radius=35,
        fill=(30, 14, 51, 210),
        outline=(142, 83, 185, 190),
        width=2,
    )
    draw.text(((W - width) // 2, y + pad_y - box[1]), text, font=text_font, fill=(218, 196, 235, 255))


def main() -> None:
    random.seed(7)
    base = Image.new("RGBA", (W, H), (5, 3, 13, 255))
    draw = ImageDraw.Draw(base)
    top = (5, 3, 16)
    bottom = (24, 4, 39)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(math.floor(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, W, y), fill=(*color, 255))

    add_glow(base, (180, 180), 430, (116, 20, 201), 150)
    add_glow(base, (2180, 200), 460, (179, 24, 224), 135)
    add_glow(base, (1950, 1080), 500, (92, 20, 190), 125)
    add_glow(base, (500, 1100), 400, (214, 21, 149), 70)

    beams = Image.new("RGBA", (W, H))
    bd = ImageDraw.Draw(beams)
    bd.polygon([(0, 850), (0, 1080), (1300, 220), (1150, 160)], fill=(143, 38, 232, 35))
    bd.polygon([(2400, 700), (2400, 930), (1150, 230), (1280, 180)], fill=(229, 51, 218, 28))
    beams = beams.filter(ImageFilter.GaussianBlur(35))
    base.alpha_composite(beams)

    particles = Image.new("RGBA", (W, H))
    pd = ImageDraw.Draw(particles)
    for _ in range(125):
        x = random.randrange(30, W - 30)
        y = random.randrange(30, H - 30)
        r = random.choice((2, 2, 3, 4, 6))
        color = random.choice(((210, 129, 255, 150), (255, 93, 220, 130), (152, 97, 255, 140)))
        pd.ellipse((x - r, y - r, x + r, y + r), fill=color)
    base.alpha_composite(particles.filter(ImageFilter.GaussianBlur(1)))

    paste_center(base, neon_card("camera", 13), (235, 245))
    paste_center(base, neon_card("chat", -12), (2160, 260))
    small_left = neon_card("message", -18).resize((270, 270), Image.Resampling.LANCZOS)
    small_right = neon_card("camera", 18).resize((250, 250), Image.Resampling.LANCZOS)
    paste_center(base, small_left, (180, 970))
    paste_center(base, small_right, (2190, 930))

    pill(base, "MESSAGE KEEPER", 120, font(38, bold=False))
    centered_text(base, "ДОБРО", 310, font(148), (250, 247, 255, 255), (146, 48, 255, 180))
    centered_text(base, "ПОЖАЛОВАТЬ", 490, font(128), (250, 247, 255, 255), (185, 45, 230, 170))
    pill(base, "СОХРАНЯЕМ ВАЖНОЕ", 760, font(36, bold=False))

    # Subtle vignette keeps attention on the title.
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-350, -280, W + 350, H + 380), fill=215)
    vignette = vignette.filter(ImageFilter.GaussianBlur(170))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 95))
    dark.putalpha(Image.eval(vignette, lambda value: 255 - value))
    base.alpha_composite(dark)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = base.convert("RGB").resize((1200, 600), Image.Resampling.LANCZOS)
    result.save(OUT, quality=95, optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
