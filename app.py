import os
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional, Any
from urllib.parse import urlencode, quote

from fastapi import FastAPI, Query, Request, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests

from auth_sessions import create_app_session, get_session_user, migrate_legacy_refresh_token, revoke_app_session
from supabase_client import SUPABASE_URL, supabase_admin, supabase_auth
from note_core import (
    process_text_note,
    generate_id,
    canonicalize_note_metadata,
    list_entity_manager_items,
    merge_entity_manager_items,
    rename_entity_manager_item,
    create_entity_manager_item,
    delete_entity_manager_items,
)
from image_pipeline import (
    MAX_FILE_MEMORIES_PER_USER,
    MAX_FILE_UPLOADS_PER_REQUEST,
    count_uploaded_memories,
    create_uploaded_note_placeholder,
    process_uploaded_note,
    delete_uploaded_file_url,
    upload_file_bytes,
    validate_uploaded_file,
)
from search_notes import filter_notes, rank_for_you, context_notes, rank_smart_search
from llm_search import summarise_search, summarise_search_structured, fallback_structured_summary, extract_search_signals
from tag_config import PREDEFINED_TAGS

app = FastAPI(title="Reverie API")
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

SESSION_COOKIE_NAME = "reverie_app_session"
LEGACY_SESSION_COOKIE_NAME = "reverie_session"
LEGACY_REFRESH_COOKIE_NAME = "reverie_refresh"
GOOGLE_OAUTH_STATE_COOKIE = "reverie_google_oauth_state"
GOOGLE_OAUTH_VERIFIER_COOKIE = "reverie_google_oauth_verifier"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30
OAUTH_COOKIE_MAX_AGE = 10 * 60
MAX_VOICE_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_AUDIO_EXTENSIONS = {".webm", ".m4a", ".mp3", ".wav"}
SUPPORTED_AUDIO_TYPES = {
    "audio/webm",
    "audio/mp4",
    "audio/m4a",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
}


