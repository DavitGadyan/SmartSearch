"""Upwork cover image (1600x1000): the liquid backdrop, two tilted screenshots, the title. Usage: python cover.py <repo>"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

repo = Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/dyada/Desktop/Github/SmartSearch")
shots = repo / "docs/portfolio"
W, H = 1600, 1000

bg = Image.open(repo / "frontend/public/img/bg/liquid.webp").convert("RGB")
bg = bg.resize((W, int(W * bg.height / bg.width)), Image.LANCZOS).crop((0, 0, W, H))
veil = Image.new("RGBA", (W, H), (255, 255, 255, 110))
canvas = Image.alpha_composite(bg.convert("RGBA"), veil)


def card(path: Path, width: int, angle: float) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    im = im.resize((width, int(width * im.height / im.width)), Image.LANCZOS)
    r = 28
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    im.putalpha(mask)
    pad = 60
    sheet = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 18, pad + im.width, pad + im.height + 18), r, fill=(20, 30, 60, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    sheet = Image.alpha_composite(sheet, shadow)
    sheet.alpha_composite(im, (pad, pad))
    return sheet.rotate(angle, resample=Image.BICUBIC, expand=True)


back = card(shots / "09-experiment-detail.png", 820, 4)
front = card(shots / "01-home.png", 900, -3)
canvas.alpha_composite(back, (W - back.width + 40, 120))
canvas.alpha_composite(front, (W - front.width - 40, 300))

draw = ImageDraw.Draw(canvas)
serif = ImageFont.truetype("/System/Library/Fonts/NewYork.ttf", 84)
sans = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
draw.text((80, 110), "SmartSearch", font=serif, fill=(17, 17, 17))
draw.text((84, 215), "Ecommerce search, ranking and", font=sans, fill=(55, 53, 47))
draw.text((84, 255), "A/B testing engine", font=sans, fill=(55, 53, 47))
lines = ["Hybrid retrieval · LambdaRank · personalization", "A/B engine with power, CUPED and SRM checks", "Claude agent with agentic checkout", "NDCG@10 0.688 → 0.722 · CTR +4.3% (p = 0.0004)"]
for i, line in enumerate(lines):
    draw.text((84, 330 + i * 40), line, font=small, fill=(111, 110, 106))

out = shots / "00-cover.png"
canvas.convert("RGB").save(out, optimize=True)
print("wrote", out)
