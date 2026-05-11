-- Server-side session storage for Reverie.
-- Run this once in Supabase SQL Editor before deploying the opaque-cookie auth code.

create table if not exists public.user_sessions (
  id text primary key,
  user_id uuid not null,
  email text,
  access_token text not null,
  refresh_token text not null,
  access_expires_at timestamptz,
  expires_at timestamptz not null,
  user_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_seen_at timestamptz,
  revoked_at timestamptz
);

create index if not exists user_sessions_user_id_idx
  on public.user_sessions (user_id);

create index if not exists user_sessions_expires_at_idx
  on public.user_sessions (expires_at);

create index if not exists user_sessions_revoked_at_idx
  on public.user_sessions (revoked_at);

alter table public.user_sessions enable row level security;

-- No public RLS policies are added intentionally.
-- The FastAPI server uses SUPABASE_SERVICE_ROLE_KEY for this table; browser clients
-- must never read or write Supabase tokens directly.
