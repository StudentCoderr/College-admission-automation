-- ===========================================================================
-- Migration: split applicant names on the applications table (2026)
--
-- Run this in the Supabase dashboard (SQL Editor -> New query -> paste -> Run)
-- if your database already has the `applications` table from an older deploy.
-- It is idempotent and safe to re-run. Existing applications are preserved
-- untouched (the new column is nullable).
--
-- Why: the admission application form now collects First / Middle / Last name
-- (matching registration and the student profile). `applications` already had
-- first_name and last_name; this adds the optional middle_name. The service
-- layer probes for the column and simply omits it on databases where the
-- migration has not been applied yet, so nothing breaks in the meantime.
--
-- If you prefer, `sql/schema.sql` contains the same statement and is also safe
-- to re-run on an existing project.
-- ===========================================================================

alter table public.applications add column if not exists middle_name text;

-- Backfill is intentionally omitted: applications store a per-application
-- snapshot of the applicant's name, and existing rows keep their first/last
-- name unchanged. New rows pick up the middle name from the student profile
-- (or from the applicant typing it) at save time.
