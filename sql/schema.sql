-- ===========================================================================
-- College Admission Automation System - Supabase / PostgreSQL schema
-- Run this in the Supabase dashboard:  SQL Editor -> New query -> paste -> Run
-- It is idempotent and safe to re-run.
-- ===========================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- USERS  (students and administrators)
-- ---------------------------------------------------------------------------
create table if not exists public.users (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique,
  password_hash text not null,
  full_name     text not null,
  first_name    text,
  middle_name   text,
  last_name     text,
  phone         text,
  role          text not null default 'student' check (role in ('student', 'admin')),
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create unique index if not exists idx_users_email_lower on public.users (lower(email));

-- ---------------------------------------------------------------------------
-- COURSES
-- ---------------------------------------------------------------------------
create table if not exists public.courses (
  id             uuid primary key default gen_random_uuid(),
  code           text not null unique,
  name           text not null,
  description    text,
  duration_years integer not null default 4 check (duration_years between 1 and 10),
  seats_total    integer not null default 60 check (seats_total between 1 and 2000),
  -- Degree or Diploma/Polytechnic. Diploma courses default to 3 years.
  program_type   text not null default 'degree'
                   check (program_type in ('degree', 'diploma')),
  -- Short eligibility statement shown on the course pages, e.g.
  -- "Pass in SSLC / Class 10 with Mathematics and Science".
  eligibility    text,
  -- Annual tuition fee (optional, admin-configurable). NULL means
  -- "contact the admissions office" in the UI.
  tuition_fee    numeric(12,2) check (tuition_fee is null or tuition_fee >= 0),
  is_active      boolean not null default true,
  -- SSLC / PUC / ITI qualifications this course accepts. NULL / empty means
  -- the course is open to all qualifications.
  eligible_qualifications text[],
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- The three columns above are additive. This makes re-running the script on an
-- older database (which already has the courses table) safe and idempotent.
alter table public.courses add column if not exists program_type text not null default 'degree'
  check (program_type in ('degree', 'diploma'));
alter table public.courses add column if not exists eligibility text;
alter table public.courses add column if not exists tuition_fee numeric(12,2)
  check (tuition_fee is null or tuition_fee >= 0);
create index if not exists idx_courses_program_type on public.courses (program_type);
-- Qualification-based eligibility (SSLC / PUC / ITI). Additive: existing
-- courses stay open to all qualifications until an admin configures them.
alter table public.courses add column if not exists eligible_qualifications text[];
create index if not exists idx_courses_eligible_qualifications
  on public.courses using gin (eligible_qualifications);

-- ---------------------------------------------------------------------------
-- USERS: student-lifecycle columns (additive, safe to re-run)
--   status              active | inactive | withdrawn  (the login gate)
--   registration_number admin-assigned college registration reference
--   assigned_course_id  optional admitted course (Degree or Diploma)
--   invite_*            one-time password-setup invitation (never a password)
-- ---------------------------------------------------------------------------
alter table public.users add column if not exists status text not null default 'active'
  check (status in ('active', 'inactive', 'withdrawn'));
alter table public.users add column if not exists registration_number text;
alter table public.users add column if not exists assigned_course_id uuid
  references public.courses(id) on delete set null;
alter table public.users add column if not exists invite_token_hash text;
alter table public.users add column if not exists invite_expires_at timestamptz;
alter table public.users add column if not exists invite_used_at timestamptz;

-- ---------------------------------------------------------------------------
-- USERS: individual name parts (additive, safe to re-run)
--   first_name  required; middle_name / last_name optional (SQL NULL when
--               left empty). full_name stays the never-null display column
--               and is rebuilt from the parts on every application write.
-- ---------------------------------------------------------------------------
alter table public.users add column if not exists first_name text;
alter table public.users add column if not exists middle_name text;
alter table public.users add column if not exists last_name text;

-- One-time backfill: split existing full_name values into the parts
-- (first token -> first_name, last token -> last_name, remainder -> middle).
-- Only touches rows that have no parts yet, so re-running is a no-op.
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

-- Rebuild the display column from the parts wherever the parts exist.
update public.users set
  full_name = btrim(concat_ws(' ', first_name, middle_name, last_name))
where first_name is not null
   or middle_name is not null
   or last_name is not null;

-- Case-insensitive uniqueness for the registration number (NULLs allowed).
create unique index if not exists idx_users_registration_number
  on public.users (lower(registration_number))
  where registration_number is not null;
create index if not exists idx_users_status on public.users (status);

-- Keep the legacy boolean in step with the status column on older databases.
update public.users set status = 'inactive'
  where is_active = false and status <> 'inactive';

-- ---------------------------------------------------------------------------
-- APPLICATIONS
-- ---------------------------------------------------------------------------
create table if not exists public.applications (
  id                  uuid primary key default gen_random_uuid(),
  application_number  text unique,
  user_id             uuid not null references public.users(id) on delete cascade,
  course_id           uuid references public.courses(id) on delete set null,
  status              text not null default 'draft'
                        check (status in ('draft','submitted','under_review',
                                          'correction_requested','approved','rejected')),

  -- personal
  first_name          text,
  middle_name         text,
  last_name           text,
  date_of_birth       date,
  gender              text,
  category            text,
  nationality         text default 'Indian',

  -- contact
  email               text,
  phone               text,
  address_line        text,
  city                text,
  state               text,
  postal_code         text,
  country             text default 'India',

  -- academic
  qualifying_exam     text,
  board_university    text,
  school_name         text,
  -- SSLC / PUC / ITI: one shared field set (the applicant selects one
  -- qualification). institution_name is the school/college/ITI institute;
  -- stream (PUC), trade + affiliation (ITI) are qualification-specific; the
  -- rest are optional. Irrelevant fields are stored NULL.
  institution_name    text,
  stream              text,
  trade               text,
  affiliation         text,
  roll_number         text,
  passing_year        integer,
  marks_obtained      numeric(10,2),
  marks_total         numeric(10,2),
  percentage          numeric(5,2),

  -- review
  admin_note          text,
  submitted_at        timestamptz,
  reviewed_at         timestamptz,
  reviewed_by         uuid references public.users(id) on delete set null,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists idx_applications_user    on public.applications (user_id);
create index if not exists idx_applications_status  on public.applications (status);
create index if not exists idx_applications_course  on public.applications (course_id);

-- Additive application columns (safe to re-run on older installs):
-- middle_name (sql/upgrade_application_names.sql) and the SSLC/PUC/ITI
-- qualification support (sql/upgrade_qualifications.sql).
alter table public.applications add column if not exists middle_name text;
alter table public.applications add column if not exists institution_name text;
alter table public.applications add column if not exists stream text;
alter table public.applications add column if not exists trade text;
alter table public.applications add column if not exists affiliation text;
alter table public.applications add column if not exists roll_number text;

-- Percentage must stay within 0-100 (idempotent constraint add).
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
-- DOCUMENTS  (metadata; the bytes live in Supabase Storage)
-- ---------------------------------------------------------------------------
create table if not exists public.documents (
  id             uuid primary key default gen_random_uuid(),
  application_id uuid not null references public.applications(id) on delete cascade,
  user_id        uuid not null references public.users(id) on delete cascade,
  doc_type       text not null,
  file_name      text not null,
  storage_path   text not null,
  mime_type      text,
  size_bytes     bigint,
  is_verified    boolean not null default false,
  uploaded_at    timestamptz not null default now()
);
create index if not exists idx_documents_application on public.documents (application_id);
create index if not exists idx_documents_user        on public.documents (user_id);

-- ---------------------------------------------------------------------------
-- APPLICATION STATUS HISTORY
-- ---------------------------------------------------------------------------
create table if not exists public.application_status_history (
  id             uuid primary key default gen_random_uuid(),
  application_id uuid not null references public.applications(id) on delete cascade,
  status         text not null,
  note           text,
  changed_by     uuid references public.users(id) on delete set null,
  created_at     timestamptz not null default now()
);
create index if not exists idx_history_application on public.application_status_history (application_id);

-- ---------------------------------------------------------------------------
-- ANNOUNCEMENTS  (public notices shown on the website home page)
-- ---------------------------------------------------------------------------
create table if not exists public.announcements (
  id           uuid primary key default gen_random_uuid(),
  title        text not null,
  body         text,
  tag          text,
  is_published boolean not null default true,
  published_at timestamptz not null default now(),
  created_at   timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- ADMIN AUDIT LOG
-- A tamper-evident trail of important administrative actions (course
-- add/edit/activate, application status changes, document verification,
-- password changes). `entity_id` is text so it can hold a uuid, a course code
-- or an application number without extra casts.
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

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end; $$;

drop trigger if exists trg_users_updated on public.users;
create trigger trg_users_updated before update on public.users
  for each row execute function public.set_updated_at();

drop trigger if exists trg_courses_updated on public.courses;
create trigger trg_courses_updated before update on public.courses
  for each row execute function public.set_updated_at();

drop trigger if exists trg_applications_updated on public.applications;
create trigger trg_applications_updated before update on public.applications
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Application number generator (called via RPC by the Flask backend)
-- Produces values such as ADM-2026-00001
-- ---------------------------------------------------------------------------
create sequence if not exists public.application_number_seq start 1;

create or replace function public.generate_application_number()
returns text language plpgsql as $$
declare
  seq bigint;
begin
  seq := nextval('public.application_number_seq');
  return 'ADM-' || to_char(now(), 'YYYY') || '-' || lpad(seq::text, 5, '0');
end; $$;

-- ===========================================================================
-- Row Level Security
-- The Flask backend uses the service-role key (which bypasses RLS), but we
-- still enable RLS as defence-in-depth for any future direct client access.
-- ===========================================================================
alter table public.users                     enable row level security;
alter table public.courses                   enable row level security;
alter table public.applications              enable row level security;
alter table public.documents                 enable row level security;
alter table public.application_status_history enable row level security;
alter table public.announcements             enable row level security;
alter table public.admin_audit_log           enable row level security;

-- Read-only catalogue is public
drop policy if exists courses_public_read on public.courses;
create policy courses_public_read on public.courses
  for select using (true);

-- Published announcements are public
drop policy if exists announcements_public_read on public.announcements;
create policy announcements_public_read on public.announcements
  for select using (is_published);

-- Students may read only their own rows (requires Supabase Auth JWT).
drop policy if exists users_select_self on public.users;
create policy users_select_self on public.users
  for select using (auth.uid() = id);

drop policy if exists applications_select_own on public.applications;
create policy applications_select_own on public.applications
  for select using (auth.uid() = user_id);

drop policy if exists documents_select_own on public.documents;
create policy documents_select_own on public.documents
  for select using (auth.uid() = user_id);

drop policy if exists history_select_own on public.application_status_history;
create policy history_select_own on public.application_status_history
  for select using (
    exists (
      select 1 from public.applications a
      where a.id = application_id and a.user_id = auth.uid()
    )
  );

-- ===========================================================================
-- Storage bucket for private admission documents
-- ===========================================================================
insert into storage.buckets (id, name, public)
values ('admission-documents', 'admission-documents', false)
on conflict (id) do nothing;

-- Authenticated users may read files they own (path is namespaced by user id
-- when using direct client access). The Flask backend uses signed URLs instead.
drop policy if exists documents_read_own_storage on storage.objects;
create policy documents_read_own_storage on storage.objects
  for select using (
    bucket_id = 'admission-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
