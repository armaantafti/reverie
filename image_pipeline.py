import os
import re
import shutil
import uuid
import base64
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional, Tuple
from urllib.parse import quote, unquote, urlparse
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageOps, ImageFilter, ImageStat, UnidentifiedImageError
import pytesseract

from note_core import build_document_note_update, build_image_note_update
from supabase_client import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL, supabase_admin

IMAGE_BUCKET = os.getenv("SUPABASE_IMAGE_BUCKET", "memory-images").strip() or "memory-images"
MAX_FILE_UPLOADS_PER_REQUEST = 10
MAX_FILE_MEMORIES_PER_USER = 20
MAX_IMAGE_UPLOADS_PER_REQUEST = MAX_FILE_UPLOADS_PER_REQUEST
MAX_IMAGE_MEMORIES_PER_USER = MAX_FILE_MEMORIES_PER_USER
MAX_IMAGE_FILE_SIZE_BYTES = int(os.getenv("MAX_IMAGE_FILE_SIZE_BYTES", str(8 * 1024 * 1024)))
MAX_DOCUMENT_FILE_SIZE_BYTES = int(os.getenv("MAX_DOCUMENT_FILE_SIZE_BYTES", str(12 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(36_000_000)))
MAX_IMAGE_WIDTH = int(os.getenv("MAX_IMAGE_WIDTH", "6000"))
MAX_IMAGE_HEIGHT = int(os.getenv("MAX_IMAGE_HEIGHT", "6000"))
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/rtf",
    "text/rtf",
    "application/vnd.oasis.opendocument.text",
}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"}
TESSERACT_CMD = (os.getenv("TESSERACT_CMD") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_VISION_MODEL = (os.getenv("OPENAI_VISION_MODEL") or "gpt-4o-mini").strip()

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

if not TESSERACT_CMD:
    TESSERACT_CMD = shutil.which("tesseract") or ""
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
else:
    print("OCR warning: tesseract executable was not found on PATH. Install tesseract-ocr or set TESSERACT_CMD.")


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "image").strip())
    cleaned = cleaned.strip(".-") or "image"
    return cleaned[:80]


def _now_ist_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()


def validate_image_upload(file_name: str, content_type: str, image_bytes: bytes) -> str:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    extension = os.path.splitext(file_name or "")[1].lower()

    if normalized_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValueError("only JPG, PNG, and WEBP images are supported")
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("image file must end in .jpg, .jpeg, .png, or .webp")
    if not image_bytes:
        raise ValueError("one of the uploaded images was empty")
    if len(image_bytes) > MAX_IMAGE_FILE_SIZE_BYTES:
        max_mb = MAX_IMAGE_FILE_SIZE_BYTES // (1024 * 1024)
        raise ValueError(f"image uploads must be {max_mb} MB or smaller")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            detected_type = Image.MIME.get(image.format or "", "")
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise ValueError("uploaded file is not a valid supported image") from exc

    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        raise ValueError(f"image dimensions must be at most {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}")
    if detected_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValueError("uploaded file is not a valid JPG, PNG, or WEBP image")

    return detected_type


def validate_uploaded_file(file_name: str, content_type: str, file_bytes: bytes) -> Tuple[str, str]:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    extension = os.path.splitext(file_name or "")[1].lower()

    if normalized_type in ALLOWED_IMAGE_CONTENT_TYPES or extension in ALLOWED_IMAGE_EXTENSIONS:
        return "image", validate_image_upload(file_name, content_type, file_bytes)

    if normalized_type not in ALLOWED_DOCUMENT_CONTENT_TYPES and extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValueError("supported uploads are images, PDF, Word documents, text files, and common document formats")
    if not file_bytes:
        raise ValueError("one of the uploaded files was empty")
    if len(file_bytes) > MAX_DOCUMENT_FILE_SIZE_BYTES:
        max_mb = MAX_DOCUMENT_FILE_SIZE_BYTES // (1024 * 1024)
        raise ValueError(f"document uploads must be {max_mb} MB or smaller")

    return "document", normalized_type or "application/octet-stream"


