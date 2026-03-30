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
from llm_search import summarise_search, extract_keywords

DEFAULT_USER_ID = "public-beta"

app = FastAPI(title="Reverie API")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


def resolve_user_id(user_id: Optional[str]) -> str:
    value = (user_id or DEFAULT_USER_ID).strip()
    return value or DEFAULT_USER_ID


def get_user_notes(user_id: str):
    result = (
        supabase_admin.table("notes")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


class AuthIn(BaseModel):
    email: str
    password: str


@app.post("/signup")
async def signup(data: AuthIn):
    email = data.email.strip()
    password = data.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    res = supabase_auth.auth.sign_up({
        "email": email,
        "password": password
    })
    return jsonable_encoder(res)


@app.post("/login")
async def login(data: AuthIn):
    email = data.email.strip()
    password = data.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    res = supabase_auth.auth.sign_in_with_password({
        "email": email,
        "password": password
    })
    return jsonable_encoder(res)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
    request,
    "index.html",
    {"request": request}
)


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse(
    request,
    "tasks.html",
    {"request": request}
)


@app.get("/recommendations", response_class=HTMLResponse)
async def recs_page(request: Request):
    return templates.TemplateResponse(
    request,
    "recommendations.html",
    {"request": request}
)

class TextNoteIn(BaseModel):
    text: str
    user_id: Optional[str] = None


@app.post("/notes/text")
def create_text_note(payload: TextNoteIn):
    note = process_text_note(
        payload.text,
        platform="web",
        message_id=None,
        user_id=resolve_user_id(payload.user_id),
    )
    return note


@app.post("/sync-calendar")
def sync_calendar():
    try:
        sync_notes_to_calendar()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/notes")
def list_notes(
    user_id: Optional[str] = Query(None, description="Supabase user id"),
    query: Optional[str] = Query(None, description="Search text in title/summary/person/tags"),
    days: Optional[int] = Query(None, description="Limit to last N days"),
):
    notes = get_user_notes(resolve_user_id(user_id))
    results = filter_notes(notes, query=query, days=days)
    return results


@app.get("/for-you")
def for_you(
    user_id: Optional[str] = Query(None, description="Supabase user id"),
    limit: Optional[int] = Query(6, ge=1, le=20),
):
    notes = get_user_notes(resolve_user_id(user_id))
    ranked = rank_for_you(notes, limit=limit)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/for-you/all")
def for_you_all(user_id: Optional[str] = Query(None, description="Supabase user id")):
    notes = get_user_notes(resolve_user_id(user_id))
    ranked = rank_for_you(notes, limit=None)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/context")
def context_view(
    user_id: Optional[str] = Query(None, description="Supabase user id"),
    kind: str = Query(...),
    value: str = Query(...),
):
    notes = get_user_notes(resolve_user_id(user_id))
    results = context_notes(notes, kind=kind, value=value)
    return {"kind": kind, "value": value, "notes": results, "count": len(results)}


class SmartSearchIn(BaseModel):
    query: str
    user_id: Optional[str] = None
    days: Optional[int] = None


@app.post("/smart-search")
def smart_search(payload: SmartSearchIn):
    notes = get_user_notes(resolve_user_id(payload.user_id))
    keywords = extract_keywords(payload.query)
    filtered = filter_by_keywords(notes, keywords=keywords, days=payload.days)
    summary = summarise_search(payload.query, filtered)
    return {
        "summary": summary,
        "keywords": keywords,
        "notes": filtered
    }
