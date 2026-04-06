from typing import Optional, Any

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from supabase_client import supabase_admin, supabase_auth
from note_core import process_text_note
from search_notes import filter_notes, filter_by_keywords, rank_for_you, context_notes
from sync_notes_to_gcal import sync_notes_to_calendar
from llm_search import summarise_search, extract_search_signals

app = FastAPI(title="Reverie API")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


def get_user_notes(user_id: str):
    result = (
        supabase_admin.table("notes")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


VALID_NOTE_STATUSES = {"pending", "completed", "skipped"}


class NoteStatusIn(BaseModel):
    note_id: str
    user_id: Optional[str] = None
    status: str
    status_note: Optional[str] = None


def _error_detail(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    if getattr(exc, "args", None):
        return str(exc.args[0])
    return "Request failed"


def _extract_bearer_token(request: Request) -> str:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return token


def _get_authenticated_user_id(request: Request) -> str:
    token = _extract_bearer_token(request)
    try:
        response = supabase_auth.auth.get_user(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail="invalid access token") from e

    user = getattr(response, "user", None) or (response.get("user") if isinstance(response, dict) else None)
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=401, detail="invalid access token")
    return user_id.strip()


class AuthIn(BaseModel):
    email: str
    password: str


@app.post("/signup")
async def signup(data: AuthIn):
    email = data.email.strip()
    password = data.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    try:
        res = supabase_auth.auth.sign_up({
            "email": email,
            "password": password
        })
        return jsonable_encoder(res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e


@app.post("/login")
async def login(data: AuthIn):
    email = data.email.strip()
    password = data.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    try:
        res = supabase_auth.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return jsonable_encoder(res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_error_detail(e)) from e


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request}
    )


@app.get("/recommendations", response_class=HTMLResponse)
async def recs_page(request: Request):
    return templates.TemplateResponse(
        "recommendations.html",
        {"request": request}
    )


class TextNoteIn(BaseModel):
    text: str
    user_id: Optional[str] = None


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


@app.post("/sync-calendar")
def sync_calendar():
    try:
        sync_notes_to_calendar()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": _error_detail(e)}


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
    user_id: Optional[str] = Query(None, description="Supabase user id"),
    query: Optional[str] = Query(None, description="Search text in title/summary/person/tags"),
    days: Optional[int] = Query(None, description="Limit to last N days"),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    results = filter_notes(notes, query=query, days=days)
    return results


@app.get("/for-you")
def for_you(
    request: Request,
    user_id: Optional[str] = Query(None, description="Supabase user id"),
    limit: Optional[int] = Query(6, ge=1, le=20),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    ranked = rank_for_you(notes, limit=limit)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/for-you/all")
def for_you_all(request: Request, user_id: Optional[str] = Query(None, description="Supabase user id")):
    notes = get_user_notes(_get_authenticated_user_id(request))
    ranked = rank_for_you(notes, limit=None)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/context")
def context_view(
    request: Request,
    user_id: Optional[str] = Query(None, description="Supabase user id"),
    kind: str = Query(...),
    value: str = Query(...),
):
    notes = get_user_notes(_get_authenticated_user_id(request))
    results = context_notes(notes, kind=kind, value=value)
    return {"kind": kind, "value": value, "notes": results, "count": len(results)}


class SmartSearchIn(BaseModel):
    query: str
    user_id: Optional[str] = None
    days: Optional[int] = None


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
