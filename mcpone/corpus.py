# /// script
# requires-python = ">=3.12"
# dependencies = ["Pillow==11.3.0"]
# ///
"""Generate synthetic, public OCR inputs; no personal documents are used."""
import argparse
import hashlib
import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument("out", type=Path)
parser.add_argument("--font", type=Path, default=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype(str(args.font), 36)
texts = {
    "eng": "The quick brown fox jumps over the lazy dog.\nInvoice number 2048 is due on 22 November 2026.\nPlease send three blue folders and seven white pens.\nA clear scan preserves punctuation, spaces, and 123.45.",
    "deu": "Grüße aus München: Äpfel, Öl und süßer Käse.\nDie Straße führt über die Brücke zum großen Büro.\nFünf Bücher kosten 123,45 Euro für zwölf Schüler.\nÄÖÜ äöü ß: schön, größer, äußerst zuverlässig.",
}
identifiers = "ABO0I1l5S8B\nINV-2026-O0I1-0058\nDE89 3704 0044 0532 0130 00"
cases = []
def save(name, language, text, kind):
    image = Image.new("L", (1200, 340), 255)
    draw = ImageDraw.Draw(image)
    draw.multiline_text((40, 32), text, font=font, fill=0, spacing=18)
    if kind == "degraded":
        image = image.resize((600, 170), Image.Resampling.LANCZOS).resize(image.size, Image.Resampling.BILINEAR)
        image = image.filter(ImageFilter.GaussianBlur(0.65)).rotate(1.3, resample=Image.Resampling.BICUBIC, fillcolor=255)
        rng = random.Random(20261122)
        image = image.point(lambda p: int(60 + p * 0.68))
        pixels = image.load()
        for _ in range(5000):
            x, y = rng.randrange(image.width), rng.randrange(image.height)
            pixels[x, y] = max(0, min(255, pixels[x, y] + rng.randrange(-65, 66)))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=38)
        image = Image.open(io.BytesIO(buffer.getvalue())).convert("L")
    filename = name + ".png"
    image.save(args.out / filename, dpi=(300, 300))
    cases.append({"name": name, "lang": language, "kind": kind, "image": filename, "text": text,
                  "sha256": hashlib.sha256((args.out / filename).read_bytes()).hexdigest()})
for language, text in texts.items():
    for kind in ("clean", "degraded"):
        save(f"{kind}-{language}", language, text, kind)
    save(f"identifiers-{language}", language, identifiers, "identifiers")
    save(f"blank-{language}", language, "", "blank")
save("mixed", "eng+deu", "Please send Grüße aus München.\nThe Straße leads to the blue Büro.", "mixed")
for language, text in texts.items():
    image = Image.new("L", (2480, 3508), 255)
    page_text = "\n".join(text.splitlines() * 12)
    ImageDraw.Draw(image).multiline_text((80, 60), page_text, font=font, fill=0, spacing=25)
    filename = f"page-{language}.png"
    image.save(args.out / filename, dpi=(300, 300))
    cases.append({"name": f"page-{language}", "lang": language, "kind": "page", "image": filename,
                  "text": page_text, "sha256": hashlib.sha256((args.out / filename).read_bytes()).hexdigest()})
# Exercise each built-in/linked decoder with identical pixels as well.
clean = Image.open(args.out / "clean-eng.png")
clean.save(args.out / "clean-eng.jpg", quality=95, dpi=(300, 300))
clean.save(args.out / "clean-eng.bmp")
clean.save(args.out / "clean-eng.pnm")
(args.out / "manifest.json").write_text(json.dumps({"font_sha256": hashlib.sha256(args.font.read_bytes()).hexdigest(), "pillow": "11.3.0", "cases": cases}, ensure_ascii=False, indent=2) + "\n")
print(f"Generated {len(cases)} cases in {args.out}")
