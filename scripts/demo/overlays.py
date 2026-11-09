"""Text layers for the demo video (this ffmpeg has no drawtext): title/outro cards and one lower-third per scene.
Usage: python overlays.py <work_dir> <scenes.tsv>   (tsv: name<TAB>title<TAB>subtitle)"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

work = Path(sys.argv[1]); scenes = Path(sys.argv[2])
W, H = 1920, 1080
SERIF = "/System/Library/Fonts/NewYork.ttf"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
INK = (17, 17, 17, 255); INK2 = (55, 53, 47, 255); MUTED = (111, 110, 106, 255)

def centered(draw, y, text, font, fill, max_w=W - 200):
    size = font.size
    while draw.textlength(text, font=font) > max_w and size > 18:
        size -= 2; font = ImageFont.truetype(font.path, size)
    w = draw.textlength(text, font=font); draw.text(((W - w) / 2, y), text, font=font, fill=fill)

def card(name, head, sub1, sub2):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    centered(d, H / 2 - 190, head, ImageFont.truetype(SERIF, 124), INK)
    centered(d, H / 2 + 0, sub1, ImageFont.truetype(SANS, 42), INK2)
    centered(d, H / 2 + 76, sub2, ImageFont.truetype(SANS, 29), MUTED)
    im.save(work / f"{name}.png")

card("intro_text", "SmartSearch", "Commerce Intelligence Engine",
     "Hybrid search  ·  Learning to rank  ·  Personalization  ·  A/B testing  ·  Agentic checkout")
card("outro_text", "What is inside", "NDCG@10 0.688 → 0.722 offline   ·   CTR +4.3% (p = 0.0004) online   ·   48k users per arm for a 5% MDE",
     "FastAPI · PostgreSQL · LightGBM · model2vec · Next.js · Claude          github.com/DavitGadyan/SmartSearch")

tf = ImageFont.truetype(SERIF, 50); sf = ImageFont.truetype(SANS, 27)
for line in scenes.read_text().splitlines():
    if not line.strip(): continue
    name, title, sub = line.split("\t")
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    tw = max(d.textlength(title, font=tf), d.textlength(sub, font=sf)) + 72
    x0, y0, bw, bh = 64, H - 222, int(tw), 140
    # frosted dark panel: blurred shadow + translucent charcoal + hairline highlight
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0)); pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((x0, y0 + 10, x0 + bw, y0 + bh + 10), 26, fill=(20, 30, 60, 70))
    panel = panel.filter(ImageFilter.GaussianBlur(14)); im.alpha_composite(panel)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 26, fill=(17, 17, 17, 150), outline=(255, 255, 255, 60), width=1)
    d.text((x0 + 36, y0 + 22), title, font=tf, fill=(255, 255, 255, 255))
    d.text((x0 + 38, y0 + 90), sub, font=sf, fill=(232, 232, 232, 255))
    im.save(work / f"cap_{name}.png")
print("overlays ok")
