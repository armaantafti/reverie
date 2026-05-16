from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tag_config import PREDEFINED_TAG_SET, TAG_WEIGHTS

IST = timezone(timedelta(hours=5, minutes=30))

def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt


def parse_date(s: str):
    return _parse_datetime(s)


def _note_reference_time(note: Dict[str, Any], now: datetime) -> Optional[datetime]:
    note_type = (note.get("note_type") or "").lower()
    due_time = _parse_datetime(note.get("due_time"))
    created_at = _parse_datetime(note.get("created_at"))

    if note_type == "reminder" and due_time is not None:
        return due_time
    return created_at or due_time or now


def _time_score(note: Dict[str, Any], now: datetime) -> float:
    note_type = (note.get("note_type") or "").lower()
    status = (note.get("status") or "pending").strip().lower()
    due_time = _parse_datetime(note.get("due_time"))
    created_at = _parse_datetime(note.get("created_at"))

    if note_type == "reminder" and status == "pending" and due_time is not None:
        if due_time < now:
            return 1.00
        hours_until_due = (due_time - now).total_seconds() / 3600.0
        if hours_until_due <= 24:
            return 0.95
        if hours_until_due <= 168:
            return 0.75
        return 0.30

    if created_at is None:
        return 0.30

    hours_since_created = max((now - created_at).total_seconds() / 3600.0, 0.0)
    if hours_since_created <= 24:
        return 0.70
    if hours_since_created <= 720:
        return 0.50
    return 0.30


def _type_score(note: Dict[str, Any]) -> float:
    note_type = (note.get("note_type") or "").lower()
    if note_type == "reminder":
        return 1.00
    if note_type == "recommendation":
        return 0.72
    if note_type == "passive":
        return 0.32
    return 0.45


def _tag_score(note: Dict[str, Any]) -> float:
    tags = [str(t).strip().lower() for t in (note.get("tags") or []) if str(t).strip()]
    if not tags:
        return 0.0
    weights = [TAG_WEIGHTS.get(tag, 0.36) for tag in tags]
    average = sum(weights) / len(weights)
    peak = max(weights)
    diversity_boost = min(len(tags), 3) * 0.03
    return min(1.0, (0.65 * peak) + (0.35 * average) + diversity_boost)


def _person_score(note: Dict[str, Any]) -> float:
    return 1.0 if str(note.get("person_name") or "").strip() else 0.0


def _entity_score(note: Dict[str, Any]) -> float:
    entities = note.get("entities") or []
    if not isinstance(entities, list):
        entities = [entities]
    count = sum(1 for e in entities if str(e).strip())
    return min(count, 5) / 5.0


def _status_score(note: Dict[str, Any]) -> float:
    status = (note.get("status") or "pending").strip().lower()
    if status == "pending":
        return 1.00
    if status == "skipped":
        return 0.45
    return 0.0


def _richness_score(note: Dict[str, Any]) -> float:
    return (0.5 * _person_score(note)) + (0.5 * _entity_score(note))


def score_for_you(note: Dict[str, Any], now: Optional[datetime] = None) -> float:
    now = now or datetime.now(IST)
    status_component = _status_score(note)
    time_component = _time_score(note, now)
    type_component = _type_score(note)
    tag_component = _tag_score(note)
    richness_component = _richness_score(note)
    score = (
        0.40 * status_component +
        0.35 * time_component +
        0.15 * type_component +
        0.07 * tag_component +
        0.03 * richness_component
    )
    return round(score, 6)


def rank_for_you(notes: Iterable[Dict[str, Any]], limit: Optional[int] = 6) -> List[Dict[str, Any]]:
    now = datetime.now(IST)
    ranked: List[Dict[str, Any]] = []
    for note in notes:
        note_type = (note.get("note_type") or "").lower()
        status = (note.get("status") or "pending").strip().lower()

        if status == "completed":
            continue
        if note_type == "passive":
            continue

        item = dict(note)
        item["score"] = score_for_you(note, now=now)
        reference = _note_reference_time(note, now) or now
        item["_reference_ts"] = reference.timestamp()
        item["_status_rank"] = {"pending": 2, "skipped": 1}.get(status, 0)
        item["_type_rank"] = {"reminder": 3, "recommendation": 2, "note": 1}.get(note_type, 0)
        ranked.append(item)
    ranked.sort(key=lambda n: (-float(n.get("score", 0.0)), -int(n.get("_status_rank", 0)), -float(n.get("_reference_ts", 0.0)), -int(n.get("_type_rank", 0)), str(n.get("title") or "").lower()))
    cleaned = []
    for item in ranked[:limit] if limit is not None else ranked:
        item = dict(item)
        item.pop("_reference_ts", None)
        item.pop("_status_rank", None)
        item.pop("_type_rank", None)
        cleaned.append(item)
    return cleaned


