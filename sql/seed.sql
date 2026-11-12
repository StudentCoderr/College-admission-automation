-- ===========================================================================
-- Default course catalogue
-- ===========================================================================
-- This is the SQL equivalent of:
--
--     flask --app wsgi seed-courses
--
-- It is idempotent: existing course codes are left untouched, so re-running it
-- never overwrites changes you made in the admin dashboard.
--
-- The same list is defined in app/data/courses.py. Edit that file (or the admin
-- dashboard) if you want to change the catalogue for future seeds.
--
-- New databases: run sql/schema.sql first. Existing databases: run the upgrade
-- files in sql/ first so the program_type / eligibility / tuition_fee /
-- eligible_qualifications columns exist.
-- ===========================================================================

insert into public.courses
  (code, name, description, duration_years, seats_total, program_type,
   eligibility, tuition_fee, eligible_qualifications, is_active)
values
  ('BTECH-CSE',
   'B.Tech Computer Science & Engineering',
   'Four year undergraduate engineering programme.',
   4, 120, 'degree',
   'Pass in PUC / Class 12 with Physics, Chemistry and Mathematics.',
   85000.00, array['puc'], true),

  ('BTECH-ECE',
   'B.Tech Electronics & Communication Engineering',
   'Four year undergraduate engineering programme.',
   4, 60, 'degree',
   'Pass in PUC / Class 12 with Physics, Chemistry and Mathematics.',
   75000.00, array['puc'], true),

  ('BCOM',
   'Bachelor of Commerce',
   'Three year undergraduate commerce programme.',
   3, 80, 'degree',
   'Pass in PUC / Class 12 in any stream.',
   45000.00, array['puc'], true),

  ('BSC-CS',
   'B.Sc Computer Science',
   'Three year undergraduate science programme.',
   3, 60, 'degree',
   'Pass in PUC / Class 12 with Mathematics.',
   50000.00, array['puc'], true),

  ('DIP-CSE',
   'Diploma in Computer Science and Engineering',
   'Three year diploma in computer science and software engineering.',
   3, 60, 'diploma',
   'Pass in SSLC / Class 10 with Mathematics and Science.',
   25000.00, array['sslc'], true),

  ('DIP-ISE',
   'Diploma in Information Science and Engineering',
   'Three year diploma focused on information systems.',
   3, 60, 'diploma',
   'Pass in SSLC / Class 10 with Mathematics and Science.',
   25000.00, array['sslc'], true),

  ('DIP-ECE',
   'Diploma in Electronics and Communication Engineering',
   'Three year diploma in electronics and communication.',
   3, 60, 'diploma',
   'Pass in SSLC / Class 10 with Mathematics and Science.',
   25000.00, array['sslc'], true),

  ('DIP-MECH',
   'Diploma in Mechanical Engineering',
   'Three year diploma in mechanical systems.',
   3, 60, 'diploma',
   'Pass in SSLC / Class 10 with Mathematics and Science.',
   25000.00, array['sslc'], true),

  ('DIP-CIVIL',
   'Diploma in Civil Engineering',
   'Three year diploma in construction and civil design.',
   3, 60, 'diploma',
   'Pass in SSLC / Class 10 with Mathematics and Science.',
   25000.00, array['sslc'], true),

  ('DIP-COMMERCE',
   'Diploma in Commercial Practice',
   'Three year diploma in commerce and office practice.',
   3, 80, 'diploma',
   'Pass in SSLC / Class 10.',
   18000.00, array['sslc'], true)
on conflict (code) do nothing;
