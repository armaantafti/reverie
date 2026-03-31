import json
import re
from typing import Any, Dict, List, Optional

from llm_extractor import LLMConfig, _call_llm_raw

PREDEFINED_TAGS = [
    "travel",
    "entertainment",
    "food",
    "study",
    "school",
    "fitness",
    "health",
    "friends",
    "family",
    "work",
    "finance",
    "personal",
    "tasks",
    "ideas",
    "goals",
    "communication",
    "documents",
    "events",
]

KEYWORD_SYSTEM_PROMPT = (
    "You help the Reverie app understand search queries. "
    "Extract 1-5 short keywords from the user's query that will be useful for searching notes. "
    "Also choose the single best matching tag from this exact list when one fits: "
    + ", ".join(PREDEFINED_TAGS)
    + ". "
    "Use the meaning of the query to decide the best tag. "
    "Output ONLY valid JSON in this exact shape: "
    '{"keywords":["word1","word2"],"best_matching_tag":"entertainment"}. '
    "If no tag clearly fits, use null for best_matching_tag."
)

SEARCH_SYSTEM_PROMPT = (
    "You are a helpful assistant inside the Reverie app. "
    "Given a user's search query and a list of notes (title, summary, tags, due_time), "
    "write a concise response that helps the user recall what they asked for. "
    "Focus on the most relevant notes and group similar ones together. "
    "Do NOT invent notes that are not in the list."
)


def _strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json_response(text: str) -> Dict[str, Any]:
    text = _strip_code_fences(text)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _normalize_keywords(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        s = str(item).strip()
        if s:
            out.append(s)
        if len(out) >= 5:
            break
    return out


def _normalize_tag(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    tag = value.strip().lower()
    return tag if tag in PREDEFINED_TAGS else None


def extract_search_signals(query: str) -> Dict[str, object]:
    q = (query or "").strip()
    if not q:
        return {"keywords": [], "best_matching_tag": None}

    cfg = LLMConfig.load()
    user_prompt = (
        f"User query: {q}\n\n"
        "Return JSON with:\n"
        "- keywords: array of 1 to 5 short keywords\n"
        f"- best_matching_tag: one tag from this list or null: {', '.join(PREDEFINED_TAGS)}\n"
        "Do not invent tags. Return only JSON."
    )

    try:
        content = _call_llm_raw(cfg, KEYWORD_SYSTEM_PROMPT, user_prompt)
        data = _parse_json_response(content)

        keywords = _normalize_keywords(data.get("keywords"))
        best_matching_tag = _normalize_tag(data.get("best_matching_tag"))

        return {
            "keywords": keywords,
            "best_matching_tag": best_matching_tag,
        }

    except Exception:
        return {
            "keywords": [],
            "best_matching_tag": None,
        }


def extract_keywords(query: str) -> list[str]:
    return list(extract_search_signals(query).get("keywords") or [])


def summarise_search(query: str, notes: List[Dict]) -> str:
    cfg = LLMConfig.load()

    if not notes:
        return "I couldn't find any notes matching that search."

    lines = []
    for i, n in enumerate(notes[:20], start=1):
        title = n.get("title") or "(no title)"
        summary = n.get("summary") or ""
        tags = ", ".join(n.get("tags") or [])
        due = n.get("due_time") or ""
        line = f"{i}. Title: {title}\n   Summary: {summary}\n   Tags: {tags}\n   Due: {due}"
        lines.append(line)

    notes_blob = "\n\n".join(lines)

    user_prompt = (
        f"User query: {query}\n\n"
        f"Here are the matching notes:\n\n{notes_blob}\n\n"
        f"Now give the user a short answer (2-5 sentences) that summarises the key items and suggestions."
    )

    return _call_llm_raw(cfg, SEARCH_SYSTEM_PROMPT, user_prompt)
