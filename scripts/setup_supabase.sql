-- ra-killer Supabase schema
-- Run this in the Supabase SQL editor to create all tables.

-- Enable UUID generation
create extension if not exists "uuid-ossp";

-- 1. Raw events (one row per source per scrape)
create table if not exists raw_events (
    id uuid primary key default uuid_generate_v4(),
    source text not null,
    source_id text not null,
    title text not null,
    event_date date not null,
    start_time time,
    end_time time,
    venue_name text,
    venue_address text,
    artists text[] default '{}',
    cost_display text,
    price_min_cents integer,
    price_max_cents integer,
    source_url text,
    attending_count integer,
    description text,
    image_url text,
    extra jsonb,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(source, source_id)
);

create index if not exists idx_raw_events_date on raw_events(event_date);
create index if not exists idx_raw_events_source on raw_events(source);

-- 2. Canonical deduplicated events
create table if not exists events (
    id uuid primary key default uuid_generate_v4(),
    title text not null,
    event_date date not null,
    start_time time,
    end_time time,
    venue_name text,
    venue_address text,
    artists text[] default '{}',
    cost_display text,
    price_min_cents integer,
    price_max_cents integer,
    source_urls jsonb default '{}',
    sources text[] default '{}',
    attending_count integer,
    description text,
    image_url text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_events_date on events(event_date);
create index if not exists idx_events_venue on events(venue_name);

-- 3. Taste profile
create table if not exists taste_profile (
    id uuid primary key default uuid_generate_v4(),
    category text not null,   -- artist, venue
    name text not null,
    weight real default 1.0,
    source text default 'manual',  -- manual, learned
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(category, name)
);

-- 4. Recommendations
create table if not exists recommendations (
    id uuid primary key default uuid_generate_v4(),
    event_id uuid references events(id) on delete cascade,
    score real not null,
    reasoning text default '',
    telegram_message_id bigint,
    feedback text,  -- 'approve', 'reject', null
    created_at timestamptz default now()
);

create index if not exists idx_recs_event on recommendations(event_id);
create index if not exists idx_recs_message on recommendations(telegram_message_id);

-- 5. Scrape logs
create table if not exists scrape_logs (
    id uuid primary key default uuid_generate_v4(),
    source text not null,
    status text not null,  -- success, error
    event_count integer default 0,
    duration_seconds real default 0,
    error text,
    created_at timestamptz default now()
);

create index if not exists idx_scrape_logs_source on scrape_logs(source, created_at);

-- 6. Alert log (for rate-limiting alerts)
create table if not exists alert_log (
    id uuid primary key default uuid_generate_v4(),
    source text not null,
    message text,
    created_at timestamptz default now()
);

create index if not exists idx_alert_log_source on alert_log(source, created_at);

-- Auto-update updated_at timestamps
create or replace function update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger tr_raw_events_updated
    before update on raw_events
    for each row execute function update_updated_at();

create trigger tr_events_updated
    before update on events
    for each row execute function update_updated_at();

create trigger tr_taste_profile_updated
    before update on taste_profile
    for each row execute function update_updated_at();
