-- ===========================================================================
-- Upgrade: split student names into three columns
--   * users.first_name   required, shown everywhere in the UI
--   * users.middle_name  optional (SQL NULL when left empty)
--   * users.last_name    optional (SQL NULL when left empty)
--
-- users.full_name is KEPT as the never-null display column for compatibility
-- with legacy screens, audit records and API consumers; the application
-- rebuilds it from the three parts on every insert/update.
--
-- Run this once in the Supabase dashboard:  SQL Editor -> New query -> paste
-- -> Run. It is idempotent and safe to re-run, and it never deletes or alters
-- existing student, course, application or document data. Existing full_name
-- values are split best-effort into the new parts.
--
-- This is the same block that is now part of sql/schema.sql, provided
-- separately so an already-deployed database can be upgraded in place.
-- ===========================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- New columns on public.users (additive, safe to re-run)
-- ---------------------------------------------------------------------------
alter table public.users add column if not exists first_name text;
alter table public.users add column if not exists middle_name text;
alter table public.users add column if not exists last_name text;

-- ---------------------------------------------------------------------------
-- One-time backfill: split existing full_name values into the parts.
-- First token -> first_name, last token -> last_name, anything between ->
-- middle_name. Internal whitespace is collapsed first. Only rows without
-- parts yet are touched, so re-running changes nothing.
-- ---------------------------------------------------------------------------
with normalized as (
  select
    id,
    btrim(regexp_replace(full_name, '\s+', ' ', 'g')) as name
  from public.users
  where first_name is null
)
update public.users u set
  first_name  = nullif(split_part(n.name, ' ', 1), ''),
  last_name   = nullif((regexp_match(n.name, ' ([^ ]+)$'))[1], ''),
  middle_name = nullif((regexp_match(n.name, '^[^ ]+ (.*) [^ ]+$'))[1], '')
from normalized n
where u.id = n.id
  and n.name <> '';

-- Rebuild the never-null display column from the parts for any row that has
-- them now (covers backfilled rows and any written by the new application
-- code). NULL middle / last names are simply omitted.
update public.users set
  full_name = btrim(concat_ws(' ', first_name, middle_name, last_name))
where first_name is not null
   or middle_name is not null
   or last_name is not null;

-- ---------------------------------------------------------------------------
-- NOTE
-- ---------------------------------------------------------------------------
-- The columns are nullable on purpose: a student may legally have no middle
-- name and no (surname) last name in this system, so those fields are stored
-- as SQL NULL, never as empty strings.