-- ===========================================================================
-- Migration: add Diploma / Polytechnic course support (2026)
--
-- Run this in the Supabase dashboard (SQL Editor -> New query -> paste -> Run)
-- if your database already has the `courses` table from an older deploy.
-- It is idempotent and safe to re-run. Existing courses, students and
-- applications are preserved untouched (the applications.course_id foreign key
-- already points at public.courses).
--
-- If you prefer, `sql/schema.sql` contains the same statements and is also
-- safe to re-run on an existing project.
-- ===========================================================================

-- 1) Programme type: 'degree' (default for existing rows) or 'diploma'.
alter table public.courses add column if not exists program_type text not null default 'degree'
  check (program_type in ('degree', 'diploma'));

-- 2) Short eligibility statement shown on the course pages.
alter table public.courses add column if not exists eligibility text;

-- 3) Annual tuition fee in whole currency units (optional, NULL = not published).
alter table public.courses add column if not exists tuition_fee numeric(12,2)
  check (tuition_fee is null or tuition_fee >= 0);

-- 4) Make filtering by programme type fast.
create index if not exists idx_courses_program_type on public.courses (program_type);

-- ---------------------------------------------------------------------------
-- Next step: add your real Degree / Diploma / Polytechnic courses through the
-- admin dashboard (Manage Courses). No sample catalogue is bundled.
-- ---------------------------------------------------------------------------