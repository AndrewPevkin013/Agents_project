#!/usr/bin/env python3
"""
visual.py — анализ инженерных чертежей.

Структура:
    visual.py
    drawing/            <- сюда кладём чертежи (PNG/JPG/TIF)
    out/                <- сюда пишутся результаты (.md, .json, *_annotated.png)

Зависимости:
    pip install opencv-python numpy pillow rapidocr-onnxruntime

Запуск:
    python visual.py               # обработать всё из drawing/
    python visual.py --make-tests  # создать 2 тестовых чертежа в drawing/ и обработать
    python visual.py --vlm anthropic          # + описание от Claude (ANTHROPIC_API_KEY)
    python visual.py --vlm openai             # + описание от GPT-4o  (OPENAI_API_KEY)
    python visual.py --vlm ollama --model qwen2.5vl:7b   # локально через Ollama
    python visual.py --ocr easyocr            # латиница с диакритикой (es/ca/de/fr/nl)
    python visual.py --clip                   # CLIP-теги + визуальный эмбеддинг (out/*.clip.npy)
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from rapidocr_onnxruntime import RapidOCR
    _OCR = RapidOCR()
    HAS_OCR = True
except ImportError:
    _OCR = None
    HAS_OCR = False

_EASY = None            # ленивая инициализация EasyOCR (кириллица), см. run_ocr
OCR_UPSCALE = 2.0       # мелкие сканы апскейлим перед OCR
OCR_LANGS = ("en", "es", "fr", "de", "nl", "it")   # для easyocr; каталанские диакритики покрыты общей латинской моделью

HERE = Path(__file__).resolve().parent
DRAWING_DIR = HERE / "drawing"
OUT_DIR = HERE / "out"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
PDF_DPI = 200

# ------------------------------------------------------------------ данные

@dataclass
class TextRegion:
    x: int
    y: int
    w: int
    h: int
    text: str = ""
    conf: float = 0.0

@dataclass
class DrawingReport:
    file: str
    width: int
    height: int
    ink_ratio: float
    n_lines: int
    n_horizontal: int
    n_vertical: int
    n_diagonal: int
    circles: list[tuple[int, int, int]]
    n_rectangles: int
    n_contours: int
    has_border: bool
    has_title_block: bool
    text_regions: list[TextRegion] = field(default_factory=list)
    ocr_text: str = ""
    scan: dict = field(default_factory=dict)
    diagram: dict = field(default_factory=dict)      # nodes/edges для блок-схем

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

# ------------------------------------------------------------------ подготовка сканов

@dataclass
class ScanInfo:
    is_scan: bool = False
    skew_deg: float = 0.0
    noise: float = 0.0          # доля изолированных чёрных пикселей (пыль копира)
    background: int = 255       # медианная яркость фона
    contrast: float = 1.0       # (фон - чернила) / 255
    applied: list = field(default_factory=list)

def estimate_skew(gray: np.ndarray) -> float:
    """Угол перекоса по длинным почти-горизонтальным линиям (Хаф)."""
    edges = cv2.Canny(gray, 50, 150)
    h, w = gray.shape
    lines = cv2.HoughLinesP(edges, 1, np.pi / 720, threshold=120,
                            minLineLength=max(w, h) // 8, maxLineGap=10)
    if lines is None:
        return 0.0
    angs = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if abs(a) < 15:                       # почти горизонтальные
            angs.append(a)
        elif abs(abs(a) - 90) < 15:           # почти вертикальные → приводим к горизонтали
            angs.append(a - 90 if a > 0 else a + 90)
    if len(angs) < 5:
        return 0.0
    return float(np.median(angs))

def rotate_keep(img: np.ndarray, deg: float) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    fill = (255, 255, 255) if img.ndim == 3 else 255
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=fill)

def analyze_scan_quality(gray: np.ndarray) -> ScanInfo:
    info = ScanInfo()
    info.background = int(np.median(gray))
    dark = gray[gray < 128]
    ink_level = int(np.median(dark)) if dark.size > 100 else 0
    info.contrast = round((info.background - ink_level) / 255.0, 3)
    binv = (gray < 128).astype(np.uint8)
    # изолированные пиксели: чёрные, у которых нет чёрных соседей
    neigh = cv2.filter2D(binv, -1, np.ones((3, 3), np.float32)) - binv
    isolated = int(((binv == 1) & (neigh == 0)).sum())
    info.noise = round(isolated / max(int(binv.sum()), 1), 4)
    info.skew_deg = round(estimate_skew(gray), 2)
    info.is_scan = (info.background < 235 or info.noise > 0.01 or abs(info.skew_deg) > 0.4
                    or info.contrast < 0.6)
    return info

def clean_scan(img: np.ndarray, info: ScanInfo) -> np.ndarray:
    """Deskew → шумоподавление → выравнивание фона → CLAHE. Возвращает BGR."""
    out = img.copy()
    if abs(info.skew_deg) > 0.3:
        out = rotate_keep(out, info.skew_deg); info.applied.append(f"deskew {info.skew_deg:+.2f}°")
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    if info.noise > 0.005:
        gray = cv2.medianBlur(gray, 3); info.applied.append("median3")
        if gray.size <= 4_000_000:                       # NL-means дорог на больших сканах
            gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
            info.applied.append("nlmeans")
        else:
            gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8)); info.applied.append("close2")
    if info.background < 235:
        # вычитание фона: делим на сильно размытую копию → ровный белый фон
        bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(gray.shape) / 60)
        gray = cv2.divide(gray, bg, scale=255); info.applied.append("flatten-bg")
    if info.contrast < 0.75:
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray); info.applied.append("clahe")
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

# ------------------------------------------------------------------ анализ

def preprocess(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Серый + бинарная маска чернил (линии = 255)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 31, 15)
    # пыль после порога: убираем компоненты ≤2 px, не трогая тонкие линии
    n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    small = np.where(stats[:, cv2.CC_STAT_AREA] <= 2)[0]
    if len(small):
        ink[np.isin(lab, small)] = 0
    return gray, ink

def detect_lines(ink: np.ndarray) -> tuple[int, int, int, int]:
    edges = cv2.Canny(ink, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=40, maxLineGap=6)
    if lines is None:
        return 0, 0, 0, 0
    lines = lines.reshape(-1, 4)          # совместимость: (N,1,4) и (N,4)
    h = v = d = 0
    for x1, y1, x2, y2 in lines:
        ang = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180
        if ang < 5 or ang > 175:
            h += 1
        elif 85 < ang < 95:
            v += 1
        else:
            d += 1
    return len(lines), h, v, d

def detect_circles(gray: np.ndarray, ink: np.ndarray, min_cover: float = 0.85):
    """Hough + верификация: доля точек окружности, попавших в чернила (±1 px).
    Большие сканы обрабатываются в уменьшенном масштабе (радиусы возвращаются в исходных px)."""
    H0, W0 = ink.shape
    scale = 1.0
    if max(H0, W0) > 1600:
        scale = 1600 / max(H0, W0)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ink = (cv2.resize(ink, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) > 40).astype(np.uint8) * 255
    H, W = ink.shape
    c = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=15,
                         param1=120, param2=40, minRadius=5, maxRadius=min(400, int(0.2 * max(H, W))))
    if c is None:
        return []
    ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    cos, sin = np.cos(ang), np.sin(ang)
    out = []
    for x, y, r in c.reshape(-1, 3)[:400]:
        hit = np.zeros(len(ang), bool)
        for dr in ((-2, -1, 0, 1, 2) if scale < 1 else (-1, 0, 1)):
            xs = np.clip((x + (r + dr) * cos).astype(int), 0, W - 1)
            ys = np.clip((y + (r + dr) * sin).astype(int), 0, H - 1)
            hit |= ink[ys, xs] > 0
        if hit.mean() >= min_cover:
            out.append((int(x / scale), int(y / scale), int(r / scale)))
    return out

def detect_rects_and_contours(ink: np.ndarray):
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for c in contours:
        if cv2.contourArea(c) < 400:
            continue
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            rects.append(cv2.boundingRect(approx))
    return len(rects), len(contours), rects

def detect_frame_and_title(rects, W: int, H: int) -> tuple[bool, bool]:
    has_border = any(w > 0.85 * W and h > 0.85 * H for _, _, w, h in rects)
    has_title = any(x > 0.55 * W and y > 0.75 * H and w > 0.2 * W and h > 0.05 * H
                    for x, y, w, h in rects)
    return has_border, has_title

def detect_text_regions(gray: np.ndarray) -> list[TextRegion]:
    """MSER-блобы, похожие на символы → склейка в строки."""
    mser = cv2.MSER_create(delta=5, min_area=30, max_area=2000)
    regions, _ = mser.detectRegions(gray)
    boxes = []
    for r in regions:
        x, y, w, h = cv2.boundingRect(r.reshape(-1, 1, 2))
        if 0.15 < w / max(h, 1) < 3.0 and 6 <= h <= 60:
            boxes.append((x, y, w, h))
    if not boxes:
        return []
    mask = np.zeros(gray.shape, np.uint8)
    for x, y, w, h in boxes:
        cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 20 and 8 <= h <= 80:
            out.append(TextRegion(x, y, w, h))
    return out

def run_ocr(img: np.ndarray, min_conf: float, backend: str = "rapidocr",
            langs: tuple[str, ...] = OCR_LANGS) -> list[TextRegion]:
    """OCR всего листа. rapidocr — быстрый, но без кириллицы;
    easyocr — латиница с диакритикой (en/es/ca/de/fr/nl) (pip install easyocr, при первом запуске качает модели)."""
    global _EASY
    H, W = img.shape[:2]
    scale = OCR_UPSCALE if max(H, W) < 1500 else 1.0
    work = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1 else img

    raw: list[tuple[list, str, float]] = []
    if backend == "easyocr":
        try:
            if _EASY is None:
                import easyocr
                _EASY = easyocr.Reader(list(langs), gpu=True)
            raw = [(box, t, float(c)) for box, t, c in _EASY.readtext(work, paragraph=False)]
        except ImportError:
            print("  [ocr] easyocr не установлен (pip install easyocr) — использую rapidocr")
            backend = "rapidocr"
    if backend == "rapidocr":
        if not HAS_OCR:
            return []
        result, _ = _OCR(work)
        raw = [(box, t, float(c)) for box, t, c in (result or [])]

    out = []
    for box, text, conf in raw:
        conf *= 100
        text = text.strip()
        if not text or conf < min_conf:
            continue
        xs = [p[0] / scale for p in box]; ys = [p[1] / scale for p in box]
        x, y = int(min(xs)), int(min(ys))
        out.append(TextRegion(x, y, int(max(xs)) - x, int(max(ys)) - y, text, round(conf, 1)))
    out.sort(key=lambda t: (t.y // 20, t.x))
    return out

def analyze(path: Path, min_conf: float, ocr_backend: str = "rapidocr",
            scan_mode: str = "auto", img: np.ndarray | None = None) -> DrawingReport:
    if img is None:
        img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Не удалось прочитать {path}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    # --- сканы / ксерокопии
    sinfo = analyze_scan_quality(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if scan_mode == "on" or (scan_mode == "auto" and sinfo.is_scan):
        img = clean_scan(img, sinfo)
    H, W = img.shape[:2]
    gray, ink = preprocess(img)
    n, h, v, d = detect_lines(ink)
    circles = detect_circles(gray, ink)
    n_rect, n_cont, rects = detect_rects_and_contours(ink)
    border, title = detect_frame_and_title(rects, W, H)
    regions = detect_text_regions(gray)          # быстрый триггер: есть ли текст вообще
    if regions:
        ocr_regions = run_ocr(img, min_conf, ocr_backend)
        if ocr_regions:                           # RapidOCR дал точные боксы — берём их
            regions = ocr_regions
    ocr = "\n".join(t.text for t in regions if t.text)
    rep = DrawingReport(path.name, W, H, round(float((ink > 0).mean()), 4),
                        n, h, v, d, circles, n_rect, n_cont, border, title, regions, ocr,
                        scan=asdict(sinfo))
    rep.diagram = parse_diagram(ink, rects, regions, W, H)
    return rep

# ------------------------------------------------------------------ блок-схемы / диаграммы

def _shape_of(c) -> str | None:
    peri = cv2.arcLength(c, True)
    if peri < 40:
        return None
    approx = cv2.approxPolyDP(c, 0.03 * peri, True)
    x, y, w, h = cv2.boundingRect(c)
    area = cv2.contourArea(c)
    if area < 400 or w < 25 or h < 15:
        return None
    fill = area / (w * h)
    n = len(approx)
    (cx, cy), r = cv2.minEnclosingCircle(c)
    circ = area / (math.pi * r * r) if r > 0 else 0
    if n == 4 and fill > 0.85:
        return "process"                       # прямоугольник
    if n == 4 and 0.4 < fill < 0.65:
        return "decision"                      # ромб
    if circ > 0.85 and 0.8 < w / h < 1.25:
        return "circle"                        # коннектор / начало
    if n >= 6 and fill > 0.75 and w / h > 1.3:
        return "terminator"                    # скруглённый прямоугольник
    if n == 4 and 0.65 <= fill <= 0.85:
        return "parallelogram"                 # ввод-вывод
    return None

def parse_diagram(ink: np.ndarray, rects, regions: list[TextRegion], W: int, H: int) -> dict:
    """Блок-схема → узлы (фигура + текст внутри) и рёбра (линии, соединяющие узлы).
    Возвращает {} если это не похоже на диаграмму."""
    scale = 1.0
    if max(W, H) > 1600:                          # диаграммы не требуют полного разрешения
        scale = 1600 / max(W, H)
        ink = cv2.resize(ink, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ink = (ink > 127).astype(np.uint8) * 255
        regions = [TextRegion(int(t.x * scale), int(t.y * scale), max(int(t.w * scale), 1), max(int(t.h * scale), 1), t.text, t.conf) for t in regions]
        W, H = ink.shape[1], ink.shape[0]
    contours, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    nodes = []
    for c in contours:
        kind = _shape_of(c)
        if not kind:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w > 0.8 * W and h > 0.8 * H:        # рамка листа
            continue
        inside = [t for t in regions if t.text and x <= t.x + t.w / 2 <= x + w and y <= t.y + t.h / 2 <= y + h]
        if not inside:
            continue
        inside.sort(key=lambda t: (t.y, t.x))
        nodes.append({"id": f"n{len(nodes)+1}", "shape": kind, "text": " ".join(t.text for t in inside),
                      "bbox": [int(x), int(y), int(w), int(h)]})
    if len(nodes) < 3:
        return {}
    keep = []
    for n in sorted(nodes, key=lambda n: -n["bbox"][2] * n["bbox"][3]):
        x, y, w, h = n["bbox"]
        if any(abs(x - k["bbox"][0]) < 8 and abs(y - k["bbox"][1]) < 8 and n["text"] == k["text"] for k in keep):
            continue
        keep.append(n)
    nodes = keep
    # таблица/штамп, а не диаграмма: большинство блоков соприкасаются сторонами
    def touching(a, b):
        ax, ay, aw, ah = a["bbox"]; bx, by, bw, bh = b["bbox"]
        gx = max(ax - (bx + bw), bx - (ax + aw)); gy = max(ay - (by + bh), by - (ay + ah))
        return (gx <= 6 and gy < 0) or (gy <= 6 and gx < 0)
    touch = sum(any(touching(a, b) for b in nodes if b is not a) for a in nodes)
    if touch > 0.5 * len(nodes):
        return {}
    for i, n in enumerate(nodes):
        n["id"] = f"n{i+1}"

    mask = ink.copy()
    for n in nodes:
        x, y, w, h = n["bbox"]
        cv2.rectangle(mask, (x - 3, y - 3), (x + w + 3, y + h + 3), 0, -1)
    for t in regions:                                         # стираем только сами глифы, с усадкой
        cv2.rectangle(mask, (t.x + 3, t.y + 3), (t.x + t.w - 3, t.y + t.h - 3), 0, -1)
    lines = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=25, minLineLength=20, maxLineGap=25)
    edges = []
    if lines is not None:
        def inside(n, px, py, pad=4):
            x, y, w, h = n["bbox"]
            return x - pad <= px <= x + w + pad and y - pad <= py <= y + h + pad
        def nearest(px, py, dx=0.0, dy=0.0):
            """Узел у конца линии: сначала прямое попадание, затем «луч» вдоль линии
            (стрелка могла быть разорвана подписью или наконечником)."""
            for n in nodes:
                if inside(n, px, py, pad=8):
                    return n
            L = math.hypot(dx, dy)
            if L == 0:
                return None
            ux, uy = dx / L, dy / L
            for step in range(4, int(0.2 * max(W, H)), 4):
                qx, qy = px + ux * step, py + uy * step
                for n in nodes:
                    if inside(n, qx, qy):
                        return n
                # луч не должен пересекать чернила другого направления? — упрощение: просто идём
            return None
        def blob(px, py):
            r = 12
            return int(ink[max(py - r, 0):py + r, max(px - r, 0):px + r].sum() // 255)
        seen = set()
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            a = nearest(x1, y1, x1 - x2, y1 - y2)          # луч наружу от конца линии
            b = nearest(x2, y2, x2 - x1, y2 - y1)
            if a and b and a is not b:
                key = tuple(sorted((a["id"], b["id"])))
                if key in seen:
                    continue
                seen.add(key)
                src, dst = (a, b) if blob(x2, y2) > blob(x1, y1) else (b, a)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                label = ""
                for t in regions:
                    if t.text and not any(t.text in n["text"] for n in nodes):
                        if abs(t.x + t.w / 2 - mx) < 80 and abs(t.y + t.h / 2 - my) < 60:
                            label = t.text; break
                edges.append({"from": src["id"], "to": dst["id"], "label": label})
    if len(edges) < max(2, len(nodes) // 3):        # блоки без связей — не диаграмма
        return {}
    inv = 1 / scale
    for n in nodes:
        n["bbox"] = [int(v * inv) for v in n["bbox"]]
    return {"nodes": nodes, "edges": edges}

# ------------------------------------------------------------------ вывод

# ключевые слова штампа для en / es / ca / de / fr / nl
_KW = {
    "scale":    r"scale|escala|scala|ma[ßsb]+stab|échelle|echelle|schaal|schelle",
    "sheet":    r"sheet|hoja|full|blatt|feuille|blad|foglio|tavola|page|página|pagina|seite",
    "sheet_of": r"of|de|di|von|sur|van|/",
    "rev":      r"rev(?:isi\w{0,3})?\.?|índice|indice|[aä]nderung|aenderung|wijziging|version|issue",
    "mat_label": r"materiaal|materiale|matériau|materiau|mati[èe]re|mat[èe]ria|material|werkstoff",
    "holes":    r"x|×|holes?|agujeros?|taladros?|forats?|fori|foro|bohrungen|bohrung|löcher|loecher|trous?|perçages?|gaten|gat|boringen",
    "material": (r"steel|acero|acer|acciaio|stahl|acier|staal|inox|"
                 r"alumini(?:um|o)|alu|"
                 r"brass|latón|laton|llautó|ottone|messing|laiton|"
                 r"cast iron|fundición|fundicion|fosa|ghisa|gusseisen|guss|fonte|gietijzer|"
                 r"bronze|bronce|bronzo|"
                 r"plastic|plástico|plastico|plàstic|plastica|kunststoff|plastique|kunststof|"
                 r"titanium|titanio|titani|titan|titane|titaan|"
                 r"copper|cobre|coure|rame|kupfer|cuivre|koper|"
                 r"rubber|goma|caucho|gomma|gummi|caoutchouc"),
}
_RE = {
    "section":   re.compile(r"^[A-Z]\s*[-–]\s*[A-Z]$"),
    "holes":     re.compile(rf"^(\d+)\s*(?:{_KW['holes']})\.?\s*(.+)$", re.I),
    "thread":    re.compile(r"^M\s?\d+(?:x[\d.]+)?$", re.I),
    "diameter":  re.compile(r"^(?:Ø|⌀|D|ø|dia\.?|diam\.?)\s?\d+(?:[.,]\d+)?$", re.I),
    "dimension": re.compile(r"^\d+(?:[.,]\d+)?(?:\s?mm)?(?:\s?±\s?\d+(?:[.,]\d+)?|\s?[A-Za-z]{1,2}\d{1,2})?$"),
    "scale":     re.compile(rf"(?:{_KW['scale']})\s*:?\s*(\d+\s*[:]?\s*\d+)(?!\d)", re.I),
    "sheet":     re.compile(rf"(?:{_KW['sheet']})\s*:?\s*(\d+)\s*(?:{_KW['sheet_of']})\s*(\d+)", re.I),
    "rev":       re.compile(rf"\b(?:{_KW['rev']})\b\s*:?\s*([A-Z0-9]{{1,4}})\b", re.I),
    "material":  re.compile(rf"\b({_KW['material']})\b[\s:\-]*([A-Za-z0-9][A-Za-z0-9./\-]*)?", re.I),
    "partno":    re.compile(r"\b([A-Z]{2,4}[-_]?\d{2,}[A-Z0-9-]*|\d{3,}[-.]\d{2,}[-.\dA-Z]*)\b"),
    "mat_label": re.compile(rf"\b(?:{_KW['mat_label']})\s*(?::\s*|\s+(?=[A-Z0-9]))(.+?)(?=\s*(?:{_KW['scale']}|{_KW['sheet']}|{_KW['rev']})\b|$)", re.I),
}
_OCR_FIX = [(re.compile(r"(?<![\w.])[0O](?=\d)"), "Ø")]      # «08», «O12» → «Ø8», «Ø12» (после кол-ва отверстий и т.п.)

def _fix_ocr(s: str) -> str:
    for rx, rep in _OCR_FIX:
        s = rx.sub(rep, s)
    return s
_TITLE_JUNK = ("sheet", "scale", "rev", "drawn", "checked", "date", "material", "title", "size",
               "hoja", "escala", "dibujado", "comprobado", "fecha", "material", "título", "titulo",
               "full", "dibuixat", "comprovat", "data", "títol",
               "blatt", "maßstab", "gezeichnet", "geprüft", "datum", "werkstoff", "benennung",
               "feuille", "échelle", "echelle", "dessiné", "dessine", "vérifié", "verifie", "matière", "matiere",
               "blad", "schaal", "getekend", "gecontroleerd", "materiaal", "benaming",
               "foglio", "tavola", "scala", "disegnato", "controllato", "verificato", "data", "materiale", "titolo", "denominazione")

_LANG_HINTS = {
    "es": ("hoja", "escala", "acero", "agujeros", "dibujado", "comprobado", "pieza", "plano", "número", "fecha", "título"),
    "ca": ("full", "acer", "forats", "dibuixat", "comprovat", "peça", "plànol", "núm", "títol", "revisió"),
    "de": ("blatt", "maßstab", "masstab", "stahl", "bohrung", "gezeichnet", "geprüft", "teil", "zeichnung", "werkstoff", "benennung", "datum"),
    "fr": ("feuille", "échelle", "echelle", "acier", "trous", "dessiné", "vérifié", "pièce", "plan n", "matière", "indice", "désignation"),
    "nl": ("blad", "schaal", "staal", "gaten", "getekend", "gecontroleerd", "onderdeel", "tekening", "materiaal", "benaming", "revisie"),
    "en": ("sheet", "scale", "steel", "holes", "drawn", "checked", "approved", "part", "drawing", "material", "title", "date", "rev"),
    "it": ("foglio", "tavola", "scala", "acciaio", "fori", "disegnato", "controllato", "approvato", "pezzo", "disegno", "materiale", "titolo", "denominazione", "revisione"),
}

def detect_language(text: str) -> str:
    t = " " + text.lower() + " "
    scores = {lang: sum(t.count(k) for k in keys) for lang, keys in _LANG_HINTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ("none" if not text.strip() else "unknown")

# метки полей штампа (в любом из 6 языков) → каноническое имя поля
_FIELD_LABELS = {
    "title":   r"(?:draw(?:i|n)?n?g\s*)?title|t[ií]tulo|titolo|denominazione|t[ií]tol|benennung|bezeichnung|d[ée]signation|titre|benaming|omschrijving|drawing title|nombre|nom",
    "partno":  r"draw(?:i|n)?n?g\s*(?:number|no\.?|n[°º]\.?)|dwg\.?\s*no\.?|part\s*(?:number|no\.?)|n[úu]m(?:ero)?\.?\s*(?:de\s*)?pl[aà]no|n[úu]m\.?\s*pl[àa]nol|zeichnungs?-?\s*(?:nummer|nr\.?)|teile-?nr\.?|n[°º]\s*(?:de\s*)?plan|r[ée]f[ée]rence|tekening(?:s)?-?\s*(?:nummer|nr\.?)|artikel-?nr\.?|n(?:umero|\.|°)?\s*disegno|codice(?:\s*disegno)?",
    "cad_no":  r"cad\s*(?:no\.?|number)|cad-?nr\.?|fichier|bestand|archivo|fitxer|datei",
    "material": r"material|materiaal|materiale|mat[ée]riau|mati[èe]re|mat[èe]ria|werkstoff",
    "scale":   r"scale|escala|scala|ma[ßsb]+stab|[ée]chelle|schaal",
    "sheet":   r"sheet|page|hoja|p[aá]gina|full|blatt|seite|feuille|blad|foglio|tavola",
    "rev":     r"rev(?:isi\w{0,3})?\.?|issue|[aä]nderung|indice|[íi]ndice|wijziging",
    "drawn":   r"drawn(?:\s*by)?|dibujado|dibuixat|disegnato|gezeichnet|dessin[ée]|getekend",
    "checked": r"checked(?:\s*by)?|comprobado|comprovat|controllato|verificato|gepr[üu]ft|v[ée]rifi[ée]|gecontroleerd",
    "approved":r"approved(?:\s*by)?|aprobado|aprovat|approvato|genehmigt|freigabe|approuv[ée]|goedgekeurd",
    "contractor": r"contractor|company|empresa|firma|azienda|societ[àa]|soci[ée]t[ée]|bedrijf|client|cliente|kunde|committente",
    "date":    r"date|fecha|data|datum",
    "unit":    r"unit|unidad|unitat|unit[àa]|einheit|unit[ée]|eenheid",
    "status":  r"status|estado|estat|stato|zustand|[ée]tat|toestand",
    "lang":    r"lang(?:uage)?|idioma|lingua|sprache|langue|taal",
    "project": r"project(?:\s*no\.?)?|proyecto|projecte|progetto|projekt|projet",
}
_FIELD_RE = {k: re.compile(rf"^\s*(?:{v})\s*:?\s*$", re.I) for k, v in _FIELD_LABELS.items()}
_ANY_LABEL = "|".join(_FIELD_LABELS.values())
_FIELD_INLINE_RE = {k: re.compile(rf"^\s*(?:{v})\s*:\s*(.+?)(?=\s+(?:{_ANY_LABEL})\b|$)", re.I)
                    for k, v in _FIELD_LABELS.items()}

def extract_title_block_fields(regions: list[TextRegion], W: int, H: int) -> dict:
    """Разбор табличного штампа: метка в одной ячейке, значение под ней (или справа);
    значение, разбитое по клеткам (SU | BOL | E | 01 ...), склеивается по строке."""
    fields: dict[str, str] = {}
    regs = [t for t in regions if t.text]
    labels = []
    for t in regs:
        for k, rx in _FIELD_RE.items():
            if rx.match(t.text):
                labels.append((k, t)); break
        else:
            for k, rx in _FIELD_INLINE_RE.items():          # «Material: S235JR» в одной строке
                if (m := rx.match(t.text)) and k not in fields:
                    fields[k] = m.group(1).strip(); break
    label_boxes = [t for _, t in labels]
    for k, lab in labels:
        if k in fields:
            continue
        if k in ("rev", "date", "drawn") and ":" not in lab.text:
            continue                                   # REV / DATE / BY — шапка таблицы изменений
        h = max(lab.h, 8)
        # граница справа — ближайшая другая метка в соседней колонке
        right_labels = [l.x for l in label_boxes if l is not lab and l.x > lab.x + 0.5 * h and abs(l.y - lab.y) < 3.5 * h]
        x_limit = min(right_labels) - 0.3 * h if right_labels else lab.x + 30 * h
        # кандидаты: строка под меткой (в пределах 3 высот), начинающаяся не левее метки - 0.5h
        below = [t for t in regs if t is not lab and t not in label_boxes
                 and lab.y + 0.5 * h < t.y <= lab.y + 4.5 * h
                 and lab.x - 0.5 * h <= t.x < min(x_limit, lab.x + 4 * h)]   # значение начинается под меткой
        # или справа на той же строке
        right = [t for t in regs if t is not lab and t not in label_boxes
                 and abs(t.y - lab.y) < 0.6 * h and 0 < t.x - (lab.x + lab.w) < 4 * h]
        diag = [t for t in regs if t is not lab and t not in label_boxes
                and 0.3 * h < t.y - lab.y <= 2.5 * h and lab.x + 0.5 * h <= t.x < min(x_limit, lab.x + 10 * h)]
        cand = (min(below, key=lambda t: (t.y, t.x)) if below else
                min(right, key=lambda t: t.x) if right else
                min(diag, key=lambda t: (t.y, t.x)) if diag else None)
        if cand is None:
            continue
        # склейка ячеек той же строки, правее найденного значения, до следующей метки
        row = sorted([t for t in regs if t not in label_boxes and abs(t.y - cand.y) < 0.6 * max(cand.h, 8)
                      and t.x >= cand.x - 2 and t.x < x_limit], key=lambda t: t.x)
        joined, prev_end = [], None
        for t in row:                                     # рвём склейку на большом пробеле (другая область)
            if prev_end is not None and t.x - prev_end > 5 * h:
                break
            joined.append(t.text); prev_end = t.x + t.w
        val = " ".join(joined)
        if val:
            fields[k] = val.strip()
    return fields

def _looks_like_title(s: str, conf: float) -> bool:
    """Заголовок: ≥2 букв подряд, ≥4 символов, не служебное слово штампа, conf ≥ 60."""
    if conf < 60 or len(s) < 4 or not re.search(r"[A-Za-zÀ-ÿ]{2,}", s):
        return False
    return not any(s.lower().startswith(j) for j in _TITLE_JUNK)

def interpret_text(regions: list[TextRegion], W: int, H: int) -> dict:
    """Heuristic classification of OCR strings into drawing semantics."""
    info = {"dimensions": [], "holes": [], "sections": [], "notes": [],
            "title": None, "material": None, "scale": None, "sheet": None, "rev": None,
            "partno": None, "fields": {}}
    fields = extract_title_block_fields(regions, W, H)
    info["fields"] = fields
    if fields.get("title"):    info["title"] = fields["title"]
    if fields.get("partno"):   info["partno"] = fields["partno"]
    if fields.get("material"): info["material"] = fields["material"]
    if fields.get("scale") and (m := re.search(r"\d+\s*:\s*\d+", fields["scale"])): info["scale"] = m.group(0).replace(" ", "")
    def _norm_scale(v: str) -> str:
        v = v.replace(" ", "")
        return v if ":" in v else (f"{v[0]}:{v[1:]}" if len(v) >= 2 else v)   # «12» без двоеточия → 1:2
    if fields.get("sheet") and (m := re.search(r"(\d+)\s*(?:of|de|von|sur|van|/)\s*(\d+)", fields["sheet"], re.I)): info["sheet"] = f"{m.group(1)} of {m.group(2)}"
    if fields.get("rev") and (m := re.match(r"[A-Z0-9]{1,4}$", fields["rev"].strip(), re.I)): info["rev"] = fields["rev"].strip()
    consumed = set()
    for t in regions:
        s = t.text.strip()
        if not s:
            continue
        in_title_block = t.x > 0.55 * W and t.y > 0.75 * H
        if any(rx.match(s) for rx in _FIELD_RE.values()) or any(s in v for v in fields.values()):
            continue                                     # метки штампа и уже разобранные значения
        if _RE["section"].match(s):
            info["sections"].append(s.replace(" ", "")); continue
        if (m := _RE["holes"].match(s)) and int(m.group(1)) > 0:
            spec = _fix_ocr(m.group(2).strip())
            spec = re.sub(r"(?i)^((?:bohrung|agujeros?|trous?|gaten|fori|forats?|holes?)\s*)0(\d)", r"\1Ø\2", spec)
            # спецификация отверстия: Ø8 / M10 / D12 / 8 mm / Bohrung Ø8 — иначе это не callout
            if re.search(r"(?:^|\s|[a-z])(?:Ø|⌀|M|D)\s?\d|\d+(?:[.,]\d+)?\s?mm\b", spec):
                info["holes"].append(f"{m.group(1)} × {spec}"); continue
            info["notes"].append(s); continue
        if _RE["thread"].match(s) or _RE["diameter"].match(s) or _RE["dimension"].match(s):
            if re.match(r"^0\d", s):                      # «080», «040 H7» → «Ø80», «Ø40 H7» (Ø прочитан как ноль)
                s = "Ø" + s[1:]
            if s not in info["dimensions"]:
                info["dimensions"].append(s)
            continue

        handled = False
        if (m := _RE["scale"].search(s)) and not info["scale"]:
            info["scale"] = _norm_scale(m.group(1)); handled = True
        if (m := _RE["sheet"].search(s)) and not info["sheet"]:
            info["sheet"] = f"{m.group(1)} of {m.group(2)}"; handled = True
        if (m := _RE["rev"].search(s)) and not info["rev"]:
            info["rev"] = m.group(1); handled = True
        if not info["material"]:
            if m := _RE["mat_label"].search(s):
                info["material"] = m.group(1).strip(" :-"); handled = True
            elif m := _RE["material"].search(s):
                mat = re.split(rf"\b(?:{_KW['scale']}|{_KW['sheet']}|{_KW['rev']})\b", s[m.start():], flags=re.I)[0]
                info["material"] = mat.strip(" :-"); handled = True
        if (m := _RE["partno"].search(s)) and not fields.get("partno"):
            if info["partno"] is None:
                info["partno"] = m.group(1)
            if info["title"] is None and _looks_like_title(s, t.conf):
                info["title"] = s
            handled = True
        if not handled:
            if in_title_block and info["title"] is None and _looks_like_title(s, t.conf):
                info["title"] = s
            else:
                info["notes"].append(s)
    return info

def describe(r: DrawingReport) -> str:
    info = interpret_text(r.text_regions, r.width, r.height)
    diagram_title(r, info)
    out = [f"# Drawing `{r.file}`", ""]

    # --- identity
    ident = []
    if info["title"]:
        ident.append(f"The drawing is titled **{info['title']}**")
    elif info["partno"]:
        ident.append(f"The part number appears to be **{info['partno']}**")
    else:
        ident.append("No title block text was recognized")
    tail = []
    if info["material"]: tail.append(f"material {info['material']}")
    if info["scale"]:    tail.append(f"scale {info['scale']}")
    if info["sheet"]:    tail.append(f"sheet {info['sheet']}")
    if info["rev"]:      tail.append(f"revision {info['rev']}")
    if tail:
        ident.append("; " + ", ".join(tail))
    out.append("".join(ident) + ".")
    extra = {k: v for k, v in info["fields"].items() if k in ("drawn", "checked", "approved", "contractor", "project", "cad_no", "date", "status", "unit")}
    if extra:
        out.append("Title block also lists " + ", ".join(f"{k}: {v}" for k, v in extra.items()) + ".")

    # --- sheet layout
    layout = []
    layout.append("has a drawing frame" if r.has_border else "has no drawing frame")
    layout.append("a title block in the lower-right corner" if r.has_title_block
                  else "no detectable title block")
    out.append(f"The sheet ({r.width}×{r.height} px, {r.ink_ratio * 100:.1f}% ink) "
               f"{layout[0]} and {layout[1]}.")

    # --- geometry
    geo = []
    if r.n_horizontal + r.n_vertical > 3 * max(r.n_diagonal, 1):
        geo.append(f"Geometry is mostly orthogonal ({r.n_horizontal} horizontal, "
                   f"{r.n_vertical} vertical lines), typical of orthographic projections")
    else:
        geo.append(f"There is a notable share of inclined lines ({r.n_diagonal}), "
                   "suggesting hatching in a section view, chamfers or an axonometric view")
    if r.circles:
        radii = sorted({c[2] for c in r.circles})
        geo.append(f"{len(r.circles)} circular features were found (radii ≈ "
                   f"{', '.join(map(str, radii))} px) — likely holes, a flange or a shaft cross-section")
    else:
        geo.append("no circular features were found")
    out.append("; ".join(geo) + ".")

    # --- sections
    if info["sections"]:
        out.append(f"Section view(s) labelled {', '.join(info['sections'])} are present.")

    # --- callouts
    if info["holes"]:
        out.append("Hole/fastener callouts: " + "; ".join(info["holes"]) + ".")
    if info["dimensions"]:
        out.append("Dimensions and sizes read from the drawing: "
                   + ", ".join(info["dimensions"]) + ".")
    if info["notes"]:
        out.append("Other annotations: " + "; ".join(f"“{n}”" for n in info["notes"]) + ".")

    # --- raw OCR appendix
    if r.diagram.get("nodes"):
        out += ["", f"## Diagram graph ({len(r.diagram['nodes'])} nodes, {len(r.diagram['edges'])} edges)"]
        by_id = {n["id"]: n for n in r.diagram["nodes"]}
        out += [f"- {n['id']} [{n['shape']}] {n['text']}" for n in r.diagram["nodes"]]
        out += [f"- {e['from']} → {e['to']}" + (f"  ({e['label']})" if e["label"] else "") for e in r.diagram["edges"]]
    if r.scan.get("is_scan"):
        sc = r.scan
        out += ["", f"Scan detected: skew {sc['skew_deg']:+.2f}°, noise {sc['noise']:.3f}, background {sc['background']}, "
                    f"contrast {sc['contrast']:.2f}; cleanup: {', '.join(sc['applied']) or 'none'}."]
    if r.text_regions and any(t.text for t in r.text_regions):
        out += ["", "## Recognized text (raw OCR)"]
        out += [f"- ({t.x},{t.y}) “{t.text}” [conf {t.conf}]" for t in r.text_regions if t.text]
    elif r.text_regions:
        out += ["", "Text-like regions were detected but OCR produced nothing."]
    else:
        out += ["", "No text detected — OCR was skipped."]
    return "\n".join(out)

# ------------------------------------------------------------------ теги и RAG-описание

_KINDS = {
    "bracket":  ("bracket", "soporte", "escuadra", "suport", "staffa", "supporto", "halter", "konsole", "winkel", "support", "équerre", "equerre", "beugel", "steun"),
    "flange":   ("flange", "brida", "flangia", "flansch", "bride", "flens"),
    "shaft":    ("shaft", "eje", "árbol", "arbol", "eix", "albero", "welle", "achse", "arbre", "axe", "as", "spil"),
    "plate":    ("plate", "placa", "chapa", "piastra", "lamiera", "platte", "blech", "plaque", "tôle", "tole", "plaat"),
    "housing":  ("housing", "casing", "carcasa", "caja", "carcassa", "alloggiamento", "scatola", "gehäuse", "gehause", "carter", "boîtier", "boitier", "behuizing", "huis"),
    "cover":    ("cover", "lid", "tapa", "cubierta", "coperchio", "deckel", "abdeckung", "couvercle", "capot", "deksel", "afdekking"),
    "gear":     ("gear", "engranaje", "rueda dentada", "engranatge", "ingranaggio", "ruota dentata", "zahnrad", "engrenage", "pignon", "tandwiel"),
    "bushing":  ("bushing", "sleeve", "casquillo", "manguito", "boccola", "bussola", "buchse", "hülse", "hulse", "bague", "douille", "bus", "huls"),
    "pin":      ("pin", "pasador", "espiga", "passador", "perno", "spina", "stift", "bolzen", "goupille", "axe", "pen", "stift"),
    "bolt":     ("bolt", "screw", "tornillo", "cargol", "vite", "bullone", "schraube", "bolzen", "vis", "boulon", "bout", "schroef"),
    "nut":      ("nut", "tuerca", "femella", "dado", "mutter", "écrou", "ecrou", "moer"),
    "washer":   ("washer", "arandela", "volandera", "rondella", "scheibe", "rondelle", "ring", "sluitring"),
    "spring":   ("spring", "muelle", "resorte", "molla", "feder", "ressort", "veer"),
    "bearing":  ("bearing", "rodamiento", "cojinete", "coixinet", "cuscinetto", "lager", "roulement", "palier"),
    "pulley":   ("pulley", "polea", "politja", "puleggia", "riemenscheibe", "poulie", "riemschijf"),
    "lever":    ("lever", "arm", "palanca", "brazo", "leva", "braccio", "hebel", "arm", "levier", "bras", "hendel", "arm"),
    "frame":    ("frame", "chassis", "bastidor", "marco", "bastiment", "telaio", "rahmen", "gestell", "châssis", "cadre", "raam"),
    "beam":     ("beam", "viga", "biga", "trave", "träger", "trager", "balken", "poutre", "balk", "ligger"),
    "valve":    ("valve", "válvula", "valvula", "vàlvula", "valvola", "ventil", "vanne", "soupape", "klep", "afsluiter"),
    "pipe":     ("pipe", "tube", "tubo", "tubería", "tuberia", "canonada", "tubazione", "rohr", "tuyau", "buis", "pijp", "leiding"),
    "fitting":  ("fitting", "racor", "codo", "colze", "raccordo", "gomito", "verschraubung", "raccord", "coude", "koppeling"),
    "assembly": ("assembly", "assy", "conjunto", "montaje", "ensamblaje", "conjunt", "muntatge", "assieme", "gruppo", "complessivo", "baugruppe", "zusammenbau", "ensemble", "assemblage", "samenstel", "samenstelling"),
    "pcb":      ("pcb", "circuit board", "placa de circuito", "circuito stampato", "leiterplatte", "platine", "circuit imprimé", "printplaat"),
    "schematic":("schematic", "wiring", "esquema", "schema elettrico", "schaltplan", "schéma", "schema"),
    "floor plan":("floor plan", "planta", "pianta", "grundriss", "plan d'étage", "plattegrond"),
}
_MATERIAL_CLASS = {
    "steel": ("steel", "acero", "acer", "acciaio", "stahl", "acier", "staal", "inox", "s235", "s355", "c45", "42crmo", "1.4301", "1.4404", "aisi", "ss3"),
    "aluminium": ("alumin", "alu", "en aw", "6061", "6082", "7075", "almg"),
    "brass": ("brass", "latón", "laton", "llautó", "ottone", "messing", "laiton", "cuzn"),
    "cast_iron": ("cast iron", "fundición", "fundicion", "fosa", "ghisa", "gusseisen", "gg", "gjl", "gjs", "fonte", "gietijzer", "en-gj"),
    "bronze": ("bronze", "bronce", "bronzo", "cusn"),
    "plastic": ("plastic", "plástico", "plastico", "plàstic", "plastica", "kunststoff", "plastique", "kunststof", "pa6", "pom", "ptfe", "pe", "pp", "abs", "peek"),
    "titanium": ("titan", "titanio", "titani", "titane", "titaan", "ti6al4v"),
    "copper": ("copper", "cobre", "coure", "rame", "kupfer", "cuivre", "koper"),
    "rubber": ("rubber", "goma", "caucho", "gomma", "gummi", "caoutchouc", "nbr", "epdm"),
}
def classify_drawing(r: DrawingReport, info: dict) -> dict:
    """Derive categorical tags from geometry + interpreted text."""
    title = (info["title"] or "").lower()
    all_text = " ".join(t.text for t in r.text_regions if t.text).lower()

    kind = next((k for k, keys in _KINDS.items() if any(w in title for w in keys)), None)
    if kind is None:
        if re.search(r"\bm[²2]\b|floor plan|planta baja|grundriss|plattegrond|plan d'étage|sal[oó]n|cocina|dormitorio|ba[ñn]o|"
                     r"wohnzimmer|k[üu]che|schlafzimmer|cuisine|chambre|keuken|slaapkamer|menjador|cuina|habitaci[óo]|"
                     r"pianta|soggiorno|cucina|camera|bagno", all_text):
            kind = "floor plan"
        elif re.search(r"schaltplan|schematic|wiring|circuit|esquema el[ée]ctric|schema elettrico|sch[ée]ma [ée]lectrique|schakelschema|"
                       r"netzteil|\b\d+\s?v(?:ac|dc)?\b|\br\d+\b", all_text):
            kind = "schematic"

    # drawing type: assembly / detail part / schematic
    n_partnos = len(set(_RE["partno"].findall(" ".join(t.text for t in r.text_regions))))
    if r.diagram.get("nodes"):
        shapes = {n["shape"] for n in r.diagram["nodes"]}
        kind = "flowchart" if "decision" in shapes or "terminator" in shapes else "block diagram"
    if kind == "assembly" or any(w in all_text for w in
                                 ("assembly", "conjunto", "conjunt", "assieme", "complessivo", "distinta", "baugruppe", "stückliste", "ensemble",
                                  "samenstel", "parts list", "lista de piezas", "bill of material")):
        dtype = "assembly"
    elif kind == "floor plan":
        dtype = "layout"
    elif kind in ("flowchart", "block diagram"):
        dtype = "diagram"
    elif kind in ("pcb", "schematic") or (not r.circles and r.n_lines < 10):
        dtype = "schematic"
    elif n_partnos > 5:
        dtype = "assembly"
    else:
        dtype = "part"

    # view types
    views = []
    if info["sections"]:
        views.append("section")
    if r.n_horizontal + r.n_vertical > 3 * max(r.n_diagonal, 1):
        views.append("orthographic")
    else:
        views.append("hatched_or_axonometric")
    if len(r.circles) >= 3:
        views.append("round_features")

    # features
    features = []
    if r.circles:      features.append("holes")
    if info["holes"]:  features.append("hole_pattern")
    if any(re.match(r"^M\s?\d", d, re.I) for d in info["dimensions"]) or \
       any("m" in h.lower() for h in info["holes"]):
        features.append("threads")
    if any(re.match(r"^(?:Ø|D|Ф|⌀)", d, re.I) for d in info["dimensions"]):
        features.append("diameters")
    if info["dimensions"]:  features.append("dimensioned")
    if r.n_diagonal > 5:    features.append("hatching")

    material_class = None
    if info["material"]:
        m = info["material"].lower()
        material_class = next((cls for cls, keys in _MATERIAL_CLASS.items()
                               if any(k in m for k in keys)), "other")

    complexity = "low" if r.n_contours < 40 else "medium" if r.n_contours < 150 else "high"
    lang = detect_language(all_text)

    tags = {
        "drawing_type": dtype,
        "part_kind": kind,
        "views": views,
        "features": features,
        "material_class": material_class,
        "complexity": complexity,
        "orientation": "landscape" if r.width >= r.height else "portrait",
        "has_frame": r.has_border,
        "has_title_block": r.has_title_block,
        "text_language": lang,
        "has_text": bool(all_text),
    }
    return tags

def narrative(r: DrawingReport, info: dict, tags: dict) -> str:
    """Coherent prose description for embedding (one or two paragraphs)."""
    kind = tags["part_kind"]
    dtype = tags["drawing_type"]
    subj = {"assembly": "an assembly drawing", "schematic": "a schematic", "layout": "a layout / floor plan",
            "diagram": f"a {kind or 'diagram'}", "part": "a detail (part) drawing"}[dtype]
    if kind and kind not in ("assembly", "schematic", "pcb", "floor plan", "flowchart", "block diagram"):
        subj += f" of a {kind}"

    p1 = [f"This is {subj}"]
    if info["title"]:
        p1[0] += f' titled "{info["title"]}"'
    if info["partno"]:
        p1[0] += f" with designation {info['partno']}"
    p1[0] += "."
    props = []
    if info["material"]: props.append(f"the material is {info['material']}")
    if info["scale"]:    props.append(f"the drawing scale is {info['scale']}")
    if info["sheet"]:    props.append(f"it is sheet {info['sheet']}")
    if info["rev"]:      props.append(f"revision {info['rev']}")
    for k, label in (("contractor", "the contractor/company is"), ("project", "the project is"),
                     ("drawn", "drawn by"), ("checked", "checked by"), ("approved", "approved by"),
                     ("cad_no", "CAD file"), ("date", "dated"), ("status", "status"), ("unit", "units in")):
        if info["fields"].get(k):
            props.append(f"{label} {info['fields'][k]}")
    if props:
        p1.append("According to the title block, " + ", ".join(props) + ".")
    layout = ("The sheet is framed and carries a standard title block in the lower-right corner."
              if r.has_border and r.has_title_block else
              "The sheet has a drawing frame but no recognizable title block." if r.has_border else
              "The sheet has no frame or title block, which suggests a sketch or an excerpt.")
    p1.append(layout)

    p2 = []
    if "orthographic" in tags["views"]:
        p2.append("The geometry is dominated by horizontal and vertical lines, i.e. standard "
                  "orthographic projections")
    else:
        p2.append("The geometry contains many inclined lines, indicating hatched sections, "
                  "chamfers or an axonometric view")
    if info["sections"]:
        p2[-1] += f", and a section view {', '.join(info['sections'])} is shown"
    p2[-1] += "."
    if r.circles:
        radii = sorted({c[2] for c in r.circles})
        p2.append(f"There are {len(r.circles)} circular features with radii of roughly "
                  f"{', '.join(map(str, radii))} px, most likely holes, bores or a round outline.")
    if info["holes"]:
        p2.append("The hole pattern is called out as " + "; ".join(info["holes"]) + ".")
    if info["dimensions"]:
        p2.append("Explicit dimensions on the drawing include " + ", ".join(info["dimensions"]) + ".")
    if info["notes"]:
        p2.append("Additional annotations read: " + "; ".join(f'"{n}"' for n in info["notes"]) + ".")
    if not r.text_regions:
        p2.append("No text was detected on the sheet.")
    p2.append(f"Overall complexity is {tags['complexity']} ({r.n_contours} contours, "
              f"{r.n_lines} straight segments).")

    p3 = []
    if r.diagram.get("nodes"):
        nodes, edges = r.diagram["nodes"], r.diagram["edges"]
        by_id = {n["id"]: n for n in nodes}
        p3.append(f"The diagram contains {len(nodes)} blocks: " +
                  "; ".join(f'{n["text"]} ({n["shape"]})' for n in nodes) + ".")
        if edges:
            p3.append("Connections: " + "; ".join(
                f'{by_id[e["from"]]["text"]} → {by_id[e["to"]]["text"]}' + (f' [{e["label"]}]' if e["label"] else "")
                for e in edges) + ".")
    if r.scan.get("is_scan"):
        p3.append("Source is a scan/photocopy (" + ", ".join(r.scan.get("applied") or ["no cleanup"]) + ").")
    return " ".join(p1) + "\n\n" + " ".join(p2) + ("\n\n" + " ".join(p3) if p3 else "")

def diagram_title(r: DrawingReport, info: dict) -> None:
    """Для схем заголовок — верхняя строка листа из ≥2 слов, а не строка с похожим на номер токеном."""
    if not r.diagram.get("nodes"):
        return
    node_texts = {n["text"] for n in r.diagram["nodes"]}
    cands = [t for t in r.text_regions if t.text and (t.y < 0.15 * r.height or t.y > 0.85 * r.height)
             and len(t.text.split()) >= 2 and t.text not in node_texts
             and not any(rx.match(t.text) for rx in _FIELD_RE.values())]
    if cands:
        top = min(cands, key=lambda t: t.y if t.y < 0.15 * r.height else t.y - r.height)   # верх приоритетнее низа
        row = sorted([t for t in cands if abs(t.y - top.y) < 0.8 * max(top.h, 8)], key=lambda t: t.x)
        text = " ".join(t.text for t in row)
        text = re.sub(r"^(?:flowchart|diagram|diagrama|schema|schaltplan|blockschaltbild|sch[ée]ma)\s*:\s*", "", text, flags=re.I)
        info["title"] = re.split(rf"\s+(?:{_KW['sheet']}|{_KW['rev']}|{_KW['scale']})\b", text, flags=re.I)[0].strip()

def rag_document(r: DrawingReport, vlm: dict | None = None, clip: dict | None = None) -> dict:
    """Retrieval-ready record: tags + coherent narrative + raw OCR + filterable metadata."""
    info = interpret_text(r.text_regions, r.width, r.height)
    diagram_title(r, info)
    tags = classify_drawing(r, info)
    story = narrative(r, info, tags)
    ocr_tokens = [t.text for t in r.text_regions if t.text]

    # flat tag list for hybrid / keyword search
    tag_list = [f"type:{tags['drawing_type']}", f"complexity:{tags['complexity']}",
                f"orientation:{tags['orientation']}", f"lang:{tags['text_language']}"]
    if tags["part_kind"]:      tag_list.append(f"kind:{tags['part_kind']}")
    if tags["material_class"]: tag_list.append(f"material:{tags['material_class']}")
    tag_list += [f"view:{v}" for v in tags["views"]]
    tag_list += [f"feature:{f}" for f in tags["features"]]
    if tags["has_frame"]:       tag_list.append("frame")
    if tags["has_title_block"]: tag_list.append("title_block")
    if info["partno"]:          tag_list.append(f"partno:{info['partno']}")

    # --- CLIP zero-shot: домен и тип детали (грубо, но независимо от OCR)
    if clip:
        dom, pd = clip["domain"][0]
        kind_c, pk = clip["part_kind"][0]
        tag_list.append(f"domain:{dom.split(' /')[0].replace(' ', '_')}")
        if pk >= 0.25:
            tag_list.append(f"kind:{kind_c}")
        story += (f"\n\nVisually (CLIP zero-shot) the sheet looks like a {dom} ({pd:.0%}); "
                  f"the depicted object most resembles a {kind_c} ({pk:.0%}), "
                  f"alternatives: " + ", ".join(f"{k} ({p:.0%})" for k, p in clip["part_kind"][1:]) + ".")

    # --- merge VLM output (authoritative when present) with heuristics
    if vlm:
        if vlm.get("tags"):
            tag_list += [t for t in vlm["tags"] if isinstance(t, str)]
        if vlm.get("drawing_type"): tag_list.append(f"type:{vlm['drawing_type']}")
        if vlm.get("part_kind"):    tag_list.append(f"kind:{vlm['part_kind']}")
        tag_list += [f"view:{v}" for v in vlm.get("views", []) if isinstance(v, str)]
        tag_list += [f"feature:{f}" for f in vlm.get("features", []) if isinstance(f, str)]
        tag_list = list(dict.fromkeys(tag_list))           # dedupe, keep order
        story = (vlm.get("summary") or story) + "\n\n[Automatic geometric analysis] " + story
        if vlm.get("text_on_drawing"):
            ocr_tokens = [t for t in vlm["text_on_drawing"] if isinstance(t, str)] or ocr_tokens
        if vlm.get("dimensions"):
            info["dimensions"] = list(dict.fromkeys(info["dimensions"] + vlm["dimensions"]))
        if vlm.get("material") and not info["material"]:
            info["material"] = vlm["material"]

    # embedding text: tags header + narrative + raw text (exact-match anchors)
    text = "[" + ", ".join(tag_list) + "]\n\n" + story
    if vlm and vlm.get("identifiers"):
        text += "\n\nIdentifiers: " + " | ".join(map(str, vlm["identifiers"])) + "."
    if ocr_tokens:
        text += "\n\nText on drawing: " + " | ".join(ocr_tokens) + "."

    keywords = set(ocr_tokens)
    keywords.update(n["text"] for n in r.diagram.get("nodes", []))
    for tok in ocr_tokens:
        keywords.update(w for w in re.split(r"[\s,;|]+", tok) if len(w) > 1)
    keywords.update(info["dimensions"]); keywords.update(info["sections"])
    for h in info["holes"]: keywords.update(h.replace("×", " ").split())

    meta = {
        "source": r.file, "title": info["title"], "part_number": info["partno"],
        "material": info["material"], "scale": info["scale"], "sheet": info["sheet"],
        "revision": info["rev"], "sections": info["sections"], "holes": info["holes"],
        "dimensions": info["dimensions"], "n_circles": len(r.circles),
        "title_block_fields": info["fields"],
        "is_scan": bool(r.scan.get("is_scan")), "scan_cleanup": r.scan.get("applied", []),
        "diagram_nodes": [n["text"] for n in r.diagram.get("nodes", [])],
        "diagram_edges": [[e["from"], e["to"], e["label"]] for e in r.diagram.get("edges", [])],
        "width_px": r.width, "height_px": r.height,
        "ocr_text": ocr_tokens, "keywords": sorted(keywords),
    }
    meta.update(tags)
    if clip:
        meta.update({"clip_domain": clip["domain"][0][0], "clip_domain_p": round(clip["domain"][0][1], 3),
                     "clip_part_kind": clip["part_kind"][0][0], "clip_part_kind_p": round(clip["part_kind"][0][1], 3)})
    if vlm:
        meta.update({"vlm_backend": vlm.get("_backend"), "vlm_confidence": vlm.get("confidence"),
                     "vlm_drawing_type": vlm.get("drawing_type"), "vlm_part_kind": vlm.get("part_kind"),
                     "vlm_views": vlm.get("views"), "vlm_features": vlm.get("features"),
                     "vlm_identifiers": vlm.get("identifiers")})
    return {"id": Path(r.file).stem if not r.file.endswith(".pdf") else r.file[:-4],
            "tags": tag_list, "text": text, "metadata": meta}

# ------------------------------------------------------------------ VLM-описание

VLM_PROMPT = """You are a mechanical-engineering drawing analyst. Examine the attached drawing image.
The text on the drawing may be in English, Spanish, Catalan, German, French, Dutch or Italian.
Write the summary in ENGLISH, but copy identifiers, part numbers, material grades and standards exactly as written.
Automatic pre-analysis (may contain OCR errors, treat as hints, not ground truth):
{hints}

