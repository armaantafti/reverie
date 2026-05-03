import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_config.json")
APP_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: Optional[str]
    timeout_seconds: int = 10

    @classmethod
    def load(cls) -> "LLMConfig":
        if not os.path.exists(CONFIG_PATH):
            raise RuntimeError(f"llm_config.json not found at {CONFIG_PATH}")
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            provider=raw.get("provider", "openai"),
            base_url=raw["base_url"],
            model=raw["model"],
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout_seconds=int(raw.get("timeout_seconds", 10)),
        )


SYSTEM_PROMPT = (
    "You are an intelligent memory structuring engine. Your job is to convert raw note text into a clean, structured memory entry for future search and retrieval.\n\n"
    "Respond ONLY with a valid JSON object.\n\n"
    "The JSON MUST have exactly these keys:\n"
    " • person_name: string or null\n"
    " • note_type: one of 'reminder', 'recommendation', 'note', or 'passive' and nothing else\n"
    " • title: a short, clear title (3–6 words). It should feel natural and human, not robotic.\n"
    "   • For reminders, start with a verb (e.g. 'Call Rahul', 'Submit physics assignment')\n"
    "   • For events/interactions, summarise the moment (e.g. 'Dinner with family')\n"
    "   • For ideas/notes, capture the core concept (e.g. 'Mosquito device improvement idea')\n"
    "   • Use 'passive' for non-actionable memories kept mainly for recall, such as screenshots of chats, school incidents, or conversations with no task attached\n"
    "   • Do NOT include prefixes like 'Reminder:' or 'Recommendation' or 'Note'\n"
    " • summary: a concise paraphrase (1–2 sentences). Do not repeat the title. Do not add new information.\n"
    " • tags: array of strings. Choose 1–3 tags ONLY from this list:\n"
    "   ['travel','entertainment','food','study','school','fitness','health','friends',\n"
    "    'family','work','finance','personal','tasks','ideas','goals','communication',\n"
    "    'documents','identity document','events']\n\n"
    "   Tagging rules:\n"
    "   - Use 'identity document' for Aadhaar/Aadhar, PAN, passport, birth certificate, driving license, voter ID, or similar ID proof\n"
    "   • Use 'family' if relatives are involved\n"
    "   • Use 'friends' if friends are involved\n"
    "   • Use 'tasks' for actionable items\n    • Use 'goals' for long-term aims\n"
    "   • Use 'personal' for thoughts or feelings\n"
    "   • Use 'communication' for calls, messages, or conversations\n"
    "   • Use 'events' for specific occasions (birthdays, parties, scheduled gatherings)\n"
    "   • Always include at least one tag if applicable\n"
    "   • Prefer 1–3 tags only\n"
    " • entities: array of 1–5 important non-person entities (topics, objects, places, orgs, etc.).\n"
    "   Exclude the main person_name if already used.\n"
    "   For identity documents, include the normalized document type as an entity, such as 'aadhaar', 'pan', 'passport', or 'birth certificate'.\n"
    " • due_time: string or null\n"
    "   • If a time expression exists, convert it to ISO 8601 format with timezone Asia/Kolkata\n"
    "   • Example: '2026-03-21T15:00:00+05:30'\n"
    "   • If no time is mentioned, return null\n\n"
    "Strict rules:\n"
    " • Do NOT hallucinate or assume missing details\n"
    " • Do NOT include any keys other than the ones listed\n"
    " • Do NOT output anything except the JSON\n"
    " • Keep output concise and consistent"
)


def build_user_prompt(text: str) -> str:
    now = datetime.now(APP_TIMEZONE)
    today_str = now.strftime("%Y-%m-%d")
    now_str = now.isoformat(timespec="seconds")
    prefix = (
        f"Today is {today_str} and the current local datetime is {now_str} "
        f"in timezone Asia/Kolkata. Use this as the reference when interpreting words like "
        f"'today', 'tomorrow', 'next week', etc.\n\n"
    )
    return prefix + f"TEXT:\n{text.strip()}\n\nNow output ONLY the JSON."


def _call_llm(cfg: LLMConfig, text: str) -> Dict[str, Any]:
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(text)},
        ],
        "temperature": 0.1,
    }

    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    resp = requests.post(
        cfg.base_url,
        headers=headers,
        data=json.dumps(payload),
        timeout=cfg.timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()

    # OpenAI-style chat completion response
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned non-JSON content: {content!r}") from e

    return parsed


def _call_llm_raw(cfg: LLMConfig, system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    resp = requests.post(
        cfg.base_url,
        headers=headers,
        data=json.dumps(payload),
        timeout=cfg.timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def extract_with_llm(text: str) -> Dict[str, Any]:
    """High-level API: text -> structured fields.

    Returns a dict with the expected keys. Fills in reasonable defaults
    if the model omits something.
    """
    cfg = LLMConfig.load()
    raw = _call_llm(cfg, text)

    def norm_str(x):
        return x if isinstance(x, str) else None

    def norm_list(x):
        if isinstance(x, list):
            return [str(t) for t in x]
        return []

    out = {
        "person_name": norm_str(raw.get("person_name")),
        "note_type": raw.get("note_type") or "note",
        "summary": norm_str(raw.get("summary")) or text.strip(),
        "tags": norm_list(raw.get("tags")),
        "entities": norm_list(raw.get("entities")),
        "due_time": norm_str(raw.get("due_time")),
        "title": norm_str(raw.get("title")) or (text.strip()[:60] if text.strip() else ""),
    }

    # Normalise empty strings to None for person_name and due_time
    if out["person_name"] == "":
        out["person_name"] = None
    if out["due_time"] == "":
        out["due_time"] = None

    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python llm_extractor.py 'some note text'")
        raise SystemExit(1)

    text = " ".join(sys.argv[1:])
    cfg = LLMConfig.load()
    print(f"Using model {cfg.model} @ {cfg.base_url}")
    result = extract_with_llm(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