def count_uploaded_memories(user_id: str) -> int:
    result = (
        supabase_admin.table("notes")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data or []
    total = 0
    for row in rows:
        memory_type = str(row.get("memory_type") or "").strip().lower()
        if memory_type in {"image", "document"} or row.get("image_url"):
            total += 1
    return total


def count_image_memories(user_id: str) -> int:
    return count_uploaded_memories(user_id)


def upload_file_bytes(user_id: str, file_name: str, file_bytes: bytes, content_type: str) -> str:
    safe_name = _sanitize_filename(file_name)
    object_path = f"{user_id}/{uuid.uuid4().hex}-{safe_name}"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{IMAGE_BUCKET}/{quote(object_path, safe='/')}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type or "application/octet-stream",
        "x-upsert": "false",
    }
    resp = requests.post(upload_url, headers=headers, data=file_bytes, timeout=30)
    resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{IMAGE_BUCKET}/{quote(object_path, safe='/')}"


def upload_image_bytes(user_id: str, file_name: str, image_bytes: bytes, content_type: str) -> str:
    return upload_file_bytes(user_id, file_name, image_bytes, content_type)


def delete_uploaded_file_url(file_url: str) -> bool:
    url = str(file_url or "").strip()
    if not url:
        return False

    parsed = urlparse(url)
    marker = f"/storage/v1/object/public/{IMAGE_BUCKET}/"
    if marker not in parsed.path:
        return False

    object_path = unquote(parsed.path.split(marker, 1)[1] or "").strip("/")
    if not object_path:
        return False

    delete_url = f"{SUPABASE_URL}/storage/v1/object/{IMAGE_BUCKET}/{quote(object_path, safe='/')}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }
    resp = requests.delete(delete_url, headers=headers, timeout=20)
    if resp.status_code in {200, 204, 404}:
        return resp.status_code != 404
    resp.raise_for_status()
    return True


def create_uploaded_note_placeholder(user_id: str, file_url: str, file_name: str, memory_type: str) -> Dict[str, object]:
    base_name = os.path.splitext(file_name or "")[0].replace("-", " ").replace("_", " ").strip()
    title = base_name[:60] if base_name else ("Screenshot memory" if memory_type == "image" else "Document memory")
    summary = "Screenshot uploaded. OCR is processing in the background." if memory_type == "image" else "Document uploaded. Preview is processing in the background."
    note = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "created_at": _now_ist_iso(),
        "person_name": None,
        "title": title or ("Screenshot memory" if memory_type == "image" else "Document memory"),
        "summary": summary,
        "raw_text": "",
        "extracted_text": "",
        "image_url": file_url,
        "memory_type": memory_type,
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


def create_image_note_placeholder(user_id: str, image_url: str, file_name: str) -> Dict[str, object]:
    return create_uploaded_note_placeholder(user_id, image_url, file_name, "image")


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
    if width < 1800:
        scale = 1800 / max(width, 1)
        base = base.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    base = base.filter(ImageFilter.SHARPEN)
    variants.append(base)

    variants.append(base.point(lambda p: 255 if p > 165 else 0))

    # Only add an inverted fallback for darker screenshots.
    # This keeps OCR fast for normal screenshots while still helping dark mode.
    if _estimate_brightness(base) < 135:
        inverted = ImageOps.invert(base)
        inverted = inverted.filter(ImageFilter.SHARPEN)
        variants.append(inverted)

    return variants


def _run_ocr(image_bytes: bytes) -> str:
    if not TESSERACT_CMD:
        print("OCR warning: skipping Tesseract because the executable is missing")
        return ""

    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)

    variants = _prepare_ocr_variants(image)
    best = ""

    configs = (
        "--oem 1 --psm 6",
        "--oem 1 --psm 4",
        "--oem 1 --psm 11",
        "--oem 1 --psm 12",
    )
    for config in configs:
        for variant in variants:
            try:
                text = pytesseract.image_to_string(variant, config=config, timeout=12) or ""
            except Exception as exc:
                print(f"OCR variant failed with {config}: {exc}")
                text = ""
            if len(text.strip()) > len(best.strip()):
                best = text

    return best or ""