Return ONLY a JSON object with these fields:
{{
  "summary": "3-6 sentence coherent description: what the part/assembly is, its overall shape, views shown, key features (holes, threads, chamfers, fillets, slots, keyways...), materials and finishes, and what the title block says. Write for a search index: be specific, mention all identifiers and numbers you can read.",
  "drawing_type": "part | assembly | schematic | layout | other",
  "part_kind": "short noun, e.g. bracket, flange, shaft, housing, gear, pcb; or null",
  "views": ["list of views present, e.g. front, top, side, section A-A, isometric, detail B"],
  "features": ["list of geometric/manufacturing features: holes, threads, chamfers, fillets, slots, keyway, hatching, tolerances, surface finish, welds ..."],
  "material": "material and grade as written on the drawing, or null",
  "dimensions": ["all dimensions, diameters, threads and tolerances you can read, as strings"],
  "identifiers": ["part numbers, drawing numbers, titles, revision, sheet, scale, standards (GOST/ISO/DIN)"],
  "text_on_drawing": ["every readable text string on the drawing, corrected for OCR errors"],
  "tags": ["8-15 short lowercase search tags: part type, features, material class, standard, process (welded, machined, cast, sheet-metal ...)"],
  "diagram": {{"nodes": ["block texts in reading order"], "edges": ["A -> B (label)"]}}  — only for flowcharts/block diagrams/schematics, else null,
  "language": "en | es | ca | de | fr | nl | it | mixed | none",
  "confidence": 0.0-1.0
}}
No markdown, no commentary — JSON only."""

def _b64(path: Path) -> tuple[str, str]:
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff"}[path.suffix.lower()[1:]]
    return base64.b64encode(path.read_bytes()).decode(), mime

def _post_json(url: str, payload: dict, headers: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

def _parse_vlm_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S)
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0) if m else raw)

def vlm_describe(path: Path, hints: dict, backend: str, model: str | None) -> dict | None:
    """Ask a vision-language model for a full description. Returns parsed dict or None."""
    if backend == "none":
        return None
    prompt = VLM_PROMPT.format(hints=json.dumps(hints, ensure_ascii=False, indent=1))
    b64, mime = _b64(path)
    try:
        if backend == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                print("  [vlm] ANTHROPIC_API_KEY не задан — пропускаю VLM"); return None
            data = _post_json(
                "https://api.anthropic.com/v1/messages",
                {"model": model or "claude-sonnet-4-5", "max_tokens": 1500,
                 "messages": [{"role": "user", "content": [
                     {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                     {"type": "text", "text": prompt}]}]},
                {"x-api-key": key, "anthropic-version": "2023-06-01"})
            raw = "".join(b.get("text", "") for b in data["content"])
        elif backend == "openai":
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                print("  [vlm] OPENAI_API_KEY не задан — пропускаю VLM"); return None
            data = _post_json(
                "https://api.openai.com/v1/chat/completions",
                {"model": model or "gpt-4o", "max_tokens": 1500,
                 "messages": [{"role": "user", "content": [
                     {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                     {"type": "text", "text": prompt}]}]},
                {"Authorization": f"Bearer {key}"})
            raw = data["choices"][0]["message"]["content"]
        elif backend == "ollama":
            data = _post_json(
                os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/generate",
                {"model": model or "qwen2.5vl:7b", "prompt": prompt, "images": [b64],
                 "stream": False, "format": "json", "options": {"temperature": 0.1}},
                {}, timeout=600)
            raw = data["response"]
        else:
            raise ValueError(f"unknown backend {backend}")
        out = _parse_vlm_json(raw)
        out["_backend"] = backend
        return out
    except Exception as e:  # сеть, ключ, невалидный JSON — деградируем к эвристике
        print(f"  [vlm] ошибка ({backend}): {e} — использую эвристическое описание")
        return None

def annotate(path: Path, r: DrawingReport, out: Path) -> None:
    img = cv2.imread(str(path))
    if img is None:
        return
    by_id = {n["id"]: n for n in r.diagram.get("nodes", [])}
    for n in by_id.values():
        x, y, w, h = n["bbox"]; cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
    for e in r.diagram.get("edges", []):
        a, b = by_id[e["from"]]["bbox"], by_id[e["to"]]["bbox"]
        cv2.arrowedLine(img, (a[0] + a[2] // 2, a[1] + a[3] // 2), (b[0] + b[2] // 2, b[1] + b[3] // 2), (255, 0, 255), 2)
    for x, y, rad in r.circles:
        cv2.circle(img, (x, y), rad, (0, 0, 255), 2)
    for t in r.text_regions:
        color = (0, 160, 0) if t.text else (0, 200, 255)
        cv2.rectangle(img, (t.x, t.y), (t.x + t.w, t.y + t.h), color, 2)
    cv2.imwrite(str(out), img)

# ------------------------------------------------------------------ тесты

def _font(size: int):
    for p in ["C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/System/Library/Fonts/Helvetica.ttc"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def make_test_drawings(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    W, H = 1400, 1000
    fb, fs = _font(28), _font(20)
    paths = []

    # Тест 1: кронштейн — рамка, штамп, 4 отверстия, размеры
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    d.rectangle([300, 250, 900, 650], outline="black", width=4)
    for cx, cy in [(400, 350), (800, 350), (400, 550), (800, 550)]:
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline="black", width=3)
        d.line([cx - 40, cy, cx + 40, cy], fill="black"); d.line([cx, cy - 40, cx, cy + 40], fill="black")
    d.line([300, 700, 900, 700], fill="black")
    d.line([300, 660, 300, 710], fill="black"); d.line([900, 660, 900, 710], fill="black")
    d.text((560, 705), "600", font=fb, fill="black")
    d.line([950, 250, 950, 650], fill="black"); d.text((965, 430), "400", font=fb, fill="black")
    d.text((420, 300), "4 otv. D30", font=fs, fill="black")
    d.rectangle([950, 830, W - 20, H - 20], outline="black", width=3)
    d.text((965, 845), "BRACKET BR-01", font=fb, fill="black")
    d.text((965, 885), "Steel 09G2S   Scale 1:2", font=fs, fill="black")
    d.text((965, 915), "Sheet 1 of 1   Rev A", font=fs, fill="black")
    p = folder / "test_bracket.png"; im.save(p); paths.append(p)

    # Тест 2: фланец — вид сверху + сечение со штриховкой, без рамки
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    cx, cy = 420, 480
    for rr in (300, 240, 90):
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline="black", width=3)
    for k in range(6):
        a = math.radians(60 * k)
        hx, hy = cx + 240 * math.cos(a), cy + 240 * math.sin(a)
        d.ellipse([hx - 22, hy - 22, hx + 22, hy + 22], outline="black", width=2)
    d.line([cx - 330, cy, cx + 330, cy], fill="black"); d.line([cx, cy - 330, cx, cy + 330], fill="black")
    x0, y0 = 900, 200
    d.rectangle([x0, y0, x0 + 300, y0 + 560], outline="black", width=3)
    d.line([x0 + 110, y0, x0 + 110, y0 + 560], fill="black", width=3)
    d.line([x0 + 190, y0, x0 + 190, y0 + 560], fill="black", width=3)
    for xx in range(x0, x0 + 300, 18):
        for s0, s1 in ((x0, x0 + 110), (x0 + 190, x0 + 300)):
            if s0 <= xx < s1:
                d.line([xx, y0 + 560, min(xx + 80, s1), y0 + 480], fill="black")
                d.line([xx, y0 + 300, min(xx + 80, s1), y0 + 220], fill="black")
    d.text((x0 + 90, y0 - 50), "A-A", font=fb, fill="black")
    d.text((cx - 60, cy + 350), "FLANGE DN150 PN16", font=fb, fill="black")
    d.text((cx - 60, cy + 390), "6 x M20", font=fs, fill="black")
    p = folder / "test_flange.png"; im.save(p); paths.append(p)

    # Тест 3: немецкий штамп
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    d.rectangle([250, 200, 850, 600], outline="black", width=4)
    for cx, cy in [(350, 300), (750, 300), (350, 500), (750, 500)]:
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], outline="black", width=3)
    d.text((380, 240), "4x Bohrung Ø8", font=fs, fill="black")
    d.line([250, 650, 850, 650], fill="black"); d.text((530, 655), "600", font=fb, fill="black")
    d.rectangle([950, 830, W - 20, H - 20], outline="black", width=3)
    d.text((965, 845), "Halter HB-12", font=fb, fill="black")
    d.text((965, 885), "Werkstoff: S235JR   Maßstab 1:2", font=fs, fill="black")
    d.text((965, 915), "Blatt 1 von 1   Änderung B", font=fs, fill="black")
    p = folder / "test_halter_de.png"; im.save(p); paths.append(p)

    # Тест 4: испанский штамп
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    cx, cy = 450, 450
    for rr in (280, 220, 80):
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline="black", width=3)
    for k in range(8):
        a = math.radians(45 * k); hx, hy = cx + 220 * math.cos(a), cy + 220 * math.sin(a)
        d.ellipse([hx - 15, hy - 15, hx + 15, hy + 15], outline="black", width=2)
    d.text((cx - 80, cy + 300), "8 agujeros Ø12", font=fs, fill="black")
    d.rectangle([950, 830, W - 20, H - 20], outline="black", width=3)
    d.text((965, 845), "Brida DN80 PN10", font=fb, fill="black")
    d.text((965, 885), "Material: Acero inoxidable 1.4301", font=fs, fill="black")
    d.text((965, 915), "Escala 1:1   Hoja 1 de 2   Rev. C", font=fs, fill="black")
    p = folder / "test_brida_es.png"; im.save(p); paths.append(p)

    def title_block(d, lines):
        d.rectangle([950, 830, W - 20, H - 20], outline="black", width=3)
        for i, (txt, f) in enumerate(lines):
            d.text((965, 845 + 35 * i), txt, font=f, fill="black")

    # Тест 5: французский — вал со ступенями
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    for x0, x1, r in [(150, 400, 40), (400, 800, 60), (800, 1000, 45)]:
        d.rectangle([x0, 400 - r, x1, 400 + r], outline="black", width=3)
    d.line([130, 400, 1020, 400], fill="black")
    d.text((560, 470), "Ø120", font=fb, fill="black"); d.text((260, 470), "Ø80", font=fb, fill="black")
    d.line([150, 520, 1000, 520], fill="black"); d.text((550, 525), "850", font=fb, fill="black")
    d.text((420, 300), "2 trous Ø10", font=fs, fill="black")
    title_block(d, [("Arbre de transmission AT-204", fb), ("Matière : Acier C45   Échelle 1:2", fs), ("Feuille 1 sur 1   Indice A", fs)])
    p = folder / "test_arbre_fr.png"; im.save(p); paths.append(p)

    # Тест 6: нидерландский — крышка с 6 отверстиями
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    d.rounded_rectangle([250, 200, 850, 650], radius=60, outline="black", width=4)
    for cx, cy in [(320, 270), (550, 270), (780, 270), (320, 580), (550, 580), (780, 580)]:
        d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline="black", width=2)
    d.text((470, 400), "6 gaten Ø9", font=fs, fill="black")
    d.line([250, 700, 850, 700], fill="black"); d.text((530, 705), "600", font=fb, fill="black")
    title_block(d, [("Deksel DK-31", fb), ("Materiaal: Aluminium 6082   Schaal 1:1", fs), ("Blad 1 van 1   Revisie 02", fs)])
    p = folder / "test_deksel_nl.png"; im.save(p); paths.append(p)

    # Тест 7: каталанский — кронштейн
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    d.polygon([(250, 250), (700, 250), (700, 350), (350, 350), (350, 650), (250, 650)], outline="black", width=4)
    for cx, cy in [(300, 450), (300, 580), (500, 300), (620, 300)]:
        d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline="black", width=2)
    d.text((420, 420), "4 forats Ø8", font=fs, fill="black")
    d.line([250, 700, 700, 700], fill="black"); d.text((460, 705), "450", font=fb, fill="black")
    title_block(d, [("Suport angular SA-07", fb), ("Material: Acer S275JR   Escala 1:2", fs), ("Full 1 de 1   Revisió B", fs)])
    p = folder / "test_suport_ca.png"; im.save(p); paths.append(p)

    # Тест 7b: итальянский — втулка (сечение со штриховкой)
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
    d.rectangle([300, 300, 800, 600], outline="black", width=4)
    d.rectangle([300, 400, 800, 500], outline="white", fill="white")
    d.line([300, 400, 800, 400], fill="black", width=3); d.line([300, 500, 800, 500], fill="black", width=3)
    for xx in range(300, 800, 16):
        d.line([xx, 400, min(xx + 60, 800), 340], fill="black")
        d.line([xx, 600, min(xx + 60, 800), 540], fill="black")
    d.line([280, 450, 820, 450], fill="black")
    d.text((520, 610), "Ø60", font=fb, fill="black"); d.text((520, 250), "Ø40 H7", font=fs, fill="black")
    d.line([300, 660, 800, 660], fill="black"); d.text((530, 665), "500", font=fb, fill="black")
    d.text((350, 200), "2 fori Ø6", font=fs, fill="black")
    title_block(d, [("Boccola BC-118", fb), ("Materiale: Bronzo CuSn8   Scala 1:1", fs), ("Foglio 1 di 1   Revisione 03", fs)])
    p = folder / "test_boccola_it.png"; im.save(p); paths.append(p)

    # Тест 8: план этажа (es) — проверка домена
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 1100, 800], outline="black", width=6)
    d.line([500, 100, 500, 800], fill="black", width=4); d.line([500, 450, 1100, 450], fill="black", width=4)
    d.line([100, 500, 500, 500], fill="black", width=4)
    for x0, y0 in [(280, 500), (500, 300), (750, 450)]:          # дверные проёмы
        d.rectangle([x0 - 40, y0 - 4, x0 + 40, y0 + 4], fill="white")
    d.text((200, 280), "SALÓN 24 m²", font=fb, fill="black"); d.text((200, 620), "COCINA 12 m²", font=fb, fill="black")
    d.text((700, 250), "DORMITORIO 16 m²", font=fb, fill="black"); d.text((700, 600), "BAÑO 6 m²", font=fb, fill="black")
    d.text((100, 830), "Planta baja   Escala 1:50   Vivienda unifamiliar", font=fs, fill="black")
    p = folder / "test_planta_es.png"; im.save(p); paths.append(p)

    # Тест 9: электросхема (de) — проверка домена
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.line([200, 300, 1200, 300], fill="black", width=2); d.line([200, 700, 1200, 700], fill="black", width=2)
    for x in (400, 700, 1000):
        d.line([x, 300, x, 700], fill="black", width=2)
        d.rectangle([x - 20, 450, x + 20, 550], outline="black", width=2, fill="white")
        d.text((x + 30, 480), f"R{(x-100)//300}", font=fs, fill="black")
    d.ellipse([160, 460, 240, 540], outline="black", width=2); d.text((185, 485), "~", font=fb, fill="black")
    d.line([200, 300, 200, 460], fill="black", width=2); d.line([200, 540, 200, 700], fill="black", width=2)
    d.text((300, 200), "Schaltplan Netzteil 24V   Blatt 1 von 1", font=fs, fill="black")
    p = folder / "test_schaltplan_de.png"; im.save(p); paths.append(p)

    # ---------- Тест 10: флоучарт (en)
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    def box(x, y, w, h, txt, shape="rect"):
        if shape == "rect":
            d.rectangle([x, y, x + w, y + h], outline="black", width=3)
        elif shape == "round":
            d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, outline="black", width=3)
        elif shape == "diamond":
            d.polygon([(x + w // 2, y), (x + w, y + h // 2), (x + w // 2, y + h), (x, y + h // 2)], outline="black", width=3)
        tw = d.textlength(txt, font=fs)
        d.text((x + (w - tw) / 2, y + h / 2 - 12), txt, font=fs, fill="black")
    def arrow(x1, y1, x2, y2, label=""):
        d.line([x1, y1, x2, y2], fill="black", width=3)
        ang = math.atan2(y2 - y1, x2 - x1)
        for sgn in (1, -1):
            d.line([x2, y2, x2 - 14 * math.cos(ang - sgn * 0.45), y2 - 14 * math.sin(ang - sgn * 0.45)], fill="black", width=3)
        if label:
            d.text(((x1 + x2) / 2 + 8, (y1 + y2) / 2 - 24), label, font=fs, fill="black")
    box(560, 60, 280, 60, "Start", "round")
    box(560, 180, 280, 70, "Read sensor value")
    box(560, 310, 280, 120, "Value > limit?", "diamond")
    box(200, 500, 280, 70, "Open valve V-101")
    box(920, 500, 280, 70, "Log value")
    box(560, 650, 280, 70, "Wait 5 s")
    box(560, 780, 280, 60, "End", "round")
    arrow(700, 120, 700, 180); arrow(700, 250, 700, 310)
    arrow(560, 370, 340, 500, "yes"); arrow(840, 370, 1060, 500, "no")
    arrow(340, 570, 620, 650); arrow(1060, 570, 780, 650); arrow(700, 720, 700, 780)
    d.text((40, 940), "Flowchart: overpressure protection loop   Rev 2", font=fs, fill="black")
    p = folder / "test_flowchart_en.png"; im.save(p); paths.append(p)

    # ---------- Тест 11: архитектурная блок-схема (de)
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    box(100, 150, 260, 90, "Sensorik"); box(570, 150, 260, 90, "SPS S7-1500"); box(1040, 150, 260, 90, "HMI Panel")
    box(570, 400, 260, 90, "OPC UA Server"); box(570, 650, 260, 90, "Datenbank")
    box(1040, 650, 260, 90, "Cloud Gateway")
    arrow(360, 195, 570, 195, "4-20 mA"); arrow(830, 195, 1040, 195, "Profinet")
    arrow(700, 240, 700, 400); arrow(700, 490, 700, 650); arrow(830, 695, 1040, 695, "MQTT")
    d.text((40, 60), "Systemarchitektur Anlage 3   Blatt 1 von 1", font=fb, fill="black")
    p = folder / "test_blockdiagram_de.png"; im.save(p); paths.append(p)

    # ---------- Тест 12: P&ID-подобная схема (es)
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    d.rectangle([150, 300, 350, 700], outline="black", width=3); d.text((175, 480), "T-101", font=fb, fill="black")
    d.ellipse([650, 450, 750, 550], outline="black", width=3); d.text((672, 485), "P-101", font=fs, fill="black")
    d.rectangle([1000, 350, 1200, 650], outline="black", width=3); d.text((1030, 480), "R-201", font=fb, fill="black")
    d.line([350, 500, 650, 500], fill="black", width=3); d.line([750, 500, 1000, 500], fill="black", width=3)
    d.polygon([(480, 480), (520, 500), (480, 520)], outline="black", width=2)
    d.polygon([(520, 480), (480, 500), (520, 520)], outline="black", width=2)
    d.text((470, 430), "V-12", font=fs, fill="black")
    d.text((820, 460), "DN50 PN16", font=fs, fill="black")
    d.text((40, 60), "Diagrama P&ID   Unidad 100   Hoja 2 de 5", font=fb, fill="black")
    p = folder / "test_pid_es.png"; im.save(p); paths.append(p)
    return paths

# ------------------------------------------------------------------ main

def pdf_pages(path: Path, dpi: int = PDF_DPI):
    """Растеризация страниц PDF → (имя_страницы, BGR-массив). Векторные PDF тоже рендерятся."""
    try:
        import pymupdf
    except ImportError:
        print(f"  [pdf] pymupdf не установлен (pip install pymupdf) — {path.name} пропущен"); return
    doc = pymupdf.open(str(path))
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
        arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
        yield f"{path.stem}_p{i+1}", cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def main() -> None:
    ap = argparse.ArgumentParser(description="Описание чертежей из папки drawing/ + OCR + RAG-индекс")
    ap.add_argument("--min-conf", type=float, default=50, help="порог доверия OCR, 0–100")
    ap.add_argument("--make-tests", action="store_true", help="создать тестовые чертежи в drawing/")
    ap.add_argument("--vlm", choices=["none", "anthropic", "openai", "ollama"], default="none",
                    help="бэкенд VLM для полноценного описания (ключ — через переменную окружения)")
    ap.add_argument("--model", default=None, help="имя модели VLM (по умолчанию для бэкенда)")
    ap.add_argument("--ocr", choices=["rapidocr", "easyocr"], default="rapidocr",
                    help="easyocr — латиница с диакритикой ç à è ï ü ß ñ (en/es/ca/de/fr/nl/it)")
    ap.add_argument("--only", default=None, help="обрабатывать только файлы, имя которых содержит подстроку")
    ap.add_argument("--scan", choices=["auto", "on", "off"], default="auto",
                    help="подготовка сканов/ксерокопий: deskew, шум, фон, контраст (auto — по метрикам)")
    ap.add_argument("--clip", action="store_true",
                    help="zero-shot теги + визуальный эмбеддинг через CLIP (pip install torch open_clip_torch)")
    a = ap.parse_args()

    tagger = None
    if a.clip:
        try:
            from app.vision.clip_tags import ClipTagger
            tagger = ClipTagger()
        except Exception as e:
            print(f"  [clip] недоступен: {e}")

    DRAWING_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)

    if a.make_tests:
        for p in make_test_drawings(DRAWING_DIR):
            print("создан", p.relative_to(HERE))

    files = sorted(p for p in DRAWING_DIR.iterdir() if p.suffix.lower() in IMG_EXTS | {".pdf"}
                   and (not a.only or a.only in p.name))
    if not files:
        print(f"Папка {DRAWING_DIR} пуста — положите туда чертежи или запустите с --make-tests")
        return
    if not HAS_OCR:
        print("rapidocr-onnxruntime не установлен — OCR будет пропущен "
              "(pip install rapidocr-onnxruntime)")

    index = OUT_DIR / "rag_index.jsonl"
    with index.open("w", encoding="utf-8") as idx:
        items = []                                   # (имя, путь для VLM/CLIP, массив)
        for f in files:
            if f.suffix.lower() == ".pdf":
                for name, arr in pdf_pages(f) or []:
                    tmp = OUT_DIR / f"{name}.png"; cv2.imwrite(str(tmp), arr)
                    items.append((name, tmp, arr))
            else:
                items.append((f.stem, f, None))
        for name, f, arr in items:
            rep = analyze(f, a.min_conf, a.ocr, a.scan, arr)
            rep.file = name + (f.suffix if arr is None else ".pdf")
            md = describe(rep)
            clip = tagger(f) if tagger else None
            if clip:
                np.save(OUT_DIR / f"{name}.clip.npy", clip["embedding"])
            hints = {"ocr_text": [t.text for t in rep.text_regions if t.text],
                     "circles": len(rep.circles), "has_frame": rep.has_border,
                     "has_title_block": rep.has_title_block,
                     "heuristic_tags": classify_drawing(rep, interpret_text(rep.text_regions, rep.width, rep.height))}
            vlm = vlm_describe(f, hints, a.vlm, a.model)
            if vlm:
                (OUT_DIR / f"{name}.vlm.json").write_text(
                    json.dumps(vlm, ensure_ascii=False, indent=2), encoding="utf-8")
                md += "\n\n## VLM description\n" + (vlm.get("summary") or "")
            doc = rag_document(rep, vlm, clip)
            (OUT_DIR / f"{name}.md").write_text(md, encoding="utf-8")
            (OUT_DIR / f"{name}.json").write_text(rep.to_json(), encoding="utf-8")
            (OUT_DIR / f"{name}.rag.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            idx.write(json.dumps(doc, ensure_ascii=False) + "\n")
            annotate(f, rep, OUT_DIR / f"{name}_annotated.png")
            print(md, "\n\n## RAG text\n" + doc["text"], "\n" + "-" * 70)

    print(f"Results: {OUT_DIR}  (RAG index: {index.name}, {len(items)} docs)")

if __name__ == "__main__":
    main()