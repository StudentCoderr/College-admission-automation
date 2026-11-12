-- ===========================================================================
-- Migration: SSLC / PUC / ITI qualification support (2026)
--
-- Run this in the Supabase dashboard (SQL Editor -> New query -> paste -> Run)
-- if your database already has the `applications` and `courses` tables from an
-- older deploy. It is idempotent and safe to re-run. Existing applications and
-- courses are preserved untouched (every new column is nullable / defaulted).
--
-- If you prefer, `sql/schema.sql` contains the same statements and is also
-- safe to re-run on an existing project.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1) APPLICATIONS: one shared set of qualification-specific columns. Because a
--    student applies with exactly ONE qualification, each column is reused
--    across the SSLC / PUC / ITI flows rather than duplicating three parallel
--    field sets:
--      institution_name  school (SSLC) / college (PUC) / ITI institute (ITI)
--      board_university  (already exists) - SSLC and PUC boards only
--      stream            PUC only (science / commerce / arts / other)
--      trade             ITI only (trade / specialization)
--      affiliation       ITI only (NCVT / SCVT / other)
--      roll_number       registration / roll number - optional for all three
--    Fields that do not apply to the chosen qualification are stored NULL.
-- ---------------------------------------------------------------------------
alter table public.applications add column if not exists institution_name text;
alter table public.applications add column if not exists stream text;
alter table public.applications add column if not exists trade text;
alter table public.applications add column if not exists affiliation text;
alter table public.applications add column if not exists roll_number text;

-- Percentage must stay within 0-100. The constraint add is wrapped in a DO
-- block so re-running the script on a database that already has it is a no-op
-- (PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS).
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.applications'::regclass
      and conname = 'ck_applications_percentage_range'
  ) then
    alter table public.applications
      add constraint ck_applications_percentage_range
      check (percentage is null or (percentage >= 0 and percentage <= 100));
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 2) COURSES: which qualifications a course accepts. NULL / empty means the
--    course is open to all qualifications (the previous behaviour), so nothing
--    is blocked until the admissions office configures a course. The admin
--    dashboard (Manage Courses) has checkboxes for SSLC / PUC / ITI; the
--    application flow then validates the chosen qualification against these.
-- ---------------------------------------------------------------------------
alter table public.courses add column if not exists eligible_qualifications text[];
create index if not exists idx_courses_eligible_qualifications
  on public.courses using gin (eligible_qualifications);

-- ---------------------------------------------------------------------------
-- Next step: assign eligibility per course in the admin dashboard, or apply
-- the admin dashboard (Manage Courses) to set eligible_qualifications on your
-- real courses. No sample catalogue is bundled.
-- ---------------------------------------------------------------------------