"""
Layout Aware Text Extraction
CSS-Cover + OCR Correction
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np


# =============================================================================
# KONSTANTA KONFIGURASI
# =============================================================================

MIN_CONF              = 0.38
UPSCALE_IF_WIDTH_BELOW = 1600
OCR_UPSCALE           = 2.0
FONT_FAMILY           = '"Poppins","Montserrat","Trebuchet MS","Arial",sans-serif'
LINE_HEIGHT           = 1.12
MIN_FONT_SIZE         = 10
MAX_FONT_SIZE         = 90

IGNORE_TOP_RIGHT_LOGO = True
LOGO_X_START_RATIO    = 0.78
LOGO_Y_END_RATIO      = 0.18
MIN_LOCAL_CONTRAST    = 18.0


# =============================================================================
# UTILITAS UMUM
# =============================================================================

class NumpyEncoder(json.JSONEncoder):
    """JSON encoder yang mendukung tipe data NumPy."""

    def default(self, obj: Any):
        if isinstance(obj, np.integer):  return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.bool_):    return bool(obj)
        if isinstance(obj, np.ndarray):  return obj.tolist()
        return super().default(obj)


def safe_int(v) -> int:
    return int(round(float(v)))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def bgr_to_hex(bgr) -> str:
    b, g, r = [int(x) for x in bgr[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance_bgr(px):
    return 0.114 * px[..., 0] + 0.587 * px[..., 1] + 0.299 * px[..., 2]


# =============================================================================
# KOREKSI & NORMALISASI TEKS
# =============================================================================

# Pola penggantian teks yang umum dijumpai pada dokumen target
COMMON_REPLACEMENTS = [
    (r'Jangkauan\s+P\s*asar\s+dan\s+K\s*ontak', 'Jangkauan Pasar dan Kontak'),
    (r'Portofolio\s+Layanan\s+Utama',            'Portofolio Layanan Utama'),
    (r'Ekosistem\s+Inovasi\s+Terintegrasi',      'Ekosistem Inovasi Terintegrasi'),
    (r'Tentang\s+Perusahaan',                    'Tentang Perusahaan'),
    (r'Profile\s+Image\s+Studio',                'Profile Image Studio'),
    (r'Talent\s+Development',                    'Talent Development'),
    (r'Talent\s+Develop\w*',                     'Talent Development'),
    (r'Cyber\s+Security',                        'Cyber Security'),
    (r'Cloud\s+Computing',                       'Cloud Computing'),
]


def norm_text(t: str) -> str:
    """Normalisasi whitespace dan karakter dash."""
    t = str(t or '').strip()
    t = t.replace('—', '-').replace('–', '-')
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def fix_spacing(text: str) -> str:
    """Perbaiki spasi yang hilang atau berlebih pada teks OCR."""
    t = norm_text(text)
    if re.search(r'\w+\.\w+', t):
        return t.replace(' ', '') if 'profile' in t.lower() else t
    t = re.sub(r'([a-z])([A-Z])',     r'\1 \2', t)
    t = re.sub(r'([0-9])([A-Za-z])', r'\1 \2', t)
    t = re.sub(r'([A-Za-z])([0-9])', r'\1 \2', t)
    t = re.sub(r'\s+([,.:;!?/])',    r'\1',    t)
    t = re.sub(r'([/(])\s+',         r'\1',    t)
    t = re.sub(r'\s+',               ' ',      t)
    return t.strip()


def correct_text(text: str) -> str:
    """Koreksi kesalahan OCR yang umum dan terapkan penggantian standar."""
    t = fix_spacing(text)

    # Koreksi kata tunggal yang sering salah
    replacements = {
        r'\bCehter\b':   'Center',
        r'\bResearc\b':  'Research',
        r'\bResourc\b':  'Resource',
        r'\bprofie\b':   'profile',
        r'\bImoge\b':    'Image',
        r'\bStudic\b':   'Studio',
    }
    for pattern, repl in replacements.items():
        t = re.sub(pattern, repl, t, flags=re.I)

    # Perbaiki spasi di sekitar tanda baca
    t = re.sub(r'\s*,\s*', ', ', t)
    t = re.sub(r'\s*\.\s*', '.',  t)

    # Tangani format khusus domain
    t = re.sub(r'profile\s*image\s*\.\s*studio', 'profileimage.studio', t, flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip()

    # Terapkan penggantian berbasis pola
    for pattern, repl in COMMON_REPLACEMENTS:
        if re.fullmatch(pattern, t, flags=re.I):
            return repl
        if re.search(pattern, t, flags=re.I):
            return re.sub(pattern, repl, t, flags=re.I).strip()

    return t


def text_quality_score(text: str) -> float:
    """Hitung skor kualitas teks (0–1) berdasarkan rasio karakter valid."""
    t = text.strip()
    if not t:
        return 0.0
    good = sum(ch.isalnum() or ch in '.,:/-&() ' for ch in t)
    return good / max(1, len(t))


# =============================================================================
# PRA-PEMROSESAN GAMBAR & OCR
# =============================================================================

def preprocess_for_ocr(img) -> tuple:
    """Tingkatkan resolusi dan kontras gambar sebelum OCR."""
    h, w = img.shape[:2]
    scale = OCR_UPSCALE if w < UPSCALE_IF_WIDTH_BELOW else 1.0
    proc = img.copy()
    if scale != 1.0:
        proc = cv2.resize(
            proc,
            (safe_int(w * scale), safe_int(h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
    hsv = cv2.cvtColor(proc, cv2.COLOR_BGR2HSV)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])
    proc = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return proc, scale


def run_paddleocr(temp_path: Path, scale: float) -> list[dict]:
    """Jalankan PaddleOCR dan kembalikan daftar elemen teks terdeteksi."""
    try:
        from paddleocr import PaddleOCR
    except Exception as e:
        raise RuntimeError('PaddleOCR belum terpasang.') from e

    try:
        ocr = PaddleOCR(
            use_angle_cls=True, lang='en', show_log=False,
            use_gpu=False, det_db_thresh=0.25, det_db_box_thresh=0.45,
        )
    except TypeError:
        ocr = PaddleOCR(use_angle_cls=True, lang='en')

    result = ocr.ocr(str(temp_path), cls=True)
    if not result:
        return []

    lines = (
        result[0]
        if isinstance(result, list) and result and isinstance(result[0], list)
        else result
    )
    out = []
    for item in lines:
        if not item or len(item) < 2:
            continue
        box, rec = item[0], item[1]
        if not rec or len(rec) < 2:
            continue
        text, conf = str(rec[0]), float(rec[1])
        if conf < MIN_CONF or not text.strip():
            continue
        xs = [float(p[0]) / scale for p in box]
        ys = [float(p[1]) / scale for p in box]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        out.append({
            'text':       correct_text(text),
            'x':          safe_int(x1),
            'y':          safe_int(y1),
            'w':          safe_int(max(8, x2 - x1)),
            'h':          safe_int(max(8, y2 - y1)),
            'confidence': round(conf, 3),
        })
    return out


def run_easyocr(temp_path: Path, scale: float) -> list[dict]:
    """Jalankan EasyOCR dan kembalikan daftar elemen teks terdeteksi."""
    try:
        import easyocr
    except Exception as e:
        raise RuntimeError('EasyOCR belum terpasang.') from e

    reader = easyocr.Reader(['en', 'id'], gpu=False, verbose=False)
    results = reader.readtext(str(temp_path), paragraph=False, detail=1)
    out = []
    for box, text, conf in results:
        if float(conf) < MIN_CONF or not str(text).strip():
            continue
        xs = [float(p[0]) / scale for p in box]
        ys = [float(p[1]) / scale for p in box]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        out.append({
            'text':       correct_text(text),
            'x':          safe_int(x1),
            'y':          safe_int(y1),
            'w':          safe_int(max(8, x2 - x1)),
            'h':          safe_int(max(8, y2 - y1)),
            'confidence': round(float(conf), 3),
        })
    return out


def run_ocr(img, out_dir: Path, stem: str, engine: str) -> list[dict]:
    """Jalankan OCR (PaddleOCR atau EasyOCR) pada gambar yang diberikan."""
    proc, scale = preprocess_for_ocr(img)
    temp_path = out_dir / f'{stem}_ocr_input.png'
    cv2.imwrite(str(temp_path), proc)

    if engine == 'easyocr':
        return run_easyocr(temp_path, scale)
    try:
        return run_paddleocr(temp_path, scale)
    except Exception as e:
        print(f'  PaddleOCR gagal: {e}')
        return run_easyocr(temp_path, scale)


# =============================================================================
# ANALISIS VISUAL ELEMEN TEKS
# =============================================================================

def expand_box(el: dict, img_w: int, img_h: int,
               pad_x: int = None, pad_y: int = None) -> tuple:
    """Perluas bounding box elemen dengan padding."""
    x, y, w, h = el['x'], el['y'], el['w'], el['h']
    px = pad_x if pad_x is not None else max(4, safe_int(h * 0.25))
    py = pad_y if pad_y is not None else max(3, safe_int(h * 0.18))
    return (
        clamp(x - px,     0, img_w - 1),
        clamp(y - py,     0, img_h - 1),
        clamp(x + w + px, 0, img_w),
        clamp(y + h + py, 0, img_h),
    )


def estimate_bg_color(crop) -> np.ndarray:
    """Estimasi warna latar belakang dari piksel border crop."""
    if crop.size == 0:
        return np.array([255, 255, 255], dtype=np.uint8)
    h, w = crop.shape[:2]
    t = max(1, min(6, h // 4, w // 4))
    border = np.vstack([
        crop[:t,  :,  :].reshape(-1, 3),
        crop[-t:, :,  :].reshape(-1, 3),
        crop[:,  :t,  :].reshape(-1, 3),
        crop[:,  -t:, :].reshape(-1, 3),
    ])
    return np.median(border, axis=0).astype(np.uint8)


def local_contrast(crop) -> float:
    """Hitung kontras lokal (persentil 95 − 5) dari crop grayscale."""
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(np.percentile(gray, 95) - np.percentile(gray, 5))


def text_mask_from_crop(crop) -> np.ndarray:
    """Buat binary mask yang memisahkan piksel teks dari latar belakang."""
    if crop.size == 0:
        return np.zeros(crop.shape[:2], dtype=np.uint8)

    gray   = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bg     = estimate_bg_color(crop)
    bg_lum = float(luminance_bgr(bg.reshape(1, 1, 3))[0, 0])

    thresh_type = (
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
        if bg_lum < 120
        else cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    _, m = cv2.threshold(gray, 0, 255, thresh_type)

    h2, w2 = m.shape[:2]
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    clean = np.zeros_like(m)
    for i in range(1, n):
        x2, y2, cw, ch, area = stats[i]
        if area < 3:                             continue
        if cw > 0.98 * w2 and ch > 0.98 * h2:  continue
        if ch < max(2, h2 * 0.08):              continue
        clean[labels == i] = 255

    if clean.sum() == 0:
        clean = m
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel, iterations=1)


# =============================================================================
# KLASIFIKASI ELEMEN TEKS
# =============================================================================

def is_top_title_area(el: dict, img_h: int) -> bool:
    """Cek apakah elemen berada di area judul bagian atas."""
    if el.get('y', 0) < img_h * 0.18:
        text = norm_text(el.get('text', '')).lower()
        logo_noise = ['pis', 'profileimage', 'studio']
        if any(k == text or k in text for k in logo_noise) and el.get('x', 0) > 0:
            return False
        return True
    return False


def is_hero_title(el: dict, img_w: int, img_h: int) -> bool:
    """Cek apakah elemen adalah judul hero (besar, di bagian tengah gambar)."""
    w, h, y    = el.get('w', 0), el.get('h', 0), el.get('y', 0)
    text_words = len(str(el.get('text', '')).split())
    if img_h * 0.18 <= y < img_h * 0.70:
        if (w > img_w * 0.45 or h > img_h * 0.12) and text_words < 15:
            return True
    return False


def is_in_logo_region(el: dict, img_w: int, img_h: int) -> bool:
    """Cek apakah elemen berada di area logo pojok kanan atas."""
    if not IGNORE_TOP_RIGHT_LOGO:
        return False
    cx = el['x'] + el['w'] / 2
    cy = el['y'] + el['h'] / 2
    return cx > img_w * LOGO_X_START_RATIO and cy < img_h * LOGO_Y_END_RATIO


# =============================================================================
# ESTIMASI GAYA (FONT, WARNA, ALIGNMENT)
# =============================================================================

def estimate_text_color(crop, mask, el: dict, img_h: int) -> str:
    """Estimasi warna teks menggunakan k-means clustering (k=2)."""
    if crop.size == 0:
        return '#111827'
    pixels = crop.reshape(-1, 3).astype(np.float32)
    if len(pixels) < 10:
        return '#111827'
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(
        pixels, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS,
    )
    count_0    = np.sum(labels == 0)
    count_1    = np.sum(labels == 1)
    fg_center  = centers[0] if count_0 < count_1 else centers[1]
    fg_center  = np.clip(fg_center, 0, 255).astype(np.uint8)
    return bgr_to_hex(fg_center)


def estimate_cover_color(crop) -> str:
    """Estimasi warna latar belakang (cover) dari crop."""
    return bgr_to_hex(estimate_bg_color(crop))


def estimate_font_size(el: dict, img_w: int, img_h: int) -> int:
    """Estimasi ukuran font (px) berdasarkan dimensi bounding box dan tipe elemen."""
    h = el['h']

    if is_hero_title(el, img_w, img_h):
        text_len   = max(1, len(el.get('text', '')))
        char_aspect = 0.55
        estimated  = np.sqrt((h * el['w']) / (text_len * char_aspect))
        fs = min(h * 1.05, estimated)
        return safe_int(max(48, min(270, fs * 1.80)))

    if is_top_title_area(el, img_h):
        el['text'] = el['text'].upper()
        return safe_int(max(28, min(200, h * 1.80)))

    fs = h * 1.02
    if len(el.get('text', '')) <= 3:
        fs = h * 0.95
    return safe_int(max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, fs)))


def estimate_weight(el: dict, bg_lum: float, img_w: int, img_h: int) -> str:
    """Estimasi font-weight berdasarkan tipe elemen dan konteks."""
    t = el['text'].lower()
    if is_hero_title(el, img_w, img_h) or is_top_title_area(el, img_h):
        return '700'
    heavy_keywords = [
        'talent development', 'cyber security', 'cloud computing',
        'research center', 'human resource', 'services',
    ]
    if any(k in t for k in heavy_keywords): return '700'
    if bg_lum < 105:                        return '600'
    if any(k in t for k in ['lokasi:', 'website:']): return '600'
    return '500'


def estimate_align(el: dict, img_w: int) -> str:
    """Estimasi text-align berdasarkan posisi dan konten elemen."""
    t = el['text'].lower()
    if any(t.startswith(k) for k in ['lokasi:', 'website:', 'profile image studio']):
        return 'left'
    if el['x'] < img_w * 0.12 and el['w'] > img_w * 0.35:
        return 'left'
    return 'center'


def enrich_style(img, elements: list[dict]) -> list[dict]:
    """Tambahkan informasi gaya visual ke setiap elemen teks."""
    img_h, img_w = img.shape[:2]
    enriched = []
    for el in elements:
        pad_x = max(6, safe_int(el['h'] * 0.35))
        pad_y = max(4, safe_int(el['h'] * 0.25))
        x1, y1, x2, y2 = expand_box(el, img_w, img_h, pad_x=pad_x, pad_y=pad_y)
        crop   = img[y1:y2, x1:x2]
        mask   = text_mask_from_crop(crop)
        bg     = estimate_bg_color(crop)
        bg_lum = float(luminance_bgr(bg.reshape(1, 1, 3))[0, 0])
        enriched.append({
            **{k: v for k, v in el.items() if k != 'tokens'},
            'font_size':   estimate_font_size(el, img_w, img_h),
            'line_height': LINE_HEIGHT,
            'font_weight': estimate_weight(el, bg_lum, img_w, img_h),
            'color':       estimate_text_color(crop, mask, el, img_h),
            'cover_color': estimate_cover_color(crop),
            'align':       estimate_align(el, img_w),
            'bg_lum':      round(bg_lum, 2),
        })
    return enriched


# =============================================================================
# FILTER, DEDUPLIKASI, & MERGE ELEMEN
# =============================================================================

def filter_noise(img, elements: list[dict]) -> list[dict]:
    """Hapus elemen yang dianggap noise (kualitas rendah, logo, kontras lemah)."""
    img_h, img_w = img.shape[:2]
    out = []
    for el in elements:
        text = norm_text(el['text'])
        if not text or text_quality_score(text) < 0.70:
            continue
        if is_in_logo_region(el, img_w, img_h):
            continue
        if el['h'] < 8 or el['w'] < 8:
            continue
        x1, y1, x2, y2 = expand_box(el, img_w, img_h, pad_x=2, pad_y=2)
        crop     = img[y1:y2, x1:x2]
        contrast = local_contrast(crop)
        if contrast < MIN_LOCAL_CONTRAST and el.get('confidence', 1.0) < 0.80:
            continue
        el             = dict(el)
        el['text']     = correct_text(text)
        el['contrast'] = round(contrast, 2)
        out.append(el)
    return out


def iou(a: dict, b: dict) -> float:
    """Hitung Intersection over Union (IoU) antara dua bounding box."""
    ax1, ay1 = a['x'],          a['y']
    ax2, ay2 = a['x'] + a['w'], a['y'] + a['h']
    bx1, by1 = b['x'],          b['y']
    bx2, by2 = b['x'] + b['w'], b['y'] + b['h']
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / max(1, union)


def vertical_overlap_ratio(a: dict, b: dict) -> float:
    """Hitung rasio overlap vertikal antara dua bounding box."""
    ay1, ay2 = a['y'], a['y'] + a['h']
    by1, by2 = b['y'], b['y'] + b['h']
    ov = max(0, min(ay2, by2) - max(ay1, by1))
    return ov / max(1, min(a['h'], b['h']))


def deduplicate(elements: list[dict]) -> list[dict]:
    """Hapus elemen duplikat berdasarkan IoU dan kesamaan teks."""
    sorted_els = sorted(
        elements,
        key=lambda e: (e.get('confidence', 0), e['w'] * e['h']),
        reverse=True,
    )
    kept = []
    for el in sorted_els:
        duplicate = False
        for k in kept:
            same_text = el['text'].lower() == k['text'].lower()
            if iou(el, k) > 0.55:
                duplicate = True; break
            if same_text and abs(el['y'] - k['y']) < max(el['h'], k['h']) * 0.75:
                duplicate = True; break
        if not duplicate:
            kept.append(el)
    return sorted(kept, key=lambda e: (e['y'], e['x']))


def merge_same_line(elements: list[dict], img_w: int) -> list[dict]:
    """Gabungkan elemen-elemen yang berada pada baris yang sama."""
    if not elements:
        return []

    els   = sorted(elements, key=lambda e: (e['y'] + e['h'] / 2, e['x']))
    lines = []

    for el in els:
        placed = False
        for line in lines:
            line_box = {
                'x': min(e['x']         for e in line),
                'y': min(e['y']         for e in line),
                'w': max(e['x'] + e['w'] for e in line) - min(e['x'] for e in line),
                'h': max(e['y'] + e['h'] for e in line) - min(e['y'] for e in line),
            }
            if vertical_overlap_ratio(line_box, el) < 0.62:
                continue
            last  = max(line, key=lambda e: e['x'])
            gap   = el['x'] - (last['x'] + last['w'])
            avg_h = np.median([e['h'] for e in line] + [el['h']])
            if gap < -avg_h * 0.40:
                continue
            if gap <= max(20, avg_h * 1.35):
                line.append(el)
                placed = True
                break
        if not placed:
            lines.append([el])

    merged = []
    for group in lines:
        group = sorted(group, key=lambda e: e['x'])
        x1    = min(e['x']          for e in group)
        y1    = min(e['y']          for e in group)
        x2    = max(e['x'] + e['w'] for e in group)
        y2    = max(e['y'] + e['h'] for e in group)
        text  = correct_text(' '.join(e['text'] for e in group))
        merged.append({
            'text':       text,
            'x':          safe_int(x1),
            'y':          safe_int(y1),
            'w':          safe_int(x2 - x1),
            'h':          safe_int(y2 - y1),
            'confidence': round(float(np.mean([e.get('confidence', 1.0) for e in group])), 3),
            'tokens':     group,
        })
    return deduplicate(merged)


# =============================================================================
# INPAINTING LATAR BELAKANG
# =============================================================================

def build_mask(img, elements: list[dict]) -> np.ndarray:
    """Bangun binary mask gabungan dari semua elemen teks."""
    img_h, img_w = img.shape[:2]
    full = np.zeros((img_h, img_w), dtype=np.uint8)
    for el in elements:
        pad_x = max(4, safe_int(el['h'] * 0.25))
        pad_y = max(3, safe_int(el['h'] * 0.18))
        x1, y1, x2, y2 = expand_box(el, img_w, img_h, pad_x=pad_x, pad_y=pad_y)
        crop  = img[y1:y2, x1:x2]
        local = text_mask_from_crop(crop)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (max(2, safe_int(el['h'] * 0.08)), 2),
        )
        local = cv2.dilate(local, kernel, iterations=1)
        full[y1:y2, x1:x2] = cv2.bitwise_or(full[y1:y2, x1:x2], local)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.morphologyEx(full, cv2.MORPH_CLOSE, kernel, iterations=1)


def inpaint_background(img, mask: np.ndarray):
    """Hapus teks dari gambar menggunakan inpainting TELEA."""
    if mask.sum() == 0:
        return img.copy()
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)


# =============================================================================
# PEMBUATAN HTML
# =============================================================================

def rel_path(p, base: Path) -> str:
    return os.path.relpath(p, start=base.parent).replace('\\', '/')


def generate_html(
    elements: list[dict],
    img_w: int,
    img_h: int,
    bg_img: Path,
    html_path: Path,
    title: str,
) -> None:
    """Hasilkan file HTML interaktif dengan CSS cover dan toolbar edit."""
    bg_rel = rel_path(bg_img, html_path)

    # Bangun item HTML untuk setiap elemen teks
    html_items = []
    for i, el in enumerate(elements):
        x, y, w, h = el['x'], el['y'], el['w'], el['h']
        fs    = el['font_size']
        pad_x = max(3, safe_int(fs * 0.14))
        pad_y = max(2, safe_int(fs * 0.10))

        cover_x = x - pad_x
        cover_y = y - pad_y
        cover_w = w + pad_x * 2
        cover_h = max(h + pad_y * 2, safe_int(fs * LINE_HEIGHT + pad_y * 2))

        text_w = max(w + pad_x * 2, safe_int(len(el['text']) * fs * 0.48))
        text_w = min(text_w, img_w - max(0, cover_x))

        safe_text = html.escape(el['text'])
        html_items.append(
            f'<div class="cover" style="left:{cover_x}px;top:{cover_y}px;'
            f'width:{cover_w}px;height:{cover_h}px;background:{el["cover_color"]};"></div>\n'
            f'<div class="text-el" contenteditable="true" spellcheck="false" data-index="{i}"\n'
            f'     style="left:{x}px;top:{y}px;width:{text_w}px;min-height:{cover_h}px;\n'
            f'            font-size:{fs}px;line-height:{LINE_HEIGHT};font-weight:{el["font_weight"]};\n'
            f'            color:{el["color"]};text-align:{el["align"]};">{safe_text}</div>'
        )

    metadata = json.dumps(elements, indent=2, ensure_ascii=False, cls=NumpyEncoder)

    doc = f'''<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - Layout Aware Extraction</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ margin: 0; padding: 24px 24px 60px; background: #eef2f7; font-family: {FONT_FAMILY}; }}

/* ── Toolbar floating (Word-style popup) ── */
#toolbar {{
  position: absolute;
  display: none;
  z-index: 9999;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  width: max-content;
  max-width: 95vw;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 10px;
  padding: 14px 20px;
  box-shadow: 0 8px 24px rgba(0,0,0,.2);
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 44px;
  color: #212529;
  user-select: none;
}}

/* Font family selector */
#tb-font {{
  width: 180px;
  height: 44px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  background: white;
  font-size: 44px;
  padding: 0 12px;
  cursor: pointer;
}}

/* Font size group (minus, input, plus) */
.tb-size-group {{
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid #ced4da;
  border-radius: 6px;
  overflow: hidden;
  background: white;
  height: 60px;
}}
.tb-size-group button {{
  width: 80px;
  height: 84px;
  border: none;
  background: #f1f3f5;
  cursor: pointer;
  font-size: 40px;
  font-weight: 600;
  line-height: 1;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #495057;
  flex-shrink: 0;
}}
.tb-size-group button:hover {{ background: #dee2e6; }}
#tb-fsize {{
  width: 80px;
  height: 84px;
  border: none;
  border-left: 1px solid #ced4da;
  border-right: 1px solid #ced4da;
  text-align: center;
  font-size: 44px;
  padding: 0;
  outline: none;
  background: white;
}}

/* Separator */
.tb-sep {{
  width: 1.5px;
  height: 84px;
  background: #cbd5e1;
  margin: 0 12px;
  flex-shrink: 0;
}}

/* Format buttons (Bold / Italic / Underline / Strikethrough) */
.tb-btn {{
  width: 100px;
  height: 100px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  color: #212529;
  flex-shrink: 0;
  transition: background .12s, border-color .12s;
}}
.tb-btn:hover  {{ background: #e9ecef; border-color: #ced4da; }}
.tb-btn.active {{ background: #d0ebff; border-color: #74c0fc; color: #1971c2; }}

/* Align buttons */
.tb-align {{
  width: 100px;
  height: 100px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background .12s;
}}
.tb-align:hover  {{ background: #e9ecef; border-color: #ced4da; }}
.tb-align.active {{ background: #d0ebff; border-color: #74c0fc; }}

/* Text color picker */
.tb-color-wrap {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  position: relative;
}}
.tb-color-wrap span {{ font-size: 30px; font-weight: bold; line-height: 1; }}
.tb-color-bar {{
  width: 32px;
  height: 8px;
  border-radius: 2px;
  pointer-events: none;
}}
input[type="color"].tb-color-input {{
  position: absolute;
  opacity: 0;
  width: 40px;
  height: 40px;
  border: none;
  padding: 0;
  cursor: pointer;
  top: 0;
  left: 0;
}}

/* ── Slide canvas ── */
.slide {{
  position: relative;
  width: {img_w}px;
  height: {img_h}px;
  margin: 0 auto;
  overflow: hidden;
  background: url('{bg_rel}') 0 0 / {img_w}px {img_h}px no-repeat;
  box-shadow: 0 14px 45px rgba(15,23,42,.18);
}}
.cover {{
  position: absolute;
  pointer-events: none;
  border-radius: 4px;
  z-index: 1;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}}
.text-el {{
  position: absolute;
  z-index: 2;
  margin: 0;
  padding: 0;
  border: 1px solid transparent;
  outline: none;
  white-space: pre-wrap;
  overflow: visible;
  font-family: {FONT_FAMILY};
  letter-spacing: .015em;
  text-rendering: geometricPrecision;
  -webkit-font-smoothing: antialiased;
  cursor: text;
  border-radius: 2px;
  transition: border-color .1s;
}}
.text-el:hover          {{ border-color: rgba(37,99,235,.40); }}
.text-el:focus,
.text-el.selected       {{ border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,.18); outline: none; }}

/* JSON metadata (tersembunyi secara default) */
#meta {{
  width: {img_w}px;
  max-width: 100%;
  margin: 16px auto 0;
  white-space: pre-wrap;
  font-size: 14px;
  color: #475569;
  display: none;
}}
</style>
</head>
<body>

<div id="toolbar">

  <select id="tb-font" title="Font" onchange="applyFont(this.value)">
    <option value="Inter">Inter</option>
    <option value="Arial">Arial</option>
    <option value="Georgia">Georgia</option>
    <option value="Trebuchet MS">Trebuchet MS</option>
    <option value="Courier New">Courier New</option>
    <option value="Poppins">Poppins</option>
    <option value="Montserrat">Montserrat</option>
  </select>

  <div class="tb-size-group">
    <button title="Perkecil font" onclick="changeFontSize(-1)">&#8722;</button>
    <input id="tb-fsize" type="number" value="14" min="6" max="250"
           title="Ukuran font" onchange="applyFontSizeDirect(this.value)" />
    <button title="Perbesar font" onclick="changeFontSize(+1)">+</button>
  </div>

  <div class="tb-sep"></div>

  <button class="tb-btn" id="btn-bold"      title="Bold (Ctrl+B)"   onclick="execFmt('bold')"><b>B</b></button>
  <button class="tb-btn" id="btn-italic"    title="Italic (Ctrl+I)" onclick="execFmt('italic')"><i>I</i></button>
  <button class="tb-btn" id="btn-underline" title="Underline (Ctrl+U)" onclick="execFmt('underline')"><u>U</u></button>
  <button class="tb-btn" id="btn-strike"    title="Strikethrough"   onclick="execFmt('strikeThrough')"><s>S</s></button>

  <div class="tb-sep"></div>

  <div class="tb-color-wrap" title="Warna Teks">
    <span style="color:#212529;">A</span>
    <div class="tb-color-bar" id="txt-color-bar" style="background:#000000;"></div>
    <input type="color" class="tb-color-input" id="txt-color"
           value="#000000" oninput="applyTextColor(this.value)">
  </div>

  <div class="tb-sep"></div>

  <button class="tb-align" id="btn-left"    title="Rata Kiri"       onclick="applyAlign('left')">
    <svg width="35" height="35" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="2"  width="14" height="2" rx="1"/>
      <rect x="1" y="6"  width="9"  height="2" rx="1"/>
      <rect x="1" y="10" width="14" height="2" rx="1"/>
      <rect x="1" y="14" width="7"  height="2" rx="1"/>
    </svg>
  </button>
  <button class="tb-align active" id="btn-center" title="Tengah"    onclick="applyAlign('center')">
    <svg width="35" height="35" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1"   y="2"  width="14" height="2" rx="1"/>
      <rect x="3.5" y="6"  width="9"  height="2" rx="1"/>
      <rect x="1"   y="10" width="14" height="2" rx="1"/>
      <rect x="4.5" y="14" width="7"  height="2" rx="1"/>
    </svg>
  </button>
  <button class="tb-align" id="btn-right"   title="Rata Kanan"      onclick="applyAlign('right')">
    <svg width="35" height="35" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="2"  width="14" height="2" rx="1"/>
      <rect x="6" y="6"  width="9"  height="2" rx="1"/>
      <rect x="1" y="10" width="14" height="2" rx="1"/>
      <rect x="8" y="14" width="7"  height="2" rx="1"/>
    </svg>
  </button>
  <button class="tb-align" id="btn-justify" title="Rata Kiri-Kanan" onclick="applyAlign('justify')">
    <svg width="35" height="35" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="2"  width="14" height="2" rx="1"/>
      <rect x="1" y="6"  width="14" height="2" rx="1"/>
      <rect x="1" y="10" width="14" height="2" rx="1"/>
      <rect x="1" y="14" width="14" height="2" rx="1"/>
    </svg>
  </button>

</div>

<div class="slide">
{chr(10).join(html_items)}
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let selectedEl = null;
const toolbar  = document.getElementById('toolbar');

// ── Posisi popup toolbar di atas/bawah elemen aktif ───────────────────────
function positionToolbar(el) {{
  toolbar.style.display = 'flex';
  const rect   = el.getBoundingClientRect();
  const tbRect = toolbar.getBoundingClientRect();

  let top  = rect.top  + window.scrollY - tbRect.height - 15;
  let left = rect.left + window.scrollX;

  // Fallback ke bawah jika mentok atas
  if (top < window.scrollY + 10) top = rect.bottom + window.scrollY + 15;
  // Jaga agar tidak melewati tepi kanan
  if (left + tbRect.width > window.innerWidth + window.scrollX - 10)
    left = window.innerWidth + window.scrollX - tbRect.width - 10;
  if (left < 10) left = 10;

  toolbar.style.top  = top  + 'px';
  toolbar.style.left = left + 'px';
}}

// ── Seleksi elemen saat diklik ─────────────────────────────────────────────
document.querySelectorAll('.text-el').forEach(el => {{
  el.addEventListener('mousedown', function(e) {{
    if (selectedEl && selectedEl !== this) selectedEl.classList.remove('selected');
    selectedEl = this;
    this.classList.add('selected');
    positionToolbar(this);
    syncToolbar();
  }});
  el.addEventListener('keyup',    syncToolbar);
  el.addEventListener('mouseup',  syncToolbar);
}});

// ── Sembunyikan toolbar saat klik di luar ─────────────────────────────────
document.addEventListener('mousedown', function(e) {{
  if (!e.target.closest('.text-el') && !e.target.closest('#toolbar')) {{
    if (selectedEl) {{ selectedEl.classList.remove('selected'); selectedEl = null; }}
    toolbar.style.display = 'none';
    clearToolbarActive();
  }}
}});

// ── Sinkronisasi toolbar dengan state elemen aktif ────────────────────────
function syncToolbar() {{
  if (!selectedEl) return;

  const fs = parseFloat(selectedEl.style.fontSize) || 14;
  document.getElementById('tb-fsize').value = Math.round(fs);

  document.getElementById('btn-bold').classList.toggle('active',      document.queryCommandState('bold'));
  document.getElementById('btn-italic').classList.toggle('active',    document.queryCommandState('italic'));
  document.getElementById('btn-underline').classList.toggle('active', document.queryCommandState('underline'));
  document.getElementById('btn-strike').classList.toggle('active',    document.queryCommandState('strikeThrough'));

  const col = rgbToHex(window.getComputedStyle(selectedEl).color) || '#000000';
  document.getElementById('txt-color').value = col;
  document.getElementById('txt-color-bar').style.background = col;

  const align = selectedEl.style.textAlign || 'center';
  ['left', 'center', 'right', 'justify'].forEach(a =>
    document.getElementById('btn-' + a).classList.toggle('active', a === align)
  );
}}

function clearToolbarActive() {{
  ['btn-bold', 'btn-italic', 'btn-underline', 'btn-strike'].forEach(id =>
    document.getElementById(id).classList.remove('active'));
  ['btn-left', 'btn-center', 'btn-right', 'btn-justify'].forEach(id =>
    document.getElementById(id).classList.remove('active'));
}}

// ── Format teks (bold / italic / underline / strikethrough) ───────────────
function execFmt(cmd) {{
  if (!selectedEl) return;
  selectedEl.focus();
  if (!window.getSelection().toString()) {{
    const range = document.createRange();
    range.selectNodeContents(selectedEl);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  }}
  document.execCommand(cmd, false, null);
  syncToolbar();
}}

// ── Ukuran font ────────────────────────────────────────────────────────────
function changeFontSize(delta) {{
  if (!selectedEl) return;
  const next = Math.max(6, Math.min(250, (parseFloat(selectedEl.style.fontSize) || 14) + delta));
  selectedEl.style.fontSize = next + 'px';
  document.getElementById('tb-fsize').value = next;
}}

function applyFontSizeDirect(val) {{
  if (!selectedEl) return;
  const v = Math.max(6, Math.min(250, parseInt(val) || 14));
  selectedEl.style.fontSize = v + 'px';
  document.getElementById('tb-fsize').value = v;
}}

// ── Font family ────────────────────────────────────────────────────────────
function applyFont(family) {{
  if (!selectedEl) return;
  selectedEl.style.fontFamily = family;
}}

// ── Warna teks ────────────────────────────────────────────────────────────
function applyTextColor(val) {{
  if (!selectedEl) return;
  selectedEl.style.color = val;
  document.getElementById('txt-color-bar').style.background = val;
}}

// ── Alignment ─────────────────────────────────────────────────────────────
function applyAlign(align) {{
  if (!selectedEl) return;
  selectedEl.style.textAlign = align;
  ['left', 'center', 'right', 'justify'].forEach(a =>
    document.getElementById('btn-' + a).classList.toggle('active', a === align)
  );
}}

// ── Helper: "rgb(r,g,b)" → "#rrggbb" ──────────────────────────────────────
function rgbToHex(rgb) {{
  if (!rgb || rgb === 'transparent') return '#000000';
  if (rgb.startsWith('#')) return rgb;
  const m = rgb.match(/\\d+/g);
  if (!m || m.length < 3) return '#000000';
  return '#' + m.slice(0, 3).map(n => parseInt(n).toString(16).padStart(2, '0')).join('');
}}

// ── Keyboard shortcuts ────────────────────────────────────────────────────
document.addEventListener('keydown', function(e) {{
  if (!selectedEl) return;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key === 'b') {{ e.preventDefault(); execFmt('bold'); }}
  if (ctrl && e.key === 'i') {{ e.preventDefault(); execFmt('italic'); }}
  if (ctrl && e.key === 'u') {{ e.preventDefault(); execFmt('underline'); }}
}});
</script>
</body>
</html>'''

    html_path.write_text(doc, encoding='utf-8')


# =============================================================================
# DEBUG & OUTPUT
# =============================================================================

def save_debug(img, elements: list[dict], path: Path) -> None:
    """Simpan gambar debug dengan bounding box setiap elemen teks."""
    dbg = img.copy()
    for el in elements:
        x, y, w, h = el['x'], el['y'], el['w'], el['h']
        cv2.rectangle(dbg, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(
            dbg, el['text'][:28], (x, max(0, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA,
        )
    cv2.imwrite(str(path), dbg)


# =============================================================================
# PIPELINE UTAMA
# =============================================================================

def process_image(
    path: Path,
    out_dir: Path,
    engine: str,
    debug: bool,
    cover_mode: str,
) -> dict:
    """Jalankan pipeline ekstraksi teks layout-aware pada satu gambar."""
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f'Tidak bisa membaca: {path}')

    img_h, img_w = img.shape[:2]
    stem    = path.stem
    tmp_dir = out_dir / '_tmp'
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f'\n=== {path.name} ({img_w}x{img_h}) ===')

    raw      = run_ocr(img, tmp_dir, stem, engine)
    print(f'[1] Raw OCR     : {len(raw)} elemen')

    filtered = filter_noise(img, raw)
    print(f'[2] Setelah filter: {len(filtered)} elemen')

    merged   = merge_same_line(filtered, img_w)
    print(f'[3] Setelah merge : {len(merged)} elemen')

    elements = enrich_style(img, merged)
    print('[4] Style selesai')

    # Simpan latar belakang
    bg_path = out_dir / f'{stem}_background.png'
    if cover_mode == 'inpaint':
        mask  = build_mask(img, elements)
        clean = inpaint_background(img, mask)
        cv2.imwrite(str(bg_path), clean)
    else:
        cv2.imwrite(str(bg_path), img)
        mask = build_mask(img, elements)

    # Simpan output HTML dan JSON
    html_path = out_dir / f'{stem}_css_cover.html'
    json_path = out_dir / f'{stem}_data.json'

    generate_html(elements, img_w, img_h, bg_path, html_path, stem)
    json_path.write_text(
        json.dumps(
            {'image': path.name, 'width': img_w, 'height': img_h, 'elements': elements},
            indent=2, ensure_ascii=False, cls=NumpyEncoder,
        ),
        encoding='utf-8',
    )

    result = {
        'html':       str(html_path),
        'json':       str(json_path),
        'background': str(bg_path),
    }

    if debug:
        debug_path = out_dir / f'{stem}_debug.png'
        mask_path  = out_dir / f'{stem}_mask.png'
        save_debug(img, elements, debug_path)
        cv2.imwrite(str(mask_path), mask)
        result.update({'debug': str(debug_path), 'mask': str(mask_path)})

    print(f'[5] Selesai → {html_path}')
    return result


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Layout Aware Text Extraction — CSS Cover + OCR Correction',
    )
    parser.add_argument('--input',        default='./input',  help='Path gambar atau folder input')
    parser.add_argument('--output',       default='./output', help='Folder output')
    parser.add_argument('--engine',       choices=['paddle', 'easyocr'], default='paddle')
    parser.add_argument('--debug',        action='store_true', help='Simpan gambar debug')
    parser.add_argument('--clean-output', action='store_true', help='Bersihkan folder output sebelum dijalankan')
    parser.add_argument('--cover-mode',   choices=['css', 'inpaint'], default='css')
    args = parser.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)

    if args.clean_output and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if in_path.is_file():
        images = [in_path]
    else:
        exts   = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
        images = sorted(p for p in in_path.iterdir() if p.suffix.lower() in exts)

    if not images:
        print(f'Tidak ada gambar di {in_path}')
        return

    results = []
    for p in images:
        try:
            results.append(process_image(p, out_dir, args.engine, args.debug, args.cover_mode))
        except Exception as e:
            print(f'ERROR {p.name}: {e}')
            import traceback
            traceback.print_exc()

    (out_dir / 'results.json').write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f'\nSelesai. Output: {out_dir.resolve()}')


if __name__ == '__main__':
    main()