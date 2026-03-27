import json
from typing import List, Dict

from llm_extractor import LLMConfig, _call_llm_raw


KEYWORD_SYSTEM_PROMPT = (
    "You help the Reverie app understand search queries. "
    "Extract 1-5 short keywords from the user's query that will be useful for searching notes. "
    "Keywords should be 1-3 words each and relevant to entities, tags, or topics. "
    "Output ONLY JSON like {\"keywords\": [\"word1\", \"word2\"]}.\n"
)


def extract_keywords(query: str) -> list[str]:
    cfg = LLMConfig.load()
    q = (query or "").strip()
    if not q:
        return []

    user_prompt = (
        "User query: " + q + "\n\n" +
        "Extract up to 5 keywords."
    )
    try:
        content = _call_llm_raw(cfg, KEYWORD_SYSTEM_PROMPT, user_prompt)
        data = json.loads(content)
        kws = data.get("keywords")
        if isinstance(kws, list):
            return [str(k).strip() for k in kws if str(k).strip()]
    except Exception:
        pass
    # fallback: simple split on spaces, take a few non-stopwords
    parts = [p.strip() for p in q.split() if len(p.strip()) > 2]
    return parts[:5]


SEARCH_SYSTEM_PROMPT = (
    "You are a helpful assistant inside the Reverie app. "
    "Given a user's search query and a list of notes (title, summary, tags, due_time), "
    "write a concise response that helps the user recall what they asked for. "
    "Focus on the most relevant notes and group similar ones together. "
    "Do NOT invent notes that are not in the list."
)


def summarise_search(query: str, notes: List[Dict]) -> str:
    cfg = LLMConfig.load()

    if not notes:
        return "I couldn't find any notes matching that search."

    # Build a compact representation of notes
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
