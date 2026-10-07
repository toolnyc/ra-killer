-- Hotline messages for the two-option IVR.
-- Run in the Supabase SQL editor (DDL cannot be applied via the PostgREST client).
create table if not exists hotline_messages (
    slot text primary key check (slot in ('main', 'party')),
    body text not null,
    updated_by text,
    updated_at timestamptz default now()
);
