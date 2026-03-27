from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from note_core import process_text_note
from search_notes import load_notes, filter_notes, filter_by_keywords, rank_for_you, context_notes
from sync_notes_to_gcal import sync_notes_to_calendar
from llm_search import summarise_search, extract_keywords

app = FastAPI(title="Reverie API")

# Static files
app.mount("/static", StaticFiles(directory="."), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
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


@app.post("/notes/text")
def create_text_note(payload: TextNoteIn):
    note = process_text_note(payload.text, platform="web", message_id=None)
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
    query: Optional[str] = Query(None, description="Search text in title/summary/person/tags"),
    days: Optional[int] = Query(None, description="Limit to last N days"),
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
    return {"kind": kind, "value": value, "notes": results, "count": len(results)}


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
