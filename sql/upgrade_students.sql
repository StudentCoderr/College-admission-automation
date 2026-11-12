-- ===========================================================================
-- Upgrade: full student lifecycle management
--   * users.status              active | inactive | withdrawn
--   * users.registration_number admin-assigned college registration reference
--   * users.assigned_course_id  optional admitted (Degree / Diploma) course
--   * users.invite_*            one-time password-setup invitation
--
-- Run this once in the Supabase dashboard:  SQL Editor -> New query -> paste
-- -> Run. It is idempotent and safe to re-run, and it never deletes or alters
-- existing student, course, application or document data.
--
-- This is the same block that is now part of sql/schema.sql, provided
-- separately so an already-deployed database can be upgraded in place.
-- ===========================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- New columns on public.users
-- ---------------------------------------------------------------------------
alter table public.users add column if not exists status text not null default 'active'
  check (status in ('active', 'inactive', 'withdrawn'));
alter table public.users add column if not exists registration_number text;
alter table public.users add column if not exists assigned_course_id uuid
  references public.courses(id) on delete set null;
alter table public.users add column if not exists invite_token_hash text;
alter table public.users add column if not exists invite_expires_at timestamptz;
alter table public.users add column if not exists invite_used_at timestamptz;

-- Case-insensitive uniqueness for the registration number (NULLs allowed so
-- self-registered students who have not been given one yet are unaffected).
create unique index if not exists idx_users_registration_number
  on public.users (lower(registration_number))
  where registration_number is not null;
create index if not exists idx_users_status on public.users (status);

-- Keep the legacy boolean in step with the status column.
update public.users set status = 'inactive'
  where is_active = false and status <> 'inactive';

-- ---------------------------------------------------------------------------
-- NOTE on permanent deletion
-- ---------------------------------------------------------------------------
-- applications, documents and application_status_history all reference
-- users(id) with ON DELETE CASCADE, so deleting a student row removes their
-- admission records in one atomic database operation. The Flask backend
-- removes the matching Storage objects (files) before deleting the row.
