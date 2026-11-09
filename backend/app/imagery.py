"""Product imagery: art-directed prompts from catalog text plus a thin Higgsfield REST client (docs.higgsfield.ai).

WANDS ships no photos. Prompts are built from name, class, category path and parsed attributes so the picture depicts
the catalog item rather than a generic one; the storefront labels every image as generated."""

import io
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from app.core.config import settings

API_BASE = "https://api.higgsfield.ai"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}
NEGATIVE = (
    "text, watermark, logo, people, hands, collage, split image, several products, cartoon, illustration"
)
# alias -> (endpoint path, fixed params). Prompt enhancement is off so the prompt stays literal to the catalog row.
MODELS = {
    "qwen": (
        "alibaba/qwen-image-3/text-to-image",
        {"resolution": "1k", "prompt_extend": False, "enable_thinking": False, "negative_prompt": NEGATIVE},
    ),
    "soul": ("higgsfield-ai/soul/standard", {"resolution": "1080p", "enhance_prompt": False}),
    "z-image": ("z-image/turbo", {}),
}
SIZE = 768  # square webp; cards render at <= 480px
ATTR_ORDER = ("color", "material", "wood_tone", "style", "shape", "pattern")


def _singular(kind: str) -> str:
    return kind[:-1] if kind.endswith("s") and not kind.endswith("ss") else kind


def _lead(text: str, max_words: int = 45) -> str:
    """Leading whole sentences of a description, up to max_words."""
    out: list[str] = []
    for sent in (text or "").replace("\n", " ").split(". "):
        if len(" ".join(out + [sent]).split()) > max_words:
            break
        out.append(sent.strip().rstrip("."))
    return ". ".join(s for s in out if s) + ("." if out and out[0] else "")


def product_prompt(p: dict) -> str:
    """p: name, product_class, category_hierarchy, attributes, description (DB row as dict)."""
    attrs = p.get("attributes") or {}
    traits: list[str] = []
    for k in ATTR_ORDER:
        v = str(attrs.get(k) or "").lower()
        if v and not set(v.split()) <= set(" ".join(traits).split()):
            traits.append(v)
    path = [s.strip() for s in (p.get("category_hierarchy") or "").split("/") if s.strip()]
    kind = (
        (p.get("product_class") or (path[-1] if path else "home furnishing")).split("|")[-1].strip().lower()
    )
    outdoor = bool(path) and path[0].lower().startswith("outdoor")
    setting = (
        "on a sunlit patio, soft natural light"
        if outdoor
        else "in a bright minimalist studio, soft diffused daylight, plain light warm-grey seamless background"
    )
    subject = f"{' '.join(traits[:4])} {_singular(kind)}".strip()
    return (
        f"Ecommerce product photograph of a {subject}: {p['name']}. {_lead(p.get('description'))} "
        f"Single product centred, three-quarter view, whole item visible, {setting}, true-to-life materials and "
        "proportions, sharp focus, photorealistic catalog style. No text, no watermark, no people."
    ).replace("  ", " ")


def save_image(data: bytes, dest: Path) -> Path:
    """Centre-crop to square, downscale to SIZE and store as webp (small enough to commit)."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((SIZE, SIZE), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "WEBP", quality=82, method=6)
    return dest


def fetch(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


class HiggsfieldError(RuntimeError):
    pass


class Higgsfield:
    """Submit + poll; `Authorization: Key <id>:<secret>`; terminal statuses completed | failed | nsfw | canceled."""

    def __init__(self, key_id: str, secret: str):
        self.auth = f"Key {key_id}:{secret}"

    @classmethod
    def from_settings(cls) -> "Higgsfield | None":
        if settings.hf_api_key_id and settings.hf_api_key_secret:
            return cls(settings.hf_api_key_id, settings.hf_api_key_secret)
        return None

    def _call(self, url: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Authorization", self.auth)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise HiggsfieldError(f"{e.code} on {url}: {e.read().decode('utf-8', 'replace')[:300]}") from e
        except urllib.error.URLError as e:
            raise HiggsfieldError(f"unreachable: {e.reason}") from e

    def submit(self, prompt: str, model: str, aspect_ratio: str = "1:1", seed: int | None = None) -> str:
        path, params = MODELS.get(model, (model, {}))
        payload = {"prompt": prompt, "aspect_ratio": aspect_ratio, **params}
        if seed is not None:
            payload["seed"] = seed
        res = self._call(f"{API_BASE}/{path}", payload)
        if not res.get("request_id"):
            raise HiggsfieldError(f"unexpected submit response: {res}")
        return res["request_id"]

    def wait(self, request_id: str, timeout: float = 300) -> dict:
        deadline, delay = time.monotonic() + timeout, 2.0
        while True:
            res = self._call(f"{API_BASE}/requests/{request_id}/status")
            if res.get("status") in TERMINAL:
                return res
            if time.monotonic() > deadline:
                raise HiggsfieldError(f"{request_id} not finished after {timeout:.0f}s")
            time.sleep(delay + random.uniform(0, 0.5))
            delay = min(delay * 1.5, 10)

    def result_url(self, request_id: str, timeout: float = 300) -> str:
        res = self.wait(request_id, timeout)
        urls = [i["url"] for i in res.get("images", []) if i.get("url")]
        if res.get("status") != "completed" or not urls:
            raise HiggsfieldError(f"{request_id} ended as {res.get('status')}")
        return urls[0]
