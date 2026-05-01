import re
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from llm_extractor import extract_with_llm
from supabase_client import supabase_admin
from tag_config import PREDEFINED_TAG_SET

ENTITY_MANAGER_KINDS = {"person", "entity", "tag"}
ENTITY_MANAGER_KIND_ORDER = {"person": 0, "entity": 1, "tag": 2}

def summarise_text(text: str, max_sentences: int = 3) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return text
    return " ".join(sentences[:max_sentences])


def generate_id() -> str:
    return str(uuid.uuid4())


def _now_ist_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()


def _coerce_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _normalise_lookup_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _dedupe_case_insensitive(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = _normalise_lookup_key(text)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        tag_norm = tag.strip().lower()
        if tag_norm in PREDEFINED_TAG_SET and tag_norm not in seen:
            cleaned.append(tag_norm)
            seen.add(tag_norm)

    return cleaned


def _load_entity_alias_rows(user_id: str) -> list[dict[str, Any]]:
    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        return []
    try:
        result = (
            supabase_admin.table("entity_aliases")
            .select("*")
            .eq("user_id", resolved_user_id)
            .execute()
        )
        rows = result.data or []
        return [row for row in rows if isinstance(row, dict)]
    except Exception:
        return []


def _build_entity_alias_map(alias_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    alias_map: dict[str, dict[str, str]] = {kind: {} for kind in ENTITY_MANAGER_KINDS}
    for row in alias_rows:
        kind = str(row.get("kind") or "").strip().lower()
        if kind not in ENTITY_MANAGER_KINDS:
            continue
        alias_value = str(row.get("alias_value") or "").strip()
        canonical_value = str(row.get("canonical_value") or "").strip()
        alias_key = _normalise_lookup_key(alias_value)
        if alias_key and canonical_value:
            alias_map[kind][alias_key] = canonical_value
    return alias_map


def _canonicalize_value(alias_map: dict[str, dict[str, str]], kind: str, value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    resolved_kind = str(kind or "").strip().lower()
    if resolved_kind not in ENTITY_MANAGER_KINDS:
        return text
    return alias_map.get(resolved_kind, {}).get(_normalise_lookup_key(text), text)


def canonicalize_note_metadata(
    user_id: str,
    *,
    person_name: Any = None,
    tags: Any = None,
    entities: Any = None,
) -> dict[str, Any]:
    alias_rows = _load_entity_alias_rows(user_id)
    alias_map = _build_entity_alias_map(alias_rows)

    resolved_person = _canonicalize_value(alias_map, "person", person_name)
    resolved_tags = _dedupe_case_insensitive([
        _canonicalize_value(alias_map, "tag", value) or ""
        for value in _coerce_list(tags)
    ])
    resolved_entities = _dedupe_case_insensitive([
        _canonicalize_value(alias_map, "entity", value) or ""
        for value in _coerce_list(entities)
    ])

    return {
        "person_name": resolved_person,
        "tags": resolved_tags,
        "entities": resolved_entities,
    }


def _note_field_for_kind(kind: str) -> str:
    resolved_kind = str(kind or "").strip().lower()
    if resolved_kind == "person":
        return "person_name"
    if resolved_kind == "entity":
        return "entities"
    if resolved_kind == "tag":
        return "tags"
    raise ValueError("kind must be person, entity, or tag")


def _get_note_rows_for_entity_manager(user_id: str) -> list[dict[str, Any]]:
    result = (
        supabase_admin.table("notes")
        .select("id, person_name, entities, tags")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data or []
    return [row for row in rows if isinstance(row, dict)]


def _collect_related_cluster_values(kind: str, values: list[str], alias_rows: list[dict[str, Any]]) -> list[str]:
    related_keys = {_normalise_lookup_key(value) for value in values if str(value or "").strip()}
    changed = True
    while changed:
        changed = False
        for row in alias_rows:
            row_kind = str(row.get("kind") or "").strip().lower()
            if row_kind != kind:
                continue
            alias_value = str(row.get("alias_value") or "").strip()
            canonical_value = str(row.get("canonical_value") or "").strip()
            alias_key = _normalise_lookup_key(alias_value)
            canonical_key = _normalise_lookup_key(canonical_value)
            if alias_key in related_keys or canonical_key in related_keys:
                if alias_key and alias_key not in related_keys:
                    related_keys.add(alias_key)
                    changed = True
                if canonical_key and canonical_key not in related_keys:
                    related_keys.add(canonical_key)
                    changed = True

    cluster_values: list[str] = []
    seen: set[str] = set()

    def add_value(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        key = _normalise_lookup_key(text)
        if key in seen:
            return
        seen.add(key)
        cluster_values.append(text)

    for value in values:
        add_value(value)
    for row in alias_rows:
        row_kind = str(row.get("kind") or "").strip().lower()
        if row_kind != kind:
            continue
        if _normalise_lookup_key(row.get("alias_value")) in related_keys or _normalise_lookup_key(row.get("canonical_value")) in related_keys:
            add_value(row.get("alias_value"))
            add_value(row.get("canonical_value"))

    return cluster_values


def _delete_alias_rows_by_id(row_ids: list[str]) -> None:
    for row_id in row_ids:
        if not str(row_id or "").strip():
            continue
        (
            supabase_admin.table("entity_aliases")
            .delete()
            .eq("id", row_id)
            .execute()
        )


def _store_alias_cluster(user_id: str, kind: str, target_value: str, alias_values: list[str], alias_rows: list[dict[str, Any]]) -> None:
    resolved_user_id = (user_id or "").strip()
    resolved_kind = str(kind or "").strip().lower()
    target_text = str(target_value or "").strip()
    if not resolved_user_id or resolved_kind not in ENTITY_MANAGER_KINDS or not target_text:
        raise ValueError("user_id, kind, and target_value are required")

    cluster_values = _collect_related_cluster_values(resolved_kind, alias_values + [target_text], alias_rows)
    cluster_keys = {_normalise_lookup_key(value) for value in cluster_values}

    removable_ids: list[str] = []
    for row in alias_rows:
        row_kind = str(row.get("kind") or "").strip().lower()
        if row_kind != resolved_kind:
            continue
        alias_key = _normalise_lookup_key(row.get("alias_value"))
        canonical_key = _normalise_lookup_key(row.get("canonical_value"))
        if alias_key in cluster_keys or canonical_key in cluster_keys:
            removable_ids.append(str(row.get("id") or "").strip())
    _delete_alias_rows_by_id(removable_ids)

    rows_to_insert: list[dict[str, Any]] = []
    for value in _dedupe_case_insensitive([target_text] + cluster_values):
        rows_to_insert.append({
            "user_id": resolved_user_id,
            "kind": resolved_kind,
            "alias_value": value,
            "canonical_value": target_text,
        })
    if rows_to_insert:
        supabase_admin.table("entity_aliases").insert(rows_to_insert).execute()


def _rewrite_notes_for_kind(user_id: str, kind: str, transform_value) -> None:
    field = _note_field_for_kind(kind)
    rows = _get_note_rows_for_entity_manager(user_id)
    for row in rows:
        note_id = str(row.get("id") or "").strip()
        if not note_id:
            continue

        updates: dict[str, Any] = {}
        if field == "person_name":
            current = str(row.get("person_name") or "").strip()
            next_value = transform_value(current)
            if (next_value or None) != (current or None):
                updates[field] = next_value
        else:
            current_values = _coerce_list(row.get(field))
            next_values = _dedupe_case_insensitive([
                transformed
                for transformed in (transform_value(value) for value in current_values)
                if str(transformed or "").strip()
            ])
            if next_values != current_values:
                updates[field] = next_values

        if updates:
            (
                supabase_admin.table("notes")
                .update(updates)
                .eq("id", note_id)
                .eq("user_id", user_id)
                .execute()
            )


def list_entity_manager_items(user_id: str) -> list[dict[str, Any]]:
    alias_rows = _load_entity_alias_rows(user_id)
    alias_map = _build_entity_alias_map(alias_rows)
    note_rows = _get_note_rows_for_entity_manager(user_id)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    def ensure_item(kind: str, value: str) -> dict[str, Any]:
        canonical_value = str(value or "").strip()
        key = (kind, _normalise_lookup_key(canonical_value))
        if key not in grouped:
            grouped[key] = {
                "kind": kind,
                "value": canonical_value,
                "count": 0,
                "aliases": set(),
            }
        return grouped[key]

    for row in alias_rows:
        kind = str(row.get("kind") or "").strip().lower()
        if kind not in ENTITY_MANAGER_KINDS:
            continue
        canonical_value = _canonicalize_value(alias_map, kind, row.get("canonical_value")) or str(row.get("canonical_value") or "").strip()
        item = ensure_item(kind, canonical_value)
        alias_value = str(row.get("alias_value") or "").strip()
        if alias_value and _normalise_lookup_key(alias_value) != _normalise_lookup_key(canonical_value):
            item["aliases"].add(alias_value)

    for row in note_rows:
        person_name = str(row.get("person_name") or "").strip()
        if person_name:
            canonical_person = _canonicalize_value(alias_map, "person", person_name) or person_name
            item = ensure_item("person", canonical_person)
            item["count"] += 1
            if _normalise_lookup_key(person_name) != _normalise_lookup_key(canonical_person):
                item["aliases"].add(person_name)

        for entity in _coerce_list(row.get("entities")):
            canonical_entity = _canonicalize_value(alias_map, "entity", entity) or entity
            item = ensure_item("entity", canonical_entity)
            item["count"] += 1
            if _normalise_lookup_key(entity) != _normalise_lookup_key(canonical_entity):
                item["aliases"].add(entity)

        for tag in _coerce_list(row.get("tags")):
            canonical_tag = _canonicalize_value(alias_map, "tag", tag) or tag
            item = ensure_item("tag", canonical_tag)
            item["count"] += 1
            if _normalise_lookup_key(tag) != _normalise_lookup_key(canonical_tag):
                item["aliases"].add(tag)

    items = []
    for item in grouped.values():
        items.append({
            "kind": item["kind"],
            "value": item["value"],
            "count": int(item["count"]),
            "aliases": sorted(item["aliases"], key=lambda value: (_normalise_lookup_key(value), value.lower())),
        })

    items.sort(
        key=lambda item: (
            ENTITY_MANAGER_KIND_ORDER.get(item["kind"], 99),
            -int(item["count"]),
            _normalise_lookup_key(item["value"]),
        )
    )
    return items


def create_entity_manager_item(user_id: str, kind: str, value: str) -> dict[str, Any]:
    resolved_kind = str(kind or "").strip().lower()
    resolved_value = str(value or "").strip()
    if resolved_kind not in ENTITY_MANAGER_KINDS:
        raise ValueError("kind must be person, entity, or tag")
    if not resolved_value:
        raise ValueError("value is required")

    alias_rows = _load_entity_alias_rows(user_id)
    existing_keys = {
        (_normalise_lookup_key(row.get("alias_value")), str(row.get("kind") or "").strip().lower())
        for row in alias_rows
    }
    if (_normalise_lookup_key(resolved_value), resolved_kind) not in existing_keys:
        supabase_admin.table("entity_aliases").insert({
            "user_id": user_id,
            "kind": resolved_kind,
            "alias_value": resolved_value,
            "canonical_value": resolved_value,
        }).execute()

    return {"kind": resolved_kind, "value": resolved_value}


def merge_entity_manager_items(user_id: str, kind: str, values: list[str], target_value: str) -> dict[str, Any]:
    resolved_kind = str(kind or "").strip().lower()
    selected_values = _dedupe_case_insensitive(_coerce_list(values))
    resolved_target = str(target_value or "").strip()
    if resolved_kind not in ENTITY_MANAGER_KINDS:
        raise ValueError("kind must be person, entity, or tag")
    if not selected_values:
        raise ValueError("select at least one value to merge")
    if not resolved_target:
        raise ValueError("target value is required")

    alias_rows = _load_entity_alias_rows(user_id)
    cluster_values = _collect_related_cluster_values(resolved_kind, selected_values + [resolved_target], alias_rows)
    cluster_keys = {_normalise_lookup_key(value) for value in cluster_values}

    _store_alias_cluster(user_id, resolved_kind, resolved_target, cluster_values, alias_rows)

    def transform_value(current: str) -> Optional[str]:
        text = str(current or "").strip()
        if not text:
            return None if resolved_kind == "person" else ""
        if _normalise_lookup_key(text) in cluster_keys:
            return resolved_target
        return text

    _rewrite_notes_for_kind(user_id, resolved_kind, transform_value)
    return {"kind": resolved_kind, "value": resolved_target}


def rename_entity_manager_item(user_id: str, kind: str, value: str, new_value: str) -> dict[str, Any]:
    resolved_kind = str(kind or "").strip().lower()
    old_value = str(value or "").strip()
    target_value = str(new_value or "").strip()
    if resolved_kind not in ENTITY_MANAGER_KINDS:
        raise ValueError("kind must be person, entity, or tag")
    if not old_value:
        raise ValueError("value is required")
    if not target_value:
        raise ValueError("new_value is required")
    return merge_entity_manager_items(user_id, resolved_kind, [old_value], target_value)


def delete_entity_manager_items(user_id: str, kind: str, values: list[str]) -> dict[str, Any]:
    resolved_kind = str(kind or "").strip().lower()
    selected_values = _dedupe_case_insensitive(_coerce_list(values))
    if resolved_kind not in ENTITY_MANAGER_KINDS:
        raise ValueError("kind must be person, entity, or tag")
    if not selected_values:
        raise ValueError("select at least one value to delete")

    alias_rows = _load_entity_alias_rows(user_id)
    cluster_values = _collect_related_cluster_values(resolved_kind, selected_values, alias_rows)
    cluster_keys = {_normalise_lookup_key(value) for value in cluster_values}

    removable_ids: list[str] = []
    for row in alias_rows:
        row_kind = str(row.get("kind") or "").strip().lower()
        if row_kind != resolved_kind:
            continue
        alias_key = _normalise_lookup_key(row.get("alias_value"))
        canonical_key = _normalise_lookup_key(row.get("canonical_value"))
        if alias_key in cluster_keys or canonical_key in cluster_keys:
            removable_ids.append(str(row.get("id") or "").strip())
    _delete_alias_rows_by_id(removable_ids)

    def transform_value(current: str) -> Optional[str]:
        text = str(current or "").strip()
        if not text:
            return None if resolved_kind == "person" else ""
        if _normalise_lookup_key(text) in cluster_keys:
            return None if resolved_kind == "person" else ""
        return text

    _rewrite_notes_for_kind(user_id, resolved_kind, transform_value)
    return {"kind": resolved_kind, "removed": selected_values}


def _call_extractor(transcript: str) -> Dict[str, Any]:
    return extract_with_llm(transcript)


def _fallback_extract(transcript: str) -> Dict[str, Any]:
    summary = summarise_text(transcript, max_sentences=2)
    title_source = summary or transcript
    title = title_source.split("\n", 1)[0].strip()
    if len(title) > 60:
        title = title[:57].rstrip() + "..."

    return {
        "person_name": None,
        "note_type": "note",
        "title": title,
        "summary": summary or transcript,
        "tags": [],
        "entities": [],
        "due_time": None,
    }


def _normalise_extracted_fields(fields: Dict[str, Any], transcript: str) -> Dict[str, Any]:
    raw = fields if isinstance(fields, dict) else {}

    person_name = raw.get("person_name") if isinstance(raw.get("person_name"), str) else None
    note_type = _coerce_text(raw.get("note_type")).lower()
    summary = _coerce_text(raw.get("summary")) or summarise_text(transcript, max_sentences=2) or transcript
    title = _coerce_text(raw.get("title")) or (summary[:60] if summary else transcript[:60])
    tags = _clean_tags(_coerce_list(raw.get("tags")))[:2]
    entities = _coerce_list(raw.get("entities"))[:5]
    due_time = raw.get("due_time") if isinstance(raw.get("due_time"), str) and raw.get("due_time").strip() else None

    if note_type not in {"reminder", "recommendation", "note", "passive"}:
        note_type = "note"

    return {
        "person_name": person_name,
        "note_type": note_type,
        "title": title,
        "summary": summary,
        "tags": tags,
        "entities": entities,
        "due_time": due_time,
    }


def extract_note_fields(transcript: str) -> Dict[str, Any]:
    text = (transcript or "").strip()
    if not text:
        raise ValueError("text cannot be empty")

    try:
        fields = _call_extractor(text)
    except Exception:
        fields = _fallback_extract(text)

    return _normalise_extracted_fields(fields, text)


def build_text_note_payload(
    transcript: str,
    user_id: str,
    *,
    note_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    text = (transcript or "").strip()
    if not text:
        raise ValueError("text cannot be empty")

    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        raise ValueError("user_id is required")

    normalized = extract_note_fields(text)
    canonicalized = canonicalize_note_metadata(
        resolved_user_id,
        person_name=normalized["person_name"],
        tags=normalized["tags"],
        entities=normalized["entities"],
    )

    return {
        "id": note_id or generate_id(),
        "user_id": resolved_user_id,
        "created_at": created_at or _now_ist_iso(),
        "person_name": canonicalized["person_name"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "raw_text": text,
        "extracted_text": None,
        "image_url": None,
        "memory_type": "text",
        "note_type": normalized["note_type"],
        "tags": canonicalized["tags"],
        "entities": canonicalized["entities"],
        "due_time": normalized["due_time"],
        "calendar_event_id": None,
        "status": "pending",
        "status_note": None,
    }


def build_image_note_update(extracted_text: str, image_url: str, user_id: str) -> Dict[str, Any]:
    text = (extracted_text or "").strip()
    image = (image_url or "").strip() or None

    if not text:
        return {
            "person_name": None,
            "title": "Screenshot memory",
            "summary": "Image saved. OCR could not read enough text.",
            "raw_text": "",
            "extracted_text": "",
            "image_url": image,
            "memory_type": "image",
            "note_type": "passive",
            "tags": [],
            "entities": [],
            "due_time": None,
        }

    normalized = extract_note_fields(text)
    canonicalized = canonicalize_note_metadata(
        user_id,
        person_name=normalized["person_name"],
        tags=normalized["tags"],
        entities=normalized["entities"],
    )
    return {
        "person_name": canonicalized["person_name"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "raw_text": text,
        "extracted_text": text,
        "image_url": image,
        "memory_type": "image",
        "note_type": normalized["note_type"],
        "tags": canonicalized["tags"],
        "entities": canonicalized["entities"],
        "due_time": normalized["due_time"],
    }


def build_document_note_update(preview_text: str, file_url: str, file_name: str, user_id: str) -> Dict[str, Any]:
    text = (preview_text or "").strip()
    file_link = (file_url or "").strip() or None
    base_name = re.sub(r"\.[^.]+$", "", str(file_name or "").strip()).replace("-", " ").replace("_", " ").strip()
    fallback_title = base_name[:60] if base_name else "Document memory"

    if not text:
        return {
            "person_name": None,
            "title": fallback_title,
            "summary": "Document saved. Preview could not be read.",
            "raw_text": "",
            "extracted_text": "",
            "image_url": file_link,
            "memory_type": "document",
            "note_type": "passive",
            "tags": [],
            "entities": [],
            "due_time": None,
        }

    normalized = extract_note_fields(text)
    canonicalized = canonicalize_note_metadata(
        user_id,
        person_name=normalized["person_name"],
        tags=normalized["tags"],
        entities=normalized["entities"],
    )
    return {
        "person_name": canonicalized["person_name"],
        "title": normalized["title"] or fallback_title,
        "summary": normalized["summary"],
        "raw_text": text,
        "extracted_text": text,
        "image_url": file_link,
        "memory_type": "document",
        "note_type": normalized["note_type"],
        "tags": canonicalized["tags"],
        "entities": canonicalized["entities"],
        "due_time": normalized["due_time"],
    }


def process_text_note(
    text: str,
    platform: str = "web",
    message_id: Optional[str] = None,
    user_id: str = "",
) -> Dict[str, Any]:
    """Process a raw text note and store it in Supabase for an authenticated user."""

    transcript = (text or "").strip()
    if not transcript:
        raise ValueError("text cannot be empty")

    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        raise ValueError("user_id is required")

    note = build_text_note_payload(transcript, resolved_user_id)

    try:
        supabase_admin.table("notes").insert(note).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to save note to Supabase: {e}") from e

    return note
