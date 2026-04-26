import os
from supabase import create_client


def _clean_env(name: str, fallback_name: str | None = None) -> str:
    value = os.getenv(name)
    if not value and fallback_name:
        value = os.getenv(fallback_name)
    cleaned = (value or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _create_supabase_client(url: str, key: str, label: str):
    try:
        return create_client(url, key)
    except Exception as exc:
        raise RuntimeError(
            f"{label} is invalid. In Render, paste the Supabase key exactly, "
            "with no quotes, spaces, or line breaks."
        ) from exc


SUPABASE_URL = _clean_env("SUPABASE_URL")
SUPABASE_ANON_KEY = _clean_env("SUPABASE_ANON_KEY", "SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = _clean_env("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing")
if not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_ANON_KEY (or SUPABASE_KEY) is missing")
if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")

supabase_auth = _create_supabase_client(SUPABASE_URL, SUPABASE_ANON_KEY, "SUPABASE_ANON_KEY")
supabase_admin = _create_supabase_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, "SUPABASE_SERVICE_ROLE_KEY")
