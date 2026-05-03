from datetime import datetime
from typing import Optional, Any

from fastapi import FastAPI, Query, Request, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from supabase_client import supabase_admin, supabase_auth
from note_core import (
    process_text_note,
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
from search_notes import filter_notes, filter_by_keywords, rank_for_you, context_notes
from llm_search import summarise_search, extract_search_signals
from tag_config import PREDEFINED_TAGS

app = FastAPI(title="Reverie API")

SESSION_COOKIE_NAME = "reverie_session"

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

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


def _parse_note_types(types: Optional[str]) -> list[str]:
    return [item.strip().lower() for item in (types or "").split(",") if item.strip()]


def _template_context(request: Request) -> dict[str, Any]:
    return {
        "request": request,
        "predefined_tags": list(PREDEFINED_TAGS),
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


def _cookie_secure(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").lower()
    if "https" in forwarded_proto:
        return True
    return request.url.scheme == "https"


def _set_session_cookie(response: JSONResponse, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: JSONResponse, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=_cookie_secure(request),
    )


def _extract_request_token(request: Request) -> str:
    cookie_token = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if cookie_token:
        return cookie_token

    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return token


def _get_authenticated_user_id(request: Request) -> str:
    token = _extract_request_token(request)
    try:
        response = supabase_auth.auth.get_user(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail="invalid access token") from e

    user = getattr(response, "user", None) or (response.get("user") if isinstance(response, dict) else None)
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=401, detail="invalid access token")
    return user_id.strip()


def _get_authenticated_user(request: Request) -> dict[str, Any]:
    token = _extract_request_token(request)
    try:
        response = supabase_auth.auth.get_user(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail="invalid access token") from e

    user = getattr(response, "user", None) or (response.get("user") if isinstance(response, dict) else None)
    encoded = jsonable_encoder(user) if user is not None else None
    if not isinstance(encoded, dict) or not str(encoded.get("id") or "").strip():
        raise HTTPException(status_code=401, detail="invalid access token")
    return encoded


def _get_auth_payload_token(payload: Any) -> str:
    data = jsonable_encoder(payload)
    return str(
        data.get("access_token")
        or (data.get("session") or {}).get("access_token")
        or (data.get("data") or {}).get("access_token")
        or ((data.get("data") or {}).get("session") or {}).get("access_token")
        or ""
    ).strip()


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
        body = jsonable_encoder(res)
        response = JSONResponse(content=body)
        token = _get_auth_payload_token(res)
        if token:
            _set_session_cookie(response, request, token)
        return response
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
        body = jsonable_encoder(res)
        response = JSONResponse(content=body)
        token = _get_auth_payload_token(res)
        if token:
            _set_session_cookie(response, request, token)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e


@app.get("/session")
def get_session(request: Request):
    user = _get_authenticated_user(request)
    return {
        "authenticated": True,
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
        },
    }


@app.post("/logout")
def logout(request: Request):
    response = JSONResponse(content={"ok": True})
    _clear_session_cookie(response, request)
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
    return results


@app.get("/for-you")
def for_you(
    request: Request,
    limit: Optional[int] = Query(6, ge=1, le=20),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    ranked = rank_for_you(notes, limit=limit)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/for-you/all")
def for_you_all(request: Request):
    notes = get_user_notes(_get_authenticated_user_id(request))
    ranked = rank_for_you(notes, limit=None)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/context")
def context_view(
    request: Request,
    kind: str = Query(...),
    value: str = Query(...),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    results = context_notes(notes, kind=kind, value=value)
    return {"kind": kind, "value": value, "notes": results, "count": len(results)}


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
        return {"kind": kind, "value": value, "summary": summary, "notes": results, "count": len(results)}
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
            return {
                "summary": "I couldn't understand that search well enough to find relevant notes.",
                "notes": [],
            }

        filtered = filter_by_keywords(notes, keywords=search_terms, days=payload.days)
        try:
            summary = summarise_search(payload.query, filtered)
        except Exception:
            summary = "Smart summarise failed."
        return {
            "summary": summary,
            "notes": filtered,
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