@app.middleware("http")
async def no_cache_html(request: Request, call_next):
    response = await call_next(request)
    migrated_session_id = getattr(request.state, "migrated_app_session_id", None)
    if migrated_session_id:
        _set_session_cookie(response, request, migrated_session_id)
        _clear_legacy_auth_cookies(response, request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class CacheControlStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            query_string = scope.get("query_string", b"").decode("latin-1")
            if "v=" in query_string:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "public, max-age=86400"
        return response


# Static files
app.mount("/static", CacheControlStaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


@app.get("/service-worker.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        "static/service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


def get_user_notes(user_id: str, note_types: Optional[list[str]] = None, limit: Optional[int] = None):
    query = (
        supabase_admin.table("notes")
        .select("*")
        .eq("user_id", user_id)
    )
    clean_types = [item.strip().lower() for item in (note_types or []) if item and item.strip()]
    if clean_types:
        query = query.in_("note_type", clean_types)
    query = query.order("created_at", desc=True)
    if limit:
        query = query.limit(limit)
    result = query.execute()
    return result.data or []


CARD_NOTE_FIELDS = {
    "id",
    "title",
    "summary",
    "note_type",
    "memory_type",
    "person_name",
    "tags",
    "entities",
    "due_time",
    "status",
    "status_note",
    "created_at",
    "updated_at",
    "search_score",
    "match_reasons",
    "search_section",
}


def _card_note(note: dict[str, Any]) -> dict[str, Any]:
    return {key: note.get(key) for key in CARD_NOTE_FIELDS if key in note}


def _card_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_card_note(note) for note in notes]


def get_user_note_detail(user_id: str, note_id: str) -> dict[str, Any]:
    result = (
        supabase_admin.table("notes")
        .select("*")
        .eq("id", note_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="note not found")
    return rows[0]


def _ics_escape(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _ics_fold_line(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: list[str] = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        if current and current_len + char_len > 75:
            chunks.append(current)
            current = " " + char
            current_len = 1 + char_len
        else:
            current += char
            current_len += char_len
    if current:
        chunks.append(current)
    return "\r\n".join(chunks)


def _parse_calendar_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="note does not have a due time")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="note due time is invalid")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _ics_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _calendar_filename(note: dict[str, Any]) -> str:
    title = str(note.get("title") or "reverie-reminder").strip().lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in title).strip("-")
    safe = "-".join(part for part in safe.split("-") if part)[:48] or "reverie-reminder"
    return f"{safe}.ics"


def _build_note_ics(note: dict[str, Any]) -> str:
    note_id = str(note.get("id") or note.get("note_id") or generate_id()).strip()
    start = _parse_calendar_datetime(note.get("due_time"))
    end = start + timedelta(minutes=30)
    title = note.get("title") or "Reverie reminder"
    description_parts = [
        str(note.get("summary") or "").strip(),
        "",
        "Created from Reverie.",
    ]
    if note.get("person_name"):
        description_parts.append(f"Person: {note.get('person_name')}")
    if note.get("tags"):
        description_parts.append(f"Tags: {', '.join(note.get('tags') or [])}")
    if note.get("entities"):
        description_parts.append(f"Entities: {', '.join(note.get('entities') or [])}")

    description = "\n".join(description_parts).strip()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Reverie//Reminder Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:reverie-{note_id}@reverie-i2b8.onrender.com",
        f"DTSTAMP:{_ics_datetime(datetime.now(timezone.utc))}",
        f"DTSTART:{_ics_datetime(start)}",
        f"DTEND:{_ics_datetime(end)}",
        f"SUMMARY:{_ics_escape(title)}",
        f"DESCRIPTION:{_ics_escape(description)}",
        "BEGIN:VALARM",
        "TRIGGER:-PT10M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_escape(title)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_ics_fold_line(line) for line in lines) + "\r\n"


def _parse_note_types(types: Optional[str]) -> list[str]:
    return [item.strip().lower() for item in (types or "").split(",") if item.strip()]


def _template_context(request: Request) -> dict[str, Any]:
    authenticated = False
    try:
        authenticated = bool(_get_authenticated_user(request))
    except Exception:
        authenticated = False
    return {
        "request": request,
        "predefined_tags": list(PREDEFINED_TAGS),
        "authenticated": authenticated,
    }


VALID_NOTE_STATUSES = {"pending", "completed", "skipped"}
VALID_NOTE_TYPES = {"note", "recommendation", "reminder", "passive"}


class NoteStatusIn(BaseModel):
    note_id: str
    status: str
    status_note: Optional[str] = None


class NoteUpdateIn(BaseModel):
    note_id: str
    person_name: Optional[str] = None
    tags: Optional[list[str]] = None
    entities: Optional[list[str]] = None
    note_type: Optional[str] = None
    due_time: Optional[str] = None


class NoteDeleteIn(BaseModel):
    note_id: str


class NoteAssetRemoveIn(BaseModel):
    note_id: str


class EntityManagerMergeIn(BaseModel):
    kind: str
    values: list[str]
    target_value: str


class EntityManagerRenameIn(BaseModel):
    kind: str
    value: str
    new_value: str


class EntityManagerCreateIn(BaseModel):
    kind: str
    value: str


class EntityManagerDeleteIn(BaseModel):
    kind: str
    values: list[str]


def _error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    if getattr(exc, "args", None):
        return str(exc.args[0])
    return "Request failed"


def _clean_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _clean_due_time(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="due_time must be a valid datetime")


def _audio_file_extension(filename: str) -> str:
    lower = str(filename or "").lower()
    for ext in SUPPORTED_AUDIO_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    return ""


def _validate_audio_upload(filename: str, content_type: str, file_bytes: bytes) -> tuple[str, str]:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="audio file is empty")
    if len(file_bytes) > MAX_VOICE_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="voice recording must be 10 MB or smaller")

    ext = _audio_file_extension(filename)
    clean_type = (content_type or "").split(";")[0].strip().lower()
    if clean_type not in SUPPORTED_AUDIO_TYPES and ext not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="upload a webm, m4a, mp3, or wav voice recording")

    upload_name = filename or f"voice{ext or '.webm'}"
    upload_type = clean_type or "application/octet-stream"
    return upload_name, upload_type


def _transcribe_audio_bytes(file_name: str, content_type: str, file_bytes: bytes) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="voice transcription is not configured")

    model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
    try:
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model, "response_format": "json"},
            files={"file": (file_name, BytesIO(file_bytes), content_type)},
            timeout=75,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text[:500])
        payload = response.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"voice transcription failed: {_error_detail(exc)}") from exc

    return str(payload.get("text") or "").strip()


