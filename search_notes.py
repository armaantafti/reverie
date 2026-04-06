from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
IST = timezone(timedelta(hours=5, minutes=30))

TAGS_KNOWN = {
    "travel", "entertainment", "food", "study", "school", "fitness", "health", "friends",
    "family", "work", "finance", "personal", "tasks", "ideas", "goals", "communication",
    "documents", "events",
}

TAG_WEIGHTS = {
    "tasks": 1.00,
    "goals": 0.94,
    "communication": 0.88,
    "events": 0.82,
    "family": 0.78,
    "friends": 0.76,
    "work": 0.74,
    "school": 0.73,
    "study": 0.72,
    "personal": 0.64,
    "finance": 0.66,
    "health": 0.62,
    "fitness": 0.60,
    "travel": 0.56,
    "documents": 0.54,
    "ideas": 0.52,
    "food": 0.46,
    "entertainment": 0.40,
}

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
    type_like = q in {"reminder", "recommendation", "note"}
    tag_like = q in TAGS_KNOWN
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
        keep = False
        for k in kws:
            if k in {"reminder", "recommendation", "note"}:
                if type_str == k:
                    keep = True
                    break
            elif k in TAGS_KNOWN:
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
        if keep:
            results.append(n)
    return results