def context_notes(notes: Iterable[Dict[str, Any]], kind: str, value: str) -> List[Dict[str, Any]]:
    kind = (kind or "").strip().lower()
    value_l = (value or "").strip().lower()
    now = datetime.now(IST)
    ranked = []
    for note in notes:
        matches = False
        if kind == "tag":
            matches = value_l in {str(t).strip().lower() for t in (note.get("tags") or [])}
        elif kind == "person":
            matches = value_l == str(note.get("person_name") or "").strip().lower()
        elif kind == "entity":
            matches = value_l in {str(e).strip().lower() for e in (note.get("entities") or [])}
        elif kind == "type":
            matches = value_l == str(note.get("note_type") or "").strip().lower()
        else:
            continue
        if not matches:
            continue
        item = dict(note)
        ref = _note_reference_time(note, now) or now
        item["_reference_ts"] = ref.timestamp()
        item["_score"] = score_for_you(note, now=now)
        ranked.append(item)
    ranked.sort(key=lambda n: (-float(n.get("_reference_ts", 0.0)), -float(n.get("_score", 0.0)), str(n.get("title") or "").lower()))
    cleaned = []
    for item in ranked:
        item = dict(item)
        item.pop("_reference_ts", None)
        item.pop("_score", None)
        cleaned.append(item)
    return cleaned


def filter_notes(notes, query=None, days=None):
    now = datetime.now(IST)
    cutoff = now - timedelta(days=days) if days is not None else None
    results = []
    q = (query or "").lower()
    type_like = q in {"reminder", "recommendation", "note", "passive"}
    tag_like = q in PREDEFINED_TAG_SET
    for n in notes:
        if cutoff is not None:
            created = parse_date(n.get("created_at"))
            if created is None or created < cutoff:
                continue
        if q:
            if type_like or tag_like:
                if type_like and (n.get("note_type") or "").lower() != q:
                    continue
                if tag_like:
                    note_tags = [t.lower() for t in (n.get("tags") or [])]
                    if q not in note_tags:
                        continue
            else:
                haystack = " ".join([
                    n.get("title") or "",
                    n.get("summary") or "",
                    n.get("raw_text") or "",
                    n.get("extracted_text") or "",
                    n.get("person_name") or "",
                    " ".join(n.get("tags") or []),
                    " ".join(n.get("entities") or []),
                ]).lower()
                if q not in haystack:
                    continue
        results.append(n)
    return results


def filter_by_keywords(notes, keywords=None, days=None):
    if not keywords:
        return filter_notes(notes, query=None, days=days)
    now = datetime.now(IST)
    cutoff = now - timedelta(days=days) if days is not None else None
    results = []
    kws = [k.lower() for k in keywords if k]
    for n in notes:
        if cutoff is not None:
            created = parse_date(n.get("created_at"))
            if created is None or created < cutoff:
                continue
        type_str = (n.get("note_type") or "").lower()
        note_tags = [t.lower() for t in (n.get("tags") or [])]
        entities = [e.lower() for e in (n.get("entities") or [])]
        person = (n.get("person_name") or "").lower()
        title = (n.get("title") or "").lower()
        summary = (n.get("summary") or "").lower()
        raw_text = (n.get("raw_text") or "").lower()
        extracted_text = (n.get("extracted_text") or "").lower()
        keep = False
        for k in kws:
            if k in {"reminder", "recommendation", "note", "passive"}:
                if type_str == k:
                    keep = True
                    break
            elif k in PREDEFINED_TAG_SET:
                if k in note_tags:
                    keep = True
                    break
            else:
                if person and k == person:
                    keep = True
                    break
                if k in entities:
                    keep = True
                    break
                if k in note_tags:
                    keep = True
                    break
                if k in title or k in summary:
                    keep = True
                    break
                if k in raw_text or k in extracted_text:
                    keep = True
                    break
        if keep:
            results.append(n)
    return results


def _normalise_search_terms(values: Sequence[Any]) -> List[str]:
    terms: List[str] = []
    seen = set()
    for value in values or []:
        term = str(value or "").strip().lower()
        if not term or term in seen:
            continue
        terms.append(term)
        seen.add(term)
    return terms


def _contains_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    return term in text


def _clean_reason(label: str, term: str) -> str:
    clean = str(term or "").strip()
    if not clean:
        return label
    return f"{label}: {clean}"


