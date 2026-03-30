from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from supabase_client import supabase

from note_core import process_text_note
from sync_notes_to_gcal import sync_notes_to_calendar

# OPTIONAL (still using JSON-based logic for now — we’ll migrate later)
from search_notes import load_notes, filter_notes, filter_by_keywords, rank_for_you, context_notes
from llm_search import summarise_search, extract_keywords


# ✅ CREATE APP FIRST (CRITICAL FIX)
app = FastAPI(title="Reverie API")


# ---------------------------
# AUTH ROUTES
# ---------------------------

@app.post("/signup")
async def signup(data: dict):
    email = data.get("email")
    password = data.get("password")

    res = supabase.auth.sign_up({
        "email": email,
        "password": password
    })

    return res


@app.post("/login")
async def login(data: dict):
    email = data.get("email")
    password = data.get("password")

    res = supabase.auth.sign_in_with_password({
        "email": email,
        "password": password
    })

    return res


# ---------------------------
# STATIC + TEMPLATES
# ---------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------
# PAGES
# ---------------------------

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


# ---------------------------
# CREATE NOTE
# ---------------------------

class TextNoteIn(BaseModel):
    text: str
    user_id: str  # 🔥 REQUIRED


@app.post("/notes/text")
def create_text_note(payload: TextNoteIn):
    note = process_text_note(
        payload.text,
        platform="web",
        message_id=None,
        user_id=payload.user_id  # 🔥 PASS USER
    )
    return note


# ---------------------------
# CALENDAR
# ---------------------------

@app.post("/sync-calendar")
def sync_calendar():
    try:
        sync_notes_to_calendar()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ---------------------------
# TEMP (JSON-BASED ROUTES)
# ---------------------------
# ⚠️ We will migrate these to Supabase next

@app.get("/notes")
def list_notes(
    query: Optional[str] = Query(None),
    days: Optional[int] = Query(None),
):
    notes = load_notes()
    results = filter_notes(notes, query=query, days=days)
    return results


@app.get("/for-you")
def for_you(limit: Optional[int] = Query(6, ge=1, le=20)):
    notes = load_notes()
    ranked = rank_for_you(notes, limit=limit)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/for-you/all")
def for_you_all():
    notes = load_notes()
    ranked = rank_for_you(notes, limit=None)
    return {"notes": ranked, "count": len(ranked)}


@app.get("/context")
def context_view(kind: str = Query(...), value: str = Query(...)):
    notes = load_notes()
    results = context_notes(notes, kind=kind, value=value)
    return {"notes": results, "count": len(results)}


# ---------------------------
# SMART SEARCH
# ---------------------------

class SmartSearchIn(BaseModel):
    query: str
    days: Optional[int] = None


@app.post("/smart-search")
def smart_search(payload: SmartSearchIn):
    notes = load_notes()
    keywords = extract_keywords(payload.query)
    filtered = filter_by_keywords(notes, keywords=keywords, days=payload.days)
    summary = summarise_search(payload.query, filtered)

    return {
        "summary": summary,
        "keywords": keywords,
        "notes": filtered
    }
