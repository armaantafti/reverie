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
    "Read the user's prompt and extract up to 5 search keywords that should be used to search notes. "
    "Also choose exactly one best matching predefined tag when one clearly helps narrow the search. "
    "The tag must come only from this list: "
    + ", ".join(PREDEFINED_TAGS)
    + ". "
    "Output ONLY valid JSON in this exact shape: "
    '{"keywords":["word1","word2"],"best_matching_tag":"entertainment"}. '
    "Use null for best_matching_tag if no predefined tag clearly helps."
)

SEARCH_SYSTEM_PROMPT = (
    "You are a helpful assistant inside the Reverie app. "
    "Given a user's search query and a list of notes (title, summary, tags, due_time, status, status_note), "
    "write a concise response that helps the user recall what they asked for. "
    "Focus on the most relevant notes and group similar ones together. "
    "Take note status and any status note into account when they matter. "
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
    seen = set()
    for item in value:
        s = str(item).strip().lower()
        if not s or s in seen:
            continue
        out.append(s)
        seen.add(s)
        if len(out) >= 5:
            break
    return out


def _normalize_tag(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    tag = value.strip().lower()
    return tag if tag in PREDEFINED_TAGS else None


def _fallback_keywords(query: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9']+", (query or "").lower())
    stop_words = {
        "a", "an", "and", "are", "for", "from", "how", "i", "in", "is", "it",
        "me", "my", "of", "on", "or", "show", "that", "the", "to", "was", "what",
        "when", "where", "with",
    }
    keywords: List[str] = []
    seen = set()
    for token in tokens:
        if token in stop_words or token in seen:
            continue
        keywords.append(token)
        seen.add(token)
        if len(keywords) >= 5:
            break
    return keywords


def extract_search_signals(query: str) -> Dict[str, object]:
    q = (query or "").strip()
    if not q:
        return {"keywords": [], "best_matching_tag": None}

    cfg = LLMConfig.load()
    user_prompt = (
        f"User query: {q}\n\n"
        "Return JSON with:\n"
        "- keywords: array of 1 to 5 short search keywords\n"
        f"- best_matching_tag: one tag from this list or null: {', '.join(PREDEFINED_TAGS)}\n"
        "Rules:\n"
        "- Do not invent tags\n"
        "- Keep keywords short\n"
        "- Do not include more than 5 keywords\n"
        "- Return only JSON\n"
    )

    try:
        content = _call_llm_raw(cfg, KEYWORD_SYSTEM_PROMPT, user_prompt)
        data = _parse_json_response(content)

        keywords = _normalize_keywords(data.get("keywords"))
        best_matching_tag = _normalize_tag(data.get("best_matching_tag"))
        if not keywords:
            keywords = _fallback_keywords(q)

        return {
            "keywords": keywords,
            "best_matching_tag": best_matching_tag,
        }

    except Exception:
        return {
            "keywords": _fallback_keywords(q),
            "best_matching_tag": None,
        }


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
        status = n.get("status") or "pending"
        status_note = n.get("status_note") or ""
        line = (
            f"{i}. Title: {title}\n"
            f"   Summary: {summary}\n"
            f"   Tags: {tags}\n"
            f"   Due: {due}\n"
            f"   Status: {status}\n"
            f"   Status note: {status_note}"
        )
        lines.append(line)

    notes_blob = "\n\n".join(lines)

    user_prompt = (
        f"User query: {query}\n\n"
        f"Here are the matching notes:\n\n{notes_blob}\n\n"
        "Now give the user a short answer (2-5 sentences) that summarises the key items based on the query."
    )

    return _call_llm_raw(cfg, SEARCH_SYSTEM_PROMPT, user_prompt)
