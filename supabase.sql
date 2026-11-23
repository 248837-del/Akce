create table if not exists public.event_counters (
    event_slug text not null,
    cell_key text not null,
    value text not null,
    updated_at timestamptz not null default now(),
    primary key (event_slug, cell_key)
);

alter table public.event_counters enable row level security;

grant usage on schema public to service_role;
grant select, insert, update on table public.event_counters to service_role;