def _run_openai_vision_ocr(image_bytes: bytes, content_type: str = "image/png") -> str:
    if not OPENAI_API_KEY:
        return ""

    mime = content_type if content_type.startswith("image/") else "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": OPENAI_VISION_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You transcribe text from screenshots. Return only the visible text, preserving useful line breaks. Do not summarize.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe all readable text in this screenshot. Include chat messages, dates, times, and names if visible.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{encoded}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": 1000,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=35,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        print(f"OpenAI vision OCR failed: {exc}")
        return ""


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


def clean_document_text(text: str) -> str:
    raw = (text or "").replace("\r", "\n").replace("\u00a0", " ")
    raw = re.sub(r"[ \t]+", " ", raw)

    lines = []
    seen = set()
    for line in raw.split("\n"):
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(cleaned)

    merged = "\n".join(lines)
    merged = re.sub(r"\n{3,}", "\n\n", merged).strip()
    return merged


def _extract_pdf_preview_text(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(BytesIO(file_bytes))
    except Exception as exc:
        print(f"PDF preview extraction failed: {exc}")
        return ""

    chunks = []
    for page in reader.pages[:2]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception as exc:
            print(f"PDF page extraction failed: {exc}")
    return "\n\n".join(chunks)


def _extract_docx_preview_text(file_bytes: bytes) -> str:
    try:
        from docx import Document
    except Exception:
        return ""

    try:
        doc = Document(BytesIO(file_bytes))
    except Exception as exc:
        print(f"DOCX preview extraction failed: {exc}")
        return ""

    parts = []
    for para in doc.paragraphs:
        text = str(para.text or "").strip()
        if text:
            parts.append(text)
        if sum(len(part) for part in parts) >= 6000:
            break
    return "\n\n".join(parts)


def _extract_text_preview(file_name: str, content_type: str, file_bytes: bytes) -> str:
    extension = os.path.splitext(file_name or "")[1].lower()
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()

    if extension == ".pdf" or normalized_type == "application/pdf":
        return _extract_pdf_preview_text(file_bytes)
    if extension == ".docx" or normalized_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx_preview_text(file_bytes)
    if extension in {".txt", ".md"} or normalized_type in {"text/plain", "text/markdown"}:
        try:
            return file_bytes.decode("utf-8", errors="ignore")[:6000]
        except Exception:
            return ""
    return ""


def process_uploaded_note(
    note_id: str,
    user_id: str,
    file_url: str,
    file_name: str,
    file_bytes: bytes,
    content_type: str,
    memory_type: str,
) -> None:
    try:
        if memory_type == "image":
            extracted = _run_ocr(file_bytes)
            if len(clean_ocr_text(extracted)) < 20:
                fallback = _run_openai_vision_ocr(file_bytes, content_type)
                if len(clean_ocr_text(fallback)) > len(clean_ocr_text(extracted)):
                    extracted = fallback
            cleaned = clean_ocr_text(extracted)
            update = build_image_note_update(cleaned, file_url, user_id)
        else:
            extracted = _extract_text_preview(file_name, content_type, file_bytes)
            cleaned = clean_document_text(extracted)
            update = build_document_note_update(cleaned, file_url, file_name, user_id)
    except Exception as exc:
        print(f"upload pipeline failed for {note_id}: {exc}")
        update = build_image_note_update("", file_url, user_id) if memory_type == "image" else build_document_note_update("", file_url, file_name, user_id)

    try:
        (
            supabase_admin.table("notes")
            .update(update)
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        print(f"uploaded note update failed for {note_id}: {exc}")


def process_uploaded_image_note(note_id: str, user_id: str, image_url: str, image_bytes: bytes, content_type: str = "image/png") -> None:
    process_uploaded_note(note_id, user_id, image_url, "screenshot.png", image_bytes, content_type, "image")
