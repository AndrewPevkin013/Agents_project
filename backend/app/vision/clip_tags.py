"""
clip_tags.py — zero-shot теги и визуальный эмбеддинг чертежа через CLIP/SigLIP.

    pip install torch open_clip_torch

Использование из visual.py:
    from clip_tags import ClipTagger
    tagger = ClipTagger()                      # ViT-B-32 по умолчанию, ~600 МБ, CPU ок
    res = tagger(Path("drawing/x.png"))
    res["domain"]      -> [("mechanical part drawing", 0.71), ...]
    res["part_kind"]   -> [("flange", 0.33), ("bushing", 0.21), ...]
    res["embedding"]   -> np.ndarray (512,) L2-нормированный — для image-to-image поиска
"""
from __future__ import annotations

from pathlib import Path
import numpy as np

try:
    import torch
    import open_clip
    HAS_CLIP = True
except ImportError:          # torch/open_clip отсутствуют — ClipTagger бросит ImportError
    torch = None
    open_clip = None
    HAS_CLIP = False
from PIL import Image

# закрытые словари — CLIP выбирает ближайшую подпись; формулировки важны
DOMAINS = {
    "mechanical part drawing":    "a mechanical engineering drawing of a single machined part with dimensions",
    "assembly drawing":           "a mechanical assembly drawing with numbered parts and a parts list",
    "architectural floor plan":   "an architectural floor plan of a building with rooms and walls",
    "plumbing / piping diagram":  "a plumbing or piping schematic with pipes, valves and fixtures",
    "electrical schematic":       "an electrical circuit schematic diagram",
    "pcb layout":                 "a printed circuit board layout",
    "structural / steel drawing": "a structural steel or construction drawing with beams and columns",
    "sketch / illustration":      "a hand sketch or textbook illustration of a technical object",
}

PART_KINDS = {
    "flange": "a round flange with a bolt circle", "bracket": "an L-shaped mounting bracket",
    "shaft": "a long stepped cylindrical shaft", "gear": "a toothed gear wheel",
    "housing": "a box-like housing or casing", "cover": "a flat cover plate with holes",
    "bushing": "a short hollow cylindrical bushing or sleeve", "plate": "a flat plate with holes",
    "bolt": "a threaded bolt or screw", "nut": "a hexagonal nut", "pin": "a small cylindrical pin",
    "spring": "a coil spring", "bearing": "a ball bearing", "pulley": "a pulley or sheave",
    "lever": "a lever or arm", "pipe fitting": "a pipe elbow or tee fitting",
    "valve body": "a valve body", "frame": "a welded frame structure",
}


class ClipTagger:
    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k",
                 device: str | None = None):
        if not HAS_CLIP:
            raise ImportError("pip install torch open_clip_torch")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model, _, self.pre = open_clip.create_model_and_transforms(
            model, pretrained=pretrained, device=self.device)
        self.model.eval()
        self.tok = open_clip.get_tokenizer(model)
        self._dom = self._encode_texts([f"{v}." for v in DOMAINS.values()])
        self._kind = self._encode_texts([f"an engineering drawing of {v}." for v in PART_KINDS.values()])

    def _encode_texts(self, texts: list[str]) -> torch.Tensor:
        with torch.no_grad():
            t = self.model.encode_text(self.tok(texts).to(self.device))
        return t / t.norm(dim=-1, keepdim=True)

    def embed(self, path: Path) -> torch.Tensor:
        img = self.pre(Image.open(path).convert("RGB")).unsqueeze(0).to(self.device)
        with torch.no_grad():
            v = self.model.encode_image(img)
        return v / v.norm(dim=-1, keepdim=True)

    def __call__(self, path: Path, top_k: int = 3) -> dict:
        v = self.embed(path)
        with torch.no_grad():
            scale = self.model.logit_scale.exp()
            dom_t = (scale * v @ self._dom.T).softmax(-1)[0]
            kind_t = (scale * v @ self._kind.T).softmax(-1)[0]
        dom = dom_t.cpu().numpy(); kind = kind_t.cpu().numpy()
        dn, kn = list(DOMAINS), list(PART_KINDS)
        return {
            "domain": [(dn[i], float(dom[i])) for i in dom.argsort()[::-1][:top_k]],
            "part_kind": [(kn[i], float(kind[i])) for i in kind.argsort()[::-1][:top_k]],
            "embedding": v[0].cpu().numpy().astype(np.float32),
        }