def score_search_match(
    note: Dict[str, Any],
    query: str = "",
    keywords: Optional[Sequence[str]] = None,
    matched_tag: Optional[str] = None,
) -> tuple[int, List[str]]:
    terms = _normalise_search_terms(list(keywords or []) + _fallback_query_terms(query))
    tag_signal = str(matched_tag or "").strip().lower()
    if tag_signal and tag_signal not in terms:
        terms.append(tag_signal)

    title = (note.get("title") or "").lower()
    summary = (note.get("summary") or "").lower()
    raw = f"{note.get('raw_text') or ''} {note.get('extracted_text') or ''}".lower()
    note_type = (note.get("note_type") or "").lower()
    memory_type = (note.get("memory_type") or "").lower()
    tags = [str(t).strip().lower() for t in (note.get("tags") or []) if str(t).strip()]
    entities = [str(e).strip().lower() for e in (note.get("entities") or []) if str(e).strip()]
    person = (note.get("person_name") or "").strip().lower()

    score = 0
    reasons: List[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        if reason and reason not in reasons:
            reasons.append(reason)

    for term in terms:
        if not term:
            continue
        if _contains_term(title, term):
            add(10, _clean_reason("title", term))
        if _contains_term(summary, term):
            add(7, _clean_reason("summary", term))
        if term in tags:
            add(8, _clean_reason("tag", term))
        elif any(_contains_term(tag, term) or _contains_term(term, tag) for tag in tags):
            add(5, _clean_reason("related tag", term))
        if term in entities:
            add(8, _clean_reason("entity", term))
        elif any(_contains_term(entity, term) or _contains_term(term, entity) for entity in entities):
            add(5, _clean_reason("related entity", term))
        if person and (term == person or _contains_term(person, term) or _contains_term(term, person)):
            add(9, _clean_reason("person", term))
        if term in {note_type, memory_type}:
            add(6, _clean_reason("type", term))
        if _contains_term(raw, term):
            add(2, _clean_reason("text", term))

    if tag_signal and tag_signal in tags:
        add(6, _clean_reason("selected tag", tag_signal))

    return score, reasons[:6]


def _fallback_query_terms(query: str) -> List[str]:
    tokens = [token.lower() for token in str(query or "").replace("/", " ").replace("-", " ").split()]
    stop_words = {
        "a", "an", "and", "are", "for", "from", "i", "in", "is", "it", "me", "my",
        "of", "on", "or", "show", "that", "the", "to", "was", "what", "when", "where",
        "with", "about", "all", "find", "search",
    }
    terms: List[str] = []
    seen = set()
    for token in tokens:
        cleaned = "".join(ch for ch in token if ch.isalnum() or ch in {"'", "_"}).strip("'_")
        if len(cleaned) < 2 or cleaned in stop_words or cleaned in seen:
            continue
        terms.append(cleaned)
        seen.add(cleaned)
        if len(terms) >= 6:
            break
    return terms


def _search_reference_ts(note: Dict[str, Any], now: datetime) -> float:
    ref = _note_reference_time(note, now) or now
    return ref.timestamp()


def _search_section(note: Dict[str, Any], score: int) -> str:
    note_type = (note.get("note_type") or "").lower()
    status = (note.get("status") or "pending").strip().lower()
    memory_type = (note.get("memory_type") or "").lower()
    if note_type == "reminder" and status == "pending":
        return "action"
    if memory_type in {"image", "document"}:
        return "document"
    if score >= 12:
        return "best"
    return "related"


def rank_smart_search(
    notes: Iterable[Dict[str, Any]],
    query: str = "",
    keywords: Optional[Sequence[str]] = None,
    matched_tag: Optional[str] = None,
    days: Optional[int] = None,
    min_score: int = 4,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    now = datetime.now(IST)
    cutoff = now - timedelta(days=days) if days is not None else None
    ranked: List[Dict[str, Any]] = []
    for note in notes:
        if cutoff is not None:
            created = parse_date(note.get("created_at"))
            if created is None or created < cutoff:
                continue
        score, reasons = score_search_match(note, query=query, keywords=keywords, matched_tag=matched_tag)
        if score < min_score:
            continue
        item = dict(note)
        item["search_score"] = score
        item["match_reasons"] = reasons
        item["search_section"] = _search_section(item, score)
        item["_reference_ts"] = _search_reference_ts(note, now)
        item["_status_rank"] = 1 if (note.get("status") or "pending").strip().lower() == "pending" else 0
        item["_type_rank"] = {"reminder": 3, "recommendation": 2, "note": 1, "passive": 0}.get(
            (note.get("note_type") or "").lower(),
            0,
        )
        ranked.append(item)

    ranked.sort(
        key=lambda n: (
            -int(n.get("search_score") or 0),
            -int(n.get("_status_rank") or 0),
            -int(n.get("_type_rank") or 0),
            -float(n.get("_reference_ts") or 0.0),
            str(n.get("title") or "").lower(),
        )
    )
    cleaned = []
    for item in ranked[:limit] if limit is not None else ranked:
        item = dict(item)
        item.pop("_reference_ts", None)
        item.pop("_status_rank", None)
        item.pop("_type_rank", None)
        cleaned.append(item)
    return cleaned