def _cookie_secure(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").lower()
    if "https" in forwarded_proto:
        return True
    return request.url.scheme == "https"


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="none" if _cookie_secure(request) else "lax",
        max_age=SESSION_COOKIE_MAX_AGE,
        path="/",
    )


def _delete_cookie(response: Response, request: Request, name: str) -> None:
    response.delete_cookie(
        key=name,
        path="/",
        samesite="none" if _cookie_secure(request) else "lax",
        secure=_cookie_secure(request),
    )


def _clear_legacy_auth_cookies(response: Response, request: Request) -> None:
    _delete_cookie(response, request, LEGACY_SESSION_COOKIE_NAME)
    _delete_cookie(response, request, LEGACY_REFRESH_COOKIE_NAME)


def _clear_session_cookie(response: JSONResponse, request: Request) -> None:
    _delete_cookie(response, request, SESSION_COOKIE_NAME)
    _clear_legacy_auth_cookies(response, request)


def _set_oauth_cookie(response: Response, request: Request, name: str, value: str) -> None:
    response.set_cookie(
        key=name,
        value=value,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="none" if _cookie_secure(request) else "lax",
        max_age=OAUTH_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_oauth_cookies(response: Response, request: Request) -> None:
    _delete_cookie(response, request, GOOGLE_OAUTH_STATE_COOKIE)
    _delete_cookie(response, request, GOOGLE_OAUTH_VERIFIER_COOKIE)


def _external_origin(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    return f"{proto}://{host}"


def _google_oauth_redirect_to(request: Request, *, state: Optional[str] = None, native: bool = False) -> str:
    url = f"{_external_origin(request).rstrip('/')}/auth/google/callback"
    params: dict[str, str] = {}
    if state:
        params["rv_state"] = state
    if native:
        params["native"] = "1"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _native_auth_intent_url(session_id: str = "", error: str = "") -> str:
    params: dict[str, str] = {}
    if session_id:
        params["session"] = session_id
    if error:
        params["error"] = error
    query = f"?{urlencode(params)}" if params else ""
    fallback_target = "/auth/native/complete"
    if session_id:
        fallback_target = f"{fallback_target}?session={quote(session_id, safe='')}"
    elif error:
        fallback_target = f"/?auth_error={quote(error, safe='')}"
    fallback = f"{os.getenv('REVERIE_PUBLIC_URL', 'https://reverie-i2b8.onrender.com').rstrip('/')}{fallback_target}"
    return (
        f"intent://auth/google{query}"
        "#Intent;"
        "scheme=reverie;"
        "package=com.reverie.myapp;"
        f"S.browser_fallback_url={quote(fallback, safe='')};"
        "end"
    )


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _extract_request_session_id(request: Request) -> str:
    session_id = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if session_id:
        return session_id

    legacy_refresh = (request.cookies.get(LEGACY_REFRESH_COOKIE_NAME) or "").strip()
    if legacy_refresh:
        session_id, _user = migrate_legacy_refresh_token(legacy_refresh)
        request.state.migrated_app_session_id = session_id
        return session_id

    raise HTTPException(status_code=401, detail="missing session cookie")


def _get_authenticated_user_id(request: Request) -> str:
    user = _get_authenticated_user(request)
    return str(user.get("id") or "").strip()


def _get_authenticated_user(request: Request) -> dict[str, Any]:
    session_id = _extract_request_session_id(request)
    return get_session_user(session_id)


def _auth_response_from_payload(request: Request, payload: Any) -> JSONResponse:
    session_id, user = create_app_session(payload)
    response = JSONResponse(content={
        "authenticated": True,
        "user": {"id": user.get("id"), "email": user.get("email")},
    })
    _set_session_cookie(response, request, session_id)
    _clear_legacy_auth_cookies(response, request)
    return response


class AuthIn(BaseModel):
    email: str
    password: str


@app.post("/signup")
async def signup(data: AuthIn, request: Request):
    email = data.email.strip()
    password = data.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    try:
        res = supabase_auth.auth.sign_up({
            "email": email,
            "password": password
        })
        return _auth_response_from_payload(request, res)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e


@app.post("/login")
async def login(data: AuthIn, request: Request):
    email = data.email.strip()
    password = data.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    try:
        res = supabase_auth.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return _auth_response_from_payload(request, res)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e


@app.get("/session")
def get_session(request: Request):
    user = _get_authenticated_user(request)
    response = JSONResponse(content={
        "authenticated": True,
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
        },
    })
    return response


@app.post("/logout")
def logout(request: Request):
    session_id = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if session_id:
        revoke_app_session(session_id)
    response = JSONResponse(content={"ok": True})
    _clear_session_cookie(response, request)
    return response


@app.get("/auth/google/start")
def google_auth_start(request: Request, native: Optional[str] = None):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    is_native = str(native or "").strip().lower() in {"1", "true", "yes"}
    redirect_to = _google_oauth_redirect_to(request, state=state, native=is_native)
    params = {
        "provider": "google",
        "redirect_to": redirect_to,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "s256",
    }
    response = RedirectResponse(
        url=f"{SUPABASE_URL.rstrip('/')}/auth/v1/authorize?{urlencode(params)}",
        status_code=302,
    )
    _set_oauth_cookie(response, request, GOOGLE_OAUTH_STATE_COOKIE, state)
    _set_oauth_cookie(response, request, GOOGLE_OAUTH_VERIFIER_COOKIE, verifier)
    return response


@app.get("/auth/google/callback")
def google_auth_callback(
    request: Request,
    code: Optional[str] = None,
    rv_state: Optional[str] = None,
    native: Optional[str] = None,
    error: Optional[str] = None,
):
    is_native = str(native or "").strip().lower() in {"1", "true", "yes"}
    response = RedirectResponse(url="/?auth=google", status_code=303)
    _clear_oauth_cookies(response, request)

    if error:
        response.headers["location"] = _native_auth_intent_url(error=error) if is_native else f"/?auth_error={error}"
        return response
    saved_state = (request.cookies.get(GOOGLE_OAUTH_STATE_COOKIE) or "").strip()
    verifier = (request.cookies.get(GOOGLE_OAUTH_VERIFIER_COOKIE) or "").strip()
    if not code or not rv_state or not saved_state or not verifier or not secrets.compare_digest(rv_state, saved_state):
        response.headers["location"] = _native_auth_intent_url(error="google_oauth_state") if is_native else "/?auth_error=google_oauth_state"
        return response

    try:
        auth_response = supabase_auth.auth.exchange_code_for_session({
            "auth_code": code,
            "code_verifier": verifier,
            "redirect_to": _google_oauth_redirect_to(request, state=rv_state, native=is_native),
        })
        session_id, _user = create_app_session(auth_response)
        if is_native:
            response.headers["location"] = _native_auth_intent_url(session_id=session_id)
        else:
            _set_session_cookie(response, request, session_id)
            _clear_legacy_auth_cookies(response, request)
        return response
    except Exception as exc:
        print(f"Google OAuth callback failed: {_error_detail(exc)}")
        response.headers["location"] = _native_auth_intent_url(error="google_oauth_failed") if is_native else "/?auth_error=google_oauth_failed"
        return response


@app.get("/auth/native/complete")
def native_auth_complete(request: Request, session: Optional[str] = None, error: Optional[str] = None):
    if error:
        return RedirectResponse(url=f"/?auth_error={error}", status_code=303)
    session_id = (session or "").strip()
    if not session_id:
        return RedirectResponse(url="/?auth_error=native_auth_missing", status_code=303)
    try:
        get_session_user(session_id)
    except Exception:
        return RedirectResponse(url="/?auth_error=native_auth_invalid", status_code=303)
    response = RedirectResponse(url="/?auth=google", status_code=303)
    _set_session_cookie(response, request, session_id)
    _clear_legacy_auth_cookies(response, request)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        _template_context(request)
    )


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse(
        "tasks.html",
        _template_context(request)
    )


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    return templates.TemplateResponse(
        "search.html",
        _template_context(request)
    )


