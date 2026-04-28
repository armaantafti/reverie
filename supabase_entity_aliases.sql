create table if not exists public.entity_aliases (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  kind text not null check (kind in ('person', 'entity', 'tag')),
  alias_value text not null,
  canonical_value text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists entity_aliases_user_kind_alias_idx
  on public.entity_aliases (user_id, kind, lower(alias_value));

create index if not exists entity_aliases_user_kind_canonical_idx
  on public.entity_aliases (user_id, kind, lower(canonical_value));
