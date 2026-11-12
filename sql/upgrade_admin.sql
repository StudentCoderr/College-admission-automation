-- ===========================================================================
-- Upgrade: Admin dashboard support
--   * admin_audit_log  - trail of important administrator actions
--
-- Run this once in the Supabase dashboard:  SQL Editor -> New query -> paste
-- -> Run. It is idempotent and safe to re-run, and it never touches existing
-- student, course, application or document data.
--
-- This is the same block that is now part of sql/schema.sql, provided
-- separately so an already-deployed database can be upgraded in place.
-- ===========================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- ADMIN AUDIT LOG
-- ---------------------------------------------------------------------------
create table if not exists public.admin_audit_log (
  id          uuid primary key default gen_random_uuid(),
  actor_id    uuid references public.users(id) on delete set null,
  actor_email text,
  action      text not null,
  entity_type text,
  entity_id   text,
  details     text,
  ip_address  text,
  created_at  timestamptz not null default now()
);

create index if not exists idx_audit_created on public.admin_audit_log (created_at desc);
create index if not exists idx_audit_actor   on public.admin_audit_log (actor_id);

-- Defence-in-depth: the Flask backend uses the service-role key (which
-- bypasses RLS). No public policy is granted, so direct client access is
-- denied by default and the audit trail stays admin-only.
alter table public.admin_audit_log enable row level security;
