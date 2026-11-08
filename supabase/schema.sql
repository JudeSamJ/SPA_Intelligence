-- SPA Intelligence: database schema (PostgreSQL / Supabase). Idempotent: safe to run more than once.
-- Run it in Supabase -> SQL Editor, or let the app run it at startup (DB_AUTO_MIGRATE=1, default).
--
-- Security: every table has Row Level Security ON and NO policies. Supabase exposes the public schema through its
-- REST API to the "anon" and "authenticated" roles; with RLS on and no policy they can read and write nothing.
-- The app connects as the database owner (DATABASE_URL), which bypasses RLS. Never put DATABASE_URL in the browser.

-- Durable copy of every file the app keeps on disk (PDFs, extractions, reviews, alerts, document sets).
create table if not exists public.app_files (
    path        text primary key,                 -- logical path, e.g. uploads/<hash>.pdf
    kind        text not null,                    -- uploads | cache | reviews | docsets | state
    data        bytea not null,
    size_bytes  integer not null,
    sha256      text not null,
    updated_at  timestamptz not null default now()
);
create index if not exists app_files_kind_idx on public.app_files (kind);

-- One readable row per contract, so people can see the portfolio in the Supabase table editor.
create table if not exists public.contracts (
    id            text primary key check (id ~ '^[0-9a-f]{64}$'),
    name          text not null,
    kind          text not null check (kind in ('sample', 'upload')),
    pages         integer,
    size_bytes    integer,
    status        text not null default 'not_extracted',
    model         text,
    extracted_at  text,
    review_open   integer not null default 0,
    uploaded_at   timestamptz,
    updated_at    timestamptz not null default now()
);

-- Which buyer identity may ask about which contract. Replaces hard-coded buyer keys.
create table if not exists public.buyer_assignments (
    id          bigserial primary key,
    contract_id text not null check (contract_id ~ '^[0-9a-f]{64}$'),
    identity    text not null,                    -- lower-cased email or phone number
    channel     text not null default 'any',      -- any | teams | whatsapp | web | email
    active      boolean not null default true,
    created_by  text not null default '',
    created_at  timestamptz not null default now(),
    unique (contract_id, identity, channel)
);
create index if not exists buyer_assignments_identity_idx on public.buyer_assignments (identity) where active;

-- Every buyer question and what the assistant did. No contract text; the question is truncated by the app.
create table if not exists public.audit_log (
    id            bigserial primary key,
    at            timestamptz not null default now(),
    buyer         text not null,
    contract_id   text not null,
    channel       text not null default 'api',
    question      text not null,
    refused       boolean not null default false,
    reason        text,
    tool_calls    jsonb not null default '[]'::jsonb,
    citation_pages jsonb not null default '[]'::jsonb
);
create index if not exists audit_log_contract_idx on public.audit_log (contract_id, at desc);

-- People who have signed in (AUTH_MODE=supabase). role = null means "signed up, waiting for an admin".
-- user_id is Supabase Auth's user id. Roles are decided HERE, never by anything the user can edit about themselves.
create table if not exists public.app_users (
    user_id       text primary key,
    email         text not null,
    name          text not null default '',
    role          text check (role in ('staff', 'reviewer', 'buyer')),
    created_at    timestamptz not null default now(),
    last_login_at timestamptz,
    updated_by    text not null default ''
);
create unique index if not exists app_users_email_idx on public.app_users (lower(email));

alter table public.app_users         enable row level security;
alter table public.app_files         enable row level security;
alter table public.contracts         enable row level security;
alter table public.buyer_assignments enable row level security;
alter table public.audit_log         enable row level security;
