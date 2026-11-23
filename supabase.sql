create table if not exists public.event_counters (
    event_slug text not null,
    cell_key text not null,
    value text not null,
    updated_at timestamptz not null default now(),
    primary key (event_slug, cell_key)
);

alter table public.event_counters enable row level security;