@app.get("/entities", response_class=HTMLResponse)
async def entities_page(request: Request):
    return templates.TemplateResponse(
        "entities.html",
        _template_context(request)
    )


@app.get("/uploads", response_class=HTMLResponse)
async def uploads_page(request: Request):
    return templates.TemplateResponse(
        "uploads.html",
        _template_context(request)
    )


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    return templates.TemplateResponse(
        "account.html",
        _template_context(request)
    )


@app.get("/recommendations", response_class=HTMLResponse)
async def recs_page(request: Request):
    return templates.TemplateResponse(
        "recommendations.html",
        _template_context(request)
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse(
        "privacy.html",
        _template_context(request)
    )


@app.get("/account-deletion", response_class=HTMLResponse)
async def account_deletion_page(request: Request):
    return templates.TemplateResponse(
        "account_deletion.html",
        _template_context(request)
    )


@app.post("/voice/transcribe")
async def transcribe_voice(request: Request, audio: UploadFile = File(...)):
    _get_authenticated_user_id(request)
    file_name = audio.filename or "voice.webm"
    file_bytes = await audio.read(MAX_VOICE_UPLOAD_BYTES + 1)
    upload_name, upload_type = _validate_audio_upload(file_name, audio.content_type or "", file_bytes)
    transcript = _transcribe_audio_bytes(upload_name, upload_type, file_bytes)
    return {
        "transcript": transcript,
        "message": "Transcript added. Review before saving." if transcript else "No speech detected. Try again.",
    }


class TextNoteIn(BaseModel):
    text: str


@app.post("/notes/text")
def create_text_note(payload: TextNoteIn, request: Request):
    try:
        user_id = _get_authenticated_user_id(request)
        note = process_text_note(
            payload.text,
            platform="web",
            message_id=None,
            user_id=user_id,
        )
        return note
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/notes/status")
def update_note_status(payload: NoteStatusIn, request: Request):
    note_id = (payload.note_id or "").strip()
    user_id = _get_authenticated_user_id(request)
    status = (payload.status or "").strip().lower()
    status_note = (payload.status_note or "").strip() or None

    if not note_id:
        raise HTTPException(status_code=400, detail="note_id is required")
    if status not in VALID_NOTE_STATUSES:
        raise HTTPException(status_code=400, detail="status must be pending, completed, or skipped")

    try:
        result = (
            supabase_admin.table("notes")
            .update({
                "status": status,
                "status_note": status_note,
            })
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="note not found")
        return rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.get("/notes")
def list_notes(
    request: Request,
    query: Optional[str] = Query(None, description="Search text in title/summary/person/tags"),
    days: Optional[int] = Query(None, description="Limit to last N days"),
    types: Optional[str] = Query(None, description="Comma-separated note_type filter"),
    limit: Optional[int] = Query(None, ge=1, le=200, description="Maximum notes to return"),
):
    notes = get_user_notes(_get_authenticated_user_id(request), note_types=_parse_note_types(types), limit=limit)
    results = filter_notes(notes, query=query, days=days)
    return _card_notes(results)


@app.get("/notes/{note_id}")
def note_detail(note_id: str, request: Request):
    clean_note_id = (note_id or "").strip()
    if not clean_note_id:
        raise HTTPException(status_code=400, detail="note_id is required")
    return get_user_note_detail(_get_authenticated_user_id(request), clean_note_id)


@app.get("/calendar/notes/{note_id}.ics")
def note_calendar_ics(note_id: str, request: Request):
    clean_note_id = (note_id or "").strip()
    if not clean_note_id:
        raise HTTPException(status_code=400, detail="note_id is required")
    note = get_user_note_detail(_get_authenticated_user_id(request), clean_note_id)
    if not note.get("due_time"):
        raise HTTPException(status_code=400, detail="note does not have a due time")
    ics = _build_note_ics(note)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_calendar_filename(note)}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/for-you")
