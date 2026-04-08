import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional
from urllib.parse import quote

import requests
from PIL import Image, ImageOps, ImageFilter, ImageStat
import pytesseract

from note_core import build_image_note_update
from supabase_client import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL, supabase_admin

IMAGE_BUCKET = os.getenv("SUPABASE_IMAGE_BUCKET", "memory-images").strip() or "memory-images"
MAX_IMAGE_UPLOADS_PER_REQUEST = 10
MAX_IMAGE_MEMORIES_PER_USER = 20
TESSERACT_CMD = (os.getenv("TESSERACT_CMD") or "").strip()

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "image").strip())
    cleaned = cleaned.strip(".-") or "image"
    return cleaned[:80]


def count_image_memories(user_id: str) -> int:
    result = (
        supabase_admin.table("notes")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data or []
    total = 0
    for row in rows:
        if str(row.get("memory_type") or "").strip().lower() == "image" or row.get("image_url"):
            total += 1
    return total


def upload_image_bytes(user_id: str, file_name: str, image_bytes: bytes, content_type: str) -> str:
    safe_name = _sanitize_filename(file_name)
    object_path = f"{user_id}/{uuid.uuid4().hex}-{safe_name}"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{IMAGE_BUCKET}/{quote(object_path, safe='/')}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type or "application/octet-stream",
        "x-upsert": "false",
    }
    resp = requests.post(upload_url, headers=headers, data=image_bytes, timeout=30)
    resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{IMAGE_BUCKET}/{quote(object_path, safe='/')}"


def create_image_note_placeholder(user_id: str, image_url: str, file_name: str) -> Dict[str, object]:
    base_name = os.path.splitext(file_name or "")[0].replace("-", " ").replace("_", " ").strip()
    title = base_name[:60] if base_name else "Screenshot memory"
    note = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "person_name": None,
        "title": title or "Screenshot memory",
        "summary": "Screenshot uploaded. OCR is processing in the background.",
        "raw_text": "",
        "extracted_text": "",
        "image_url": image_url,
        "memory_type": "image",
        "note_type": "note",
        "tags": [],
        "entities": [],
        "due_time": None,
        "calendar_event_id": None,
        "status": "pending",
        "status_note": None,
    }
    supabase_admin.table("notes").insert(note).execute()
    return note


def _estimate_brightness(image: Image.Image) -> float:
    return float(ImageStat.Stat(image).mean[0])


def _prepare_ocr_variants(image: Image.Image):
    """
    Build a few OCR-friendly variants without changing the rest of the pipeline.
    This keeps the feature cost-effective while making screenshots much easier for Tesseract.
    """
    variants = []

    # Base grayscale + contrast + sharpen
    base = ImageOps.grayscale(image)
    base = ImageOps.autocontrast(base)
    width, height = base.size
    if width < 1400:
        scale = 1400 / max(width, 1)
        base = base.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    base = base.filter(ImageFilter.SHARPEN)
    variants.append(base)

    # Slightly more aggressive variant for crisp screenshots
    strong = ImageOps.grayscale(image)
    strong = ImageOps.autocontrast(strong)
    width, height = strong.size
    if width < 1600:
        scale = 1600 / max(width, 1)
        strong = strong.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    strong = strong.filter(ImageFilter.SHARPEN)
    strong = strong.filter(ImageFilter.EDGE_ENHANCE_MORE)
    variants.append(strong)

    # Thresholded variant for high-contrast screenshots
    thresh = ImageOps.grayscale(image)
    thresh = ImageOps.autocontrast(thresh)
    width, height = thresh.size
    if width < 1400:
        scale = 1400 / max(width, 1)
        thresh = thresh.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    thresh = thresh.point(lambda p: 255 if p > 170 else 0)
    variants.append(thresh)

    # Inverted variant for dark mode screenshots
    inverted = ImageOps.grayscale(image)
    inverted = ImageOps.autocontrast(inverted)
    width, height = inverted.size
    if width < 1400:
        scale = 1400 / max(width, 1)
        inverted = inverted.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    inverted = ImageOps.invert(inverted)
    inverted = inverted.filter(ImageFilter.SHARPEN)
    variants.append(inverted)

    return variants


def _run_ocr(image_bytes: bytes) -> str:
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)

    # If the screenshot is dark, try an inverted version too.
    # This is kept inside the OCR preprocessing only, so nothing else in the app changes.
    variants = _prepare_ocr_variants(image)

    configs = [
        "--psm 6",
        "--psm 11",
        "--psm 3",
    ]

    results = []
    for variant in variants:
        for config in configs:
            try:
                text = pytesseract.image_to_string(variant, config=config) or ""
                results.append(text)
            except Exception:
                continue

    best = max(results, key=lambda x: len((x or "").strip()), default="")
    return best or ""


def clean_ocr_text(text: str) -> str:
    raw = (text or "").replace("\r", "\n")
    raw = raw.replace("\u00a0", " ")
    raw = re.sub(r"-\n", "", raw)
    raw = re.sub(r"[^\S\n]+", " ", raw)

    lines = []
    seen = set()
    for line in raw.split("\n"):
        cleaned = re.sub(r"[^\w\s.,:;!?@/#&()'\"+-]", " ", line)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(cleaned)

    merged = " ".join(lines)
    merged = re.sub(r"\s+", " ", merged).strip()
    return merged


def process_uploaded_image_note(note_id: str, user_id: str, image_url: str, image_bytes: bytes) -> None:
    try:
        extracted = _run_ocr(image_bytes)
        cleaned = clean_ocr_text(extracted)
        update = build_image_note_update(cleaned, image_url)
    except Exception:
        update = build_image_note_update("", image_url)

    try:
        (
            supabase_admin.table("notes")
            .update(update)
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        pass
