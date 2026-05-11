import hashlib
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from supabase_client import supabase_admin, supabase_auth


APP_SESSION_TTL = timedelta(days=30)
ACCESS_REFRESH_SKEW = timedelta(minutes=2)
SESSION_STORE_ERROR = (
    "Server session storage is not ready. Run supabase_user_sessions.sql "
    "in Supabase SQL Editor, then redeploy."
)

_refresh_locks: dict[str, threading.Lock] = {}
_refresh_locks_guard = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hash_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _get_lock(session_hash: str) -> threading.Lock:
    with _refresh_locks_guard:
        lock = _refresh_locks.get(session_hash)
        if lock is None:
            lock = threading.Lock()
            _refresh_locks[session_hash] = lock
        return lock


def _payload_token(payload: Any) -> str:
    data = jsonable_encoder(payload)
    return str(
        data.get("access_token")
        or (data.get("session") or {}).get("access_token")
        or (data.get("data") or {}).get("access_token")
        or ((data.get("data") or {}).get("session") or {}).get("access_token")
        or ""
    ).strip()


def _payload_refresh_token(payload: Any) -> str:
    data = jsonable_encoder(payload)
    return str(
        data.get("refresh_token")
        or (data.get("session") or {}).get("refresh_token")
        or (data.get("data") or {}).get("refresh_token")
        or ((data.get("data") or {}).get("session") or {}).get("refresh_token")
        or ""
    ).strip()


def _payload_expires_at(payload: Any) -> datetime:
    data = jsonable_encoder(payload)
    expires_at = (
        data.get("expires_at")
        or (data.get("session") or {}).get("expires_at")
        or (data.get("data") or {}).get("expires_at")
        or ((data.get("data") or {}).get("session") or {}).get("expires_at")
    )
    if isinstance(expires_at, (int, float)):
        return datetime.fromtimestamp(float(expires_at), tz=timezone.utc)

    expires_in = (
        data.get("expires_in")
        or (data.get("session") or {}).get("expires_in")
        or (data.get("data") or {}).get("expires_in")
        or ((data.get("data") or {}).get("session") or {}).get("expires_in")
    )
    try:
        return _now() + timedelta(seconds=int(expires_in))
    except Exception:
        return _now() + timedelta(minutes=55)


def _payload_user(payload: Any, access_token: str) -> dict[str, Any]:
    data = jsonable_encoder(payload)
    user = (
        data.get("user")
        or (data.get("session") or {}).get("user")
        or (data.get("data") or {}).get("user")
        or ((data.get("data") or {}).get("session") or {}).get("user")
    )
    encoded = jsonable_encoder(user) if user is not None else None
    if isinstance(encoded, dict) and str(encoded.get("id") or "").strip():
        return encoded

    response = supabase_auth.auth.get_user(access_token)
    user = getattr(response, "user", None) or (response.get("user") if isinstance(response, dict) else None)
    encoded = jsonable_encoder(user) if user is not None else None
    if isinstance(encoded, dict) and str(encoded.get("id") or "").strip():
        return encoded
    raise HTTPException(status_code=401, detail="invalid Supabase session")


def _session_row(session_hash: str) -> dict[str, Any]:
    try:
        result = (
            supabase_admin.table("user_sessions")
            .select("*")
            .eq("id", session_hash)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=SESSION_STORE_ERROR) from exc
    rows = result.data or []
    row = rows[0] if rows else None
    if not isinstance(row, dict):
        raise HTTPException(status_code=401, detail="session not found")
    if row.get("revoked_at"):
        raise HTTPException(status_code=401, detail="session revoked")
    expires_at = _parse_dt(row.get("expires_at"))
    if not expires_at or expires_at <= _now():
        revoke_app_session_hash(session_hash)
        raise HTTPException(status_code=401, detail="session expired")
    return row


def _needs_access_refresh(row: dict[str, Any]) -> bool:
    expires_at = _parse_dt(row.get("access_expires_at"))
    if not expires_at:
        return True
    return expires_at <= _now() + ACCESS_REFRESH_SKEW


def _update_session_tokens(session_hash: str, payload: Any) -> dict[str, Any]:
    access_token = _payload_token(payload)
    refresh_token = _payload_refresh_token(payload)
    if not access_token or not refresh_token:
        raise HTTPException(status_code=401, detail="invalid refreshed session")
    user = _payload_user(payload, access_token)
    row_update = {
        "user_id": str(user.get("id") or "").strip(),
        "email": str(user.get("email") or "").strip() or None,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_at": _iso(_payload_expires_at(payload)),
        "user_payload": user,
        "updated_at": _iso(_now()),
        "last_seen_at": _iso(_now()),
    }
    try:
        (
            supabase_admin.table("user_sessions")
            .update(row_update)
            .eq("id", session_hash)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=SESSION_STORE_ERROR) from exc
    return {**_session_row(session_hash), **row_update}


def create_app_session(payload: Any) -> tuple[str, dict[str, Any]]:
    access_token = _payload_token(payload)
    refresh_token = _payload_refresh_token(payload)
    if not access_token or not refresh_token:
        raise HTTPException(status_code=401, detail="invalid Supabase session")

    user = _payload_user(payload, access_token)
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid Supabase user")

    session_id = new_session_id()
    now = _now()
    row = {
        "id": hash_session_id(session_id),
        "user_id": user_id,
        "email": str(user.get("email") or "").strip() or None,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_at": _iso(_payload_expires_at(payload)),
        "expires_at": _iso(now + APP_SESSION_TTL),
        "user_payload": user,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "last_seen_at": _iso(now),
        "revoked_at": None,
    }
    try:
        supabase_admin.table("user_sessions").insert(row).execute()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=SESSION_STORE_ERROR) from exc
    return session_id, user


def migrate_legacy_refresh_token(refresh_token: str) -> tuple[str, dict[str, Any]]:
    token = str(refresh_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing refresh token")
    try:
        payload = supabase_auth.auth.refresh_session(token)
        return create_app_session(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc


def get_session_user(session_id: str) -> dict[str, Any]:
    session_hash = hash_session_id(str(session_id or "").strip())
    lock = _get_lock(session_hash)
    with lock:
        row = _session_row(session_hash)
        if _needs_access_refresh(row):
            refresh_token = str(row.get("refresh_token") or "").strip()
            if not refresh_token:
                revoke_app_session_hash(session_hash)
                raise HTTPException(status_code=401, detail="missing refresh token")
            try:
                payload = supabase_auth.auth.refresh_session(refresh_token)
                row = _update_session_tokens(session_hash, payload)
            except HTTPException:
                revoke_app_session_hash(session_hash)
                raise
            except Exception as exc:
                revoke_app_session_hash(session_hash)
                raise HTTPException(status_code=401, detail="invalid refresh token") from exc
        else:
            try:
                (
                    supabase_admin.table("user_sessions")
                    .update({"last_seen_at": _iso(_now())})
                    .eq("id", session_hash)
                    .execute()
                )
            except Exception:
                pass

    user = row.get("user_payload")
    if isinstance(user, dict) and str(user.get("id") or "").strip():
        return user
    return {
        "id": row.get("user_id"),
        "email": row.get("email"),
    }


def revoke_app_session(session_id: str) -> None:
    session_hash = hash_session_id(str(session_id or "").strip())
    revoke_app_session_hash(session_hash)


def revoke_app_session_hash(session_hash: str) -> None:
    if not session_hash:
        return
    try:
        (
            supabase_admin.table("user_sessions")
            .update({"revoked_at": _iso(_now()), "updated_at": _iso(_now())})
            .eq("id", session_hash)
            .execute()
        )
    except Exception:
        pass