def for_you(
    request: Request,
    limit: Optional[int] = Query(6, ge=1, le=20),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    ranked = rank_for_you(notes, limit=limit)
    return {"notes": _card_notes(ranked), "count": len(ranked)}


@app.get("/for-you/all")
def for_you_all(request: Request):
    notes = get_user_notes(_get_authenticated_user_id(request))
    ranked = rank_for_you(notes, limit=None)
    return {"notes": _card_notes(ranked), "count": len(ranked)}


@app.get("/context")
def context_view(
    request: Request,
    kind: str = Query(...),
    value: str = Query(...),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    results = context_notes(notes, kind=kind, value=value)
    return {"kind": kind, "value": value, "notes": _card_notes(results), "count": len(results)}


@app.get("/entities/manage")
def entity_manager_list(request: Request):
    user_id = _get_authenticated_user_id(request)
    try:
        items = list_entity_manager_items(user_id)
        return {"items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/entities/manage/merge")
def entity_manager_merge(payload: EntityManagerMergeIn, request: Request):
    user_id = _get_authenticated_user_id(request)
    try:
        item = merge_entity_manager_items(user_id, payload.kind, payload.values, payload.target_value)
        return {"ok": True, "item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/entities/manage/rename")
def entity_manager_rename(payload: EntityManagerRenameIn, request: Request):
    user_id = _get_authenticated_user_id(request)
    try:
        item = rename_entity_manager_item(user_id, payload.kind, payload.value, payload.new_value)
        return {"ok": True, "item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/entities/manage/create")
def entity_manager_create(payload: EntityManagerCreateIn, request: Request):
    user_id = _get_authenticated_user_id(request)
    try:
        item = create_entity_manager_item(user_id, payload.kind, payload.value)
        return {"ok": True, "item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/entities/manage/delete")
def entity_manager_delete(payload: EntityManagerDeleteIn, request: Request):
    user_id = _get_authenticated_user_id(request)
    try:
        result = delete_entity_manager_items(user_id, payload.kind, payload.values)
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


class SmartSearchIn(BaseModel):
    query: str
    days: Optional[int] = None


class ContextSummaryIn(BaseModel):
    kind: str
    value: str


@app.post("/context-summary")
def context_summary(payload: ContextSummaryIn, request: Request):
    try:
        kind = (payload.kind or "").strip()
        value = (payload.value or "").strip()
        if not kind or not value:
            raise HTTPException(status_code=400, detail="kind and value are required")
        notes = get_user_notes(_get_authenticated_user_id(request))
        results = context_notes(notes, kind=kind, value=value)
        label = f"{kind}: {value}"
        try:
            summary = summarise_search(f"Summarise everything filed under {label}", results)
        except Exception:
            summary = "Smart summary could not be generated for this group."
        return {"kind": kind, "value": value, "summary": summary, "notes": _card_notes(results), "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/smart-search")
def smart_search(payload: SmartSearchIn, request: Request):
    try:
        notes = get_user_notes(_get_authenticated_user_id(request))
        signals = extract_search_signals(payload.query)
        keywords = list(signals.get("keywords") or [])[:5]
        matched_tag = signals.get("best_matching_tag")

        search_terms = list(keywords)
        if isinstance(matched_tag, str) and matched_tag and matched_tag not in search_terms:
            search_terms.append(matched_tag)

        if not search_terms:
            summary_json = fallback_structured_summary(payload.query, [])
            return {
                "summary": summary_json["executive_summary"],
                "summary_json": summary_json,
                "notes": [],
                "signals": signals,
                "count": 0,
            }

        ranked = rank_smart_search(
            notes,
            query=payload.query,
            keywords=keywords,
            matched_tag=matched_tag if isinstance(matched_tag, str) else None,
            days=payload.days,
            min_score=4,
            limit=50,
        )
        try:
            summary_json = summarise_search_structured(payload.query, ranked[:20])
        except Exception:
            summary_json = fallback_structured_summary(payload.query, ranked[:20])
        summary = summary_json.get("executive_summary") or "Smart search completed."
        return {
            "summary": summary,
            "summary_json": summary_json,
            "notes": _card_notes(ranked),
            "signals": signals,
            "count": len(ranked),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/notes/update")
def update_note(payload: NoteUpdateIn, request: Request):
    note_id = (payload.note_id or "").strip()
    user_id = _get_authenticated_user_id(request)

    if not note_id:
        raise HTTPException(status_code=400, detail="note_id is required")

    note_type = _clean_text(payload.note_type)
    if note_type is not None:
        note_type = note_type.lower()
        if note_type not in VALID_NOTE_TYPES:
            raise HTTPException(status_code=400, detail="note_type must be note, recommendation, reminder, or passive")

    updates = {
        "person_name": _clean_text(payload.person_name),
        "tags": _clean_list(payload.tags),
        "entities": _clean_list(payload.entities),
        "due_time": _clean_due_time(payload.due_time),
    }
    canonicalized = canonicalize_note_metadata(
        user_id,
        person_name=updates["person_name"],
        tags=updates["tags"],
        entities=updates["entities"],
    )
    updates["person_name"] = canonicalized["person_name"]
    updates["tags"] = canonicalized["tags"]
    updates["entities"] = canonicalized["entities"]
    if note_type is not None:
        updates["note_type"] = note_type

    try:
        result = (
            supabase_admin.table("notes")
            .update(updates)
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="note not found")
        return rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/notes/delete")
def delete_note(payload: NoteDeleteIn, request: Request):
    note_id = (payload.note_id or "").strip()
    user_id = _get_authenticated_user_id(request)

    if not note_id:
        raise HTTPException(status_code=400, detail="note_id is required")

    try:
        existing = (
            supabase_admin.table("notes")
            .select("id")
            .eq("id", note_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (existing.data or []):
            raise HTTPException(status_code=404, detail="note not found")

        (
            supabase_admin.table("notes")
            .delete()
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
        return {"ok": True, "note_id": note_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.get("/uploads/manage")
def list_uploaded_assets(request: Request):
    user_id = _get_authenticated_user_id(request)
    try:
        rows = get_user_notes(user_id)
        assets = [
            row for row in rows
            if str(row.get("image_url") or "").strip()
            and str(row.get("memory_type") or "").strip().lower() in {"image", "document"}
        ]
        return {"items": assets, "count": len(assets)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/uploads/manage/remove")
def remove_uploaded_asset(payload: NoteAssetRemoveIn, request: Request):
    note_id = (payload.note_id or "").strip()
    user_id = _get_authenticated_user_id(request)
    if not note_id:
        raise HTTPException(status_code=400, detail="note_id is required")

    try:
        existing = (
            supabase_admin.table("notes")
            .select("*")
            .eq("id", note_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="note not found")

        note = rows[0]
        file_url = str(note.get("image_url") or "").strip()
        if file_url:
            try:
                delete_uploaded_file_url(file_url)
            except Exception as exc:
                print(f"Asset deletion warning for note {note_id}: {exc}")

        updates = {
            "image_url": None,
            "memory_type": "text",
        }
        result = (
            supabase_admin.table("notes")
            .update(updates)
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
        updated = (result.data or [{}])[0]
        return {"ok": True, "note": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_detail(e)) from e


@app.post("/notes/uploads")
@app.post("/notes/images")
async def create_uploaded_notes(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    user_id = _get_authenticated_user_id(request)

    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")
    if len(files) > MAX_FILE_UPLOADS_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"upload at most {MAX_FILE_UPLOADS_PER_REQUEST} files at once")

    existing_total = count_uploaded_memories(user_id)
    if existing_total + len(files) > MAX_FILE_MEMORIES_PER_USER:
        raise HTTPException(status_code=400, detail=f"uploaded memory limit is {MAX_FILE_MEMORIES_PER_USER} per user")

    prepared_uploads: list[tuple[str, str, str, bytes]] = []
    for upload in files:
        file_name = upload.filename or "upload.bin"
        file_bytes = await upload.read()
        try:
            memory_type, content_type = validate_uploaded_file(file_name, upload.content_type or "", file_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        prepared_uploads.append((file_name, memory_type, content_type, file_bytes))

    created = []
    for file_name, memory_type, content_type, file_bytes in prepared_uploads:
        try:
            file_url = upload_file_bytes(
                user_id=user_id,
                file_name=file_name,
                file_bytes=file_bytes,
                content_type=content_type,
            )
            note = create_uploaded_note_placeholder(
                user_id=user_id,
                file_url=file_url,
                file_name=file_name,
                memory_type=memory_type,
            )
            background_tasks.add_task(
                process_uploaded_note,
                note["id"],
                user_id,
                file_url,
                file_name,
                file_bytes,
                content_type,
                memory_type,
            )
            created.append(note)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=_error_detail(e)) from e

    return {
        "notes": created,
        "count": len(created),
        "message": "Files uploaded. Processing is running in the background.",
    }
