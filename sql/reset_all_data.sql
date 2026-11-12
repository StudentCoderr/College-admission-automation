-- ===========================================================================
-- DESTRUCTIVE RESET: remove every member, application, course and notice
-- ===========================================================================
-- Use this only when you intend to start the project over. It keeps the
-- database schema, functions, triggers, RLS policies and the storage bucket.
--
-- IMPORTANT: SQL cannot delete the files in Supabase Storage. Empty the private
-- `admission-documents` bucket in the Supabase dashboard, or prefer the safer
-- command that also removes stored files and then creates a fresh admin:
--
--     flask --app wsgi reset-project
--
-- After running this script, create a new administrator with:
--
--     flask --app wsgi create-admin
--
-- ===========================================================================

begin;

truncate table
  public.admin_audit_log,
  public.application_status_history,
  public.documents,
  public.applications,
  public.announcements,
  public.users,
  public.courses
restart identity cascade;

-- Start application numbers at ADM-YYYY-00001 again.
do $$
begin
  if exists (
    select 1
    from pg_class
    where relkind = 'S'
      and relname = 'application_number_seq'
  ) then
    perform setval('public.application_number_seq', 1, false);
  end if;
end $$;

commit;
