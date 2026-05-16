import json
import re
from typing import Any, Dict, List, Optional

from llm_extractor import LLMConfig, _call_llm_raw
from tag_config import PREDEFINED_TAGS

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
    "You are Reverie's professional memory-search assistant. "
    "Given a user's search query and matching personal notes, produce a polished, useful answer. "
    "Use only the provided notes. Do not invent facts. "
    "Separate confirmed facts from possible inferences. "
    "Prioritize pending reminders, dated items, people, entities, and recent notes when relevant."
)

STRUCTURED_SEARCH_SYSTEM_PROMPT = (
    SEARCH_SYSTEM_PROMPT
    + " Return ONLY valid JSON in this exact shape: "
    '{'
    '"answer_title":"...",'
    '"executive_summary":"...",'
    '"key_points":["..."],'
    '"action_items":[{"title":"...","due_time":"...","status":"...","source_note_number":1}],'
    '"people_or_entities":["..."],'
    '"suggested_next_searches":["..."],'
    '"confidence":"high|medium|low",'
    '"empty_state_suggestion":"..."'
    '}. '
    "If there are no relevant notes, use a low confidence answer and fill empty_state_suggestion. "
    "Keep the tone concise and professional."
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


def _note_lines(notes: List[Dict]) -> str:
    lines = []
    for i, n in enumerate(notes[:20], start=1):
        title = n.get("title") or "(no title)"
        summary = n.get("summary") or ""
        tags = ", ".join(n.get("tags") or [])
        entities = ", ".join(n.get("entities") or [])
        person = n.get("person_name") or ""
        due = n.get("due_time") or ""
        status = n.get("status") or "pending"
        status_note = n.get("status_note") or ""
        note_type = n.get("note_type") or ""
        memory_type = n.get("memory_type") or ""
        reasons = "; ".join(n.get("match_reasons") or [])
        score = n.get("search_score") or ""
        line = (
            f"{i}. Title: {title}\n"
            f"   Summary: {summary}\n"
            f"   Type: {note_type}; Memory type: {memory_type}\n"
            f"   Person: {person}\n"
            f"   Tags: {tags}\n"
            f"   Entities: {entities}\n"
            f"   Due: {due}\n"
            f"   Status: {status}\n"
            f"   Status note: {status_note}\n"
            f"   Search score: {score}\n"
            f"   Match reasons: {reasons}"
        )
        lines.append(line)
    return "\n\n".join(lines)


def _clean_string_list(value: Any, limit: int = 6) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _normalise_action_items(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        out.append(
            {
                "title": title,
                "due_time": str(item.get("due_time") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "source_note_number": item.get("source_note_number"),
            }
        )
        if len(out) >= 5:
            break
    return out


def _normalise_summary_json(value: Dict[str, Any], query: str, notes: List[Dict]) -> Dict[str, Any]:
    title = str(value.get("answer_title") or "Smart answer").strip()
    executive = str(value.get("executive_summary") or "").strip()
    if not executive:
        if notes:
            executive = f"I found {len(notes)} relevant memory{'ies' if len(notes) != 1 else 'y'} for this search."
        else:
            executive = "I could not find a confident match for this search."
    confidence = str(value.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium" if notes else "low"
    return {
        "answer_title": title,
        "executive_summary": executive,
        "key_points": _clean_string_list(value.get("key_points"), limit=5),
        "action_items": _normalise_action_items(value.get("action_items")),
        "people_or_entities": _clean_string_list(value.get("people_or_entities"), limit=8),
        "suggested_next_searches": _clean_string_list(value.get("suggested_next_searches"), limit=4),
        "confidence": confidence,
        "empty_state_suggestion": str(value.get("empty_state_suggestion") or "").strip(),
        "query": query,
    }


def fallback_structured_summary(query: str, notes: List[Dict]) -> Dict[str, Any]:
    key_points: List[str] = []
    action_items: List[Dict[str, Any]] = []
    people_or_entities: List[str] = []
    seen_people_entities = set()
    for index, note in enumerate(notes[:8], start=1):
        title = note.get("title") or "(no title)"
        summary = note.get("summary") or ""
        if len(key_points) < 4:
            key_points.append(f"{title}: {summary}" if summary else str(title))
        if (note.get("note_type") or "").lower() == "reminder" and (note.get("status") or "pending").lower() == "pending":
            action_items.append(
                {
                    "title": str(title),
                    "due_time": note.get("due_time") or "",
                    "status": note.get("status") or "pending",
                    "source_note_number": index,
                }
            )
        person = str(note.get("person_name") or "").strip()
        if person and person.lower() not in seen_people_entities:
            people_or_entities.append(person)
            seen_people_entities.add(person.lower())
        for entity in note.get("entities") or []:
            clean = str(entity or "").strip()
            if clean and clean.lower() not in seen_people_entities:
                people_or_entities.append(clean)
                seen_people_entities.add(clean.lower())
            if len(people_or_entities) >= 8:
                break
    if not notes:
        return _normalise_summary_json(
            {
                "answer_title": "No confident matches",
                "executive_summary": "I could not find a strong match in your saved memories.",
                "confidence": "low",
                "empty_state_suggestion": "Try a person name, tag, document type, or a shorter phrase.",
            },
            query,
            notes,
        )
    return _normalise_summary_json(
        {
            "answer_title": "What I found",
            "executive_summary": f"I found {len(notes)} relevant memory{'ies' if len(notes) != 1 else 'y'} for this search, ranked by match strength.",
            "key_points": key_points,
            "action_items": action_items,
            "people_or_entities": people_or_entities,
            "suggested_next_searches": [],
            "confidence": "medium",
        },
        query,
        notes,
    )


def summarise_search_structured(query: str, notes: List[Dict]) -> Dict[str, Any]:
    if not notes:
        return fallback_structured_summary(query, notes)

    cfg = LLMConfig.load()
    notes_blob = _note_lines(notes)
    user_prompt = (
        f"User query: {query}\n\n"
        f"Here are the top ranked matching notes:\n\n{notes_blob}\n\n"
        "Create the JSON answer now. "
        "Use source_note_number values that correspond to the numbered notes above. "
        "If the notes are weakly related, say so with low or medium confidence."
    )

    try:
        content = _call_llm_raw(cfg, STRUCTURED_SEARCH_SYSTEM_PROMPT, user_prompt)
        data = _parse_json_response(content)
        return _normalise_summary_json(data, query, notes)
    except Exception:
        return fallback_structured_summary(query, notes)
