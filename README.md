<<<<<<< HEAD
# 🎓 College Admission Automation System

A complete, production-ready **online** admission portal for a college. Students
register, apply, upload documents and track their admission status; administrators
review applications, manage courses and export reports — all through a web browser
with **no local database installation**.

Built with **HTML5 + CSS3 + JavaScript** on the front end, **Python Flask** on the
back end, **Supabase (PostgreSQL + Storage)** as the online database, and designed
for **GitHub + Render** deployment.

---

## Table of contents

1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [Project structure](#project-structure)
4. [How the system is built (module by module)](#how-the-system-is-built-module-by-module)
5. [Prerequisites](#prerequisites)
6. [Step 1 — Create the Supabase project](#step-1--create-the-supabase-project)
7. [Step 2 — Configure environment variables](#step-2--configure-environment-variables)
8. [Step 3 — Run locally](#step-3--run-locally)
9. [Step 4 — Create the administrator and your courses](#step-4--create-the-administrator-and-your-courses)
10. [Administrator login, dashboard & audit log](#administrator-login-dashboard--audit-log)
11. [Testing](#testing)
12. [Deployment — GitHub](#deployment--github)
13. [Deployment — Render](#deployment--render)
14. [Deployment guide (step-by-step)](#deployment-guide-step-by-step)
15. [Security model](#security-model)
16. [Route reference](#route-reference)
17. [REST API (`/api`)](#rest-api-api)
18. [Admin dashboard (static console)](#admin-dashboard-static-console)
19. [Standalone frontend preview](#standalone-frontend-preview)
20. [Troubleshooting](#troubleshooting)

---

## Features

### Student
- Secure registration and login (passwords hashed with scrypt).
- Read-only college and course catalogue with **Degree and Diploma / Polytechnic**
  programmes, searchable and filterable by branch, each with code, duration,
  eligibility, annual tuition fee, available seats and status.
- A dedicated **course detail page** (`/courses/<id>`) to review a course before applying.
- Online admission application form: personal, contact and academic details plus a
  searchable **course picker** (filter by branch / programme type, view details).
- Document upload (marks cards, ID proof, photo, signature, etc.) to a **private**
  Supabase Storage bucket.
- Submit the application and receive a unique application number (`ADM-2026-00001`).
- Application history and real-time status tracking (draft → submitted → under
  review → approved / rejected / correction requested).
- **Profile page** (`/student/profile`) to keep the name and phone number the
  admissions office sees up to date; the login email is fixed.
- Students can only see and edit **their own** applications.

### Administrator
- A **dedicated administrator login page** (`/admin/login`), separate from the
  student portal. Student accounts are refused here, and the shared login never
  grants admin access.
- **Professional responsive dashboard** with sidebar navigation (Dashboard,
  Students, Admission Applications, Polytechnic Courses, Reports,
  **Notifications**, Admin Profile, Logout) and cards for registered students,
  total / pending / approved / rejected applications and active Polytechnic
  courses — loaded live from Supabase, with dependency-free canvas charts
  (status donut, applications by course, monthly trend, course mix).
- **Notifications action centre** (`/admin/notifications`): a single page for
  everything waiting — latest applications, documents pending verification,
  published announcements and the recent admin activity feed.
- **Students management**: a searchable, sortable, paginated table of every
  registered student (name, email, phone, registration number, registration date,
  application count, account status); search by name, email, phone or
  registration/application number; open an individual profile to see the
  student's applications and courses; activate or deactivate an account. Password
  hashes are never displayed.
- **Applications management**: search, sort, filter (course / status / date
  range) and paginate every application; inspect full details (applicant,
  selected branch, eligibility, documents) in the detail view.
- Status history showing **who** changed a status and **when**, with their note.
- Verify or un-verify submitted documents; open them via short-lived signed URLs.
- Approve, reject, request corrections, or mark as under review (with notes);
  every change is saved to Supabase and shown in the student's dashboard.
- Add, update, activate, deactivate and delete **Degree and Diploma / Polytechnic**
  courses; configure the course code, name, duration, eligibility, annual tuition
  fee and seats — only activate the branches the institution actually offers.
  Courses that already have applications are protected from deletion; deactivate
  them instead so historical records stay intact.
- **Applications grouped by course** with per-course application counts and
  remaining available seats (`seats_total − non-draft applications`).
- **Reports** page (course mix, monthly trend, per-course table) and CSV export
  (respecting the active filters).
- **Admin profile** to review your account and securely change your password.
- **Audit log**: important actions (logins, course changes, application status
  changes, document verification, account/password changes) are recorded with the
  actor, time and IP, and surfaced on the Reports and Profile pages.
- The same review/course features are also available as a **static admin console**
  (`admin/`) that consumes the `/api` JSON endpoints.

### Security (summary)
- Passwords hashed with `werkzeug.security` (scrypt).
- All inputs validated and normalised server-side.
- Parameterised queries via the Supabase client — no string-built SQL.
- CSRF protection on every state-changing request.
- Ownership checks so students never touch another student's data.
- **Every admin route verifies the administrator role server-side**; students
  get a 403 even if they type an admin URL. Anonymous visitors are redirected to
  the dedicated admin login.
- The **admin role can never be self-assigned**: registration always creates a
  `student`, and the first administrator is created with the `flask create-admin`
  CLI command (no hard-coded passwords).
- An **audit log** records important administrative actions.
- Secrets in environment variables; the **service-role key never reaches the browser**.
- Private storage bucket + short-lived signed URLs for document access.
- `HttpOnly`, `SameSite=Lax` session cookies (and `Secure` in production).

---

## Tech stack

| Layer      | Technology                                        |
|------------|---------------------------------------------------|
| Front end  | HTML5, CSS3, vanilla JavaScript (Jinja2 templates)|
| Back end   | Python 3.10+, Flask 3, Flask-Login                 |
| Database   | Supabase PostgreSQL                               |
| Files      | Supabase Storage (private bucket)                 |
| Server     | Gunicorn                                          |
| Hosting    | Render                                            |
| Source     | GitHub                                            |
| Tests      | pytest                                            |

---

## Project structure

```
college-admission-automation/
├── app/
│   ├── __init__.py              # Application factory, error handlers, CLI commands
│   ├── config.py                # Environment-driven configuration
│   ├── extensions.py            # Flask-Login + CSRF singletons
│   ├── models/
│   │   └── __init__.py          # User model, status/document constants
│   ├── services/
│   │   ├── supabase_service.py  # All DB + Storage access (one auditable place)
│   │   ├── application_service.py # Application lifecycle + review rules
│   │   ├── document_service.py  # Private upload validation & metadata
│   │   └── errors.py            # Service-level exceptions (mapped to HTTP)
│   ├── api/                     # JSON REST API mounted at /api
│   │   ├── __init__.py          # Blueprint wiring, CORS, API CSRF, error handlers
│   │   ├── responses.py         # Consistent JSON success/failure helpers
│   │   ├── decorators.py        # JSON 401/403 auth decorators
│   │   ├── serializers.py       # Row -> JSON shapes (never exposes password_hash)
│   │   ├── utils.py             # Body parsing, payload normalisation, pagination
│   │   ├── access.py            # Record-level authorization helper
│   │   ├── auth.py              # /register /login /logout /me /csrf
│   │   ├── courses.py           # /courses /announcements
│   │   ├── applications.py      # Application CRUD + submit + track
│   │   ├── documents.py         # Upload + signed-URL access
│   │   └── admin.py             # Admin review, stats, verification
│   ├── routes/
│   │   ├── main.py              # Public pages + /healthz
│   │   ├── auth.py              # Register / login / logout (HTML)
│   │   ├── student.py           # Student dashboard, apply, upload, submit
│   │   └── admin.py             # Admin login, dashboard, students, review, courses, reports, profile, CSV
│   ├── utils/
│   │   ├── security.py          # CSRF + role decorators
│   │   └── validators.py        # Server-side input validation
│   ├── templates/               # Jinja2 HTML5 templates
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── courses.html
│   │   ├── course_detail.html
│   │   ├── auth/{login,register}.html
│   │   ├── student/{dashboard,apply,_form_fields,application_detail}.html
│   │   ├── admin/
│   │   │   ├── base.html        # Admin shell (sidebar nav + topbar)
│   │   │   ├── login.html       # Dedicated administrator login
│   │   │   ├── dashboard.html   # Cards + charts + recent applications
│   │   │   ├── students.html    # Students management table
│   │   │   ├── student_detail.html
│   │   │   ├── reports.html
│   │   │   ├── profile.html
│   │   │   ├── applications.html
│   │   │   ├── application_detail.html
│   │   │   └── courses.html
│   │   └── errors/error.html
│   └── static/
│       ├── css/style.css
│       └── js/{main,admin}.js   # admin.js: sidebar toggle + canvas charts
├── frontend/                    # Standalone HTML/CSS/JS front end (see below)
│   ├── index.html               # Homepage (hero, courses, announcements)
│   ├── register.html            # Student registration
│   ├── login.html               # Login (student + admin)
│   ├── courses.html             # Course listing with eligibility & fees
│   ├── admission.html           # Multi-section application form (6 steps)
│   ├── student_dashboard.html   # Profile, summary, application status
│   ├── status.html              # Public application tracking
│   ├── admin_dashboard.html     # Statistics + application table
│   ├── application_details.html # Administrator review page
│   └── assets/
│       ├── css/{base,components,pages}.css
│       └── js/{config,sample-data,api,validation,auth,ui,components,main}.js
│           └── pages/{home,courses,auth-pages,admission,
│                      student-dashboard,status,admin-dashboard,
│                      application-details}.js
├── sql/
│   ├── schema.sql               # Tables, indexes, triggers, RLS, storage bucket
│   ├── upgrade_diploma.sql      # Migration: add Degree/Diploma course columns
│   ├── upgrade_admin.sql        # Migration: add the admin_audit_log table
│   ├── upgrade_students.sql     # Migration: student lifecycle (status, reg no, invites)
│   ├── reset_all_data.sql       # Destructive: empty every table (start over)
│   └── seed.sql                 # Default Degree + Diploma course catalogue
├── admin/                       # Static admin console (HTML/CSS/JS)
│   ├── index.html               # Dashboard, students, applications, courses, reports, profile
│   ├── login.html               # Admin sign-in (guarded by the API, not the page)
│   └── assets/
│       ├── css/admin.css
│       └── js/{config,api,ui,auth,dashboard,overview,students,reports,profile,detail,courses,app}.js
├── scripts/
│   └── demo_server.py           # Run the whole app on an in-memory database (seeded courses)
├── tests/                       # pytest suite (uses an in-memory fake DB)
│   ├── conftest.py
│   ├── fake_supabase.py
│   ├── test_auth.py
│   ├── test_student.py
│   ├── test_admin.py
│   ├── test_admin_enhanced.py   # Admin login, students, reports, profile, audit
│   ├── test_student_management.py # Add/edit/status/invite/delete lifecycle
│   ├── test_api.py
│   ├── test_validators.py
│   └── test_public.py
├── wsgi.py                      # Gunicorn / WSGI entry point
├── Procfile                     # Render process definition
├── render.yaml                  # Render Blueprint (infrastructure as code)
├── requirements.txt
├── .env.example
├── .gitignore
├── DEPLOYMENT.md                # Step-by-step production deployment guide
└── README.md
```

---

## How the system is built (module by module)

The project was assembled in independent, testable modules. Run the tests after
each module to confirm it works before moving on.

### Module 1 — Configuration & security primitives
`app/config.py`, `app/utils/security.py`, `app/utils/validators.py`, `app/extensions.py`

- All configuration comes from environment variables.
- `CSRFProtect` issues a per-session token and rejects any POST/PUT/PATCH/DELETE
  without a matching token.
- `admin_required` / `student_required` decorators enforce role-based access.
- Validators normalise and check every field (email, phone, password, dates,
  numbers, file extensions).

**Verify:** `pytest tests/test_validators.py -q`

### Module 2 — Data access layer
`app/services/supabase_service.py`

- One class wraps every database and storage operation.
- Views never build queries themselves, which keeps access control and query
  construction in a single, auditable place.
- Storage uploads go to a private bucket and are read back only through
  short-lived signed URLs.

**Verify:** covered by the fake service in `tests/fake_supabase.py`, exercised by
all route tests.

### Module 3 — Authentication
`app/routes/auth.py`, `app/models/__init__.py`

- Registration validates input, hashes the password with scrypt, and rejects
  duplicate emails. Registration **always creates a student**; it never accepts
  a role from the browser.
- Login uses a generic "invalid email or password" message to avoid user
  enumeration, blocks deactivated accounts, and only follows relative redirects.

**Verify:** `pytest tests/test_auth.py -q`

### Module 4 — Student area
`app/routes/student.py`

- Draft creation, editing while editable, document upload/delete, submission
  (requires a marks card), and ownership checks on every route.

**Verify:** `pytest tests/test_student.py -q`

### Module 5 — Administrator area
`app/routes/admin.py`, `app/templates/admin/**`

- A **dedicated admin login** (`/admin/login`) that admits only `admin` accounts.
- Dashboard cards (students, applications by status, active Polytechnic courses)
  with canvas charts, all loaded live from Supabase.
- Students management (search/sort/filter/paginate, profile, account status).
- Application search/filter, review actions with mandatory notes on
  rejection/correction, document verification, course CRUD, reports and CSV export.
- Admin profile with a secure password change.
- Every important action is written to the **audit log** (`_audit()` helper).

**Verify:** `pytest tests/test_admin.py tests/test_admin_enhanced.py -q`

### Module 6 — Front end
`app/templates/**`, `app/static/**`

- Shared `base.html` layout with role-aware navigation and flash messages.
- `admin/base.html` is the administrator shell with sidebar navigation; all admin
  pages extend it.
- A reusable `student/_form_fields.html` powers both the apply and edit forms.
- `main.js` only improves UX (percentage auto-fill, double-submit guard); all
  validation remains on the server.
- `admin.js` adds the sidebar toggle and dependency-free canvas charts.

**Verify:** `pytest tests/test_public.py -q`

### Module 7 — Admin console & demo server
`admin/**`, `scripts/demo_server.py`, `app/api/admin.py`

- `app/api/admin.py` adds administrator-only JSON endpoints: sorted, filtered,
  date-ranged, paginated application listing with a whitelist of sort columns,
  detail views that enrich status history with the reviewer's name/role and
  attach short-lived signed URLs to documents, course CRUD + activation toggle,
  **students list/detail/status, extended stats and the audit log**, and a CSV
  export that honours the same filters.
- `admin/` is a dependency-free HTML/CSS/JS console that consumes exactly those
  endpoints: login gate, **Dashboard overview**, **Students management**, the
  searchable/sortable/filterable applications table with pagination, the detail
  drawer with document verification and review actions, course management,
  **Reports** (status/course breakdowns + audit trail), an **Admin Profile** with a
  secure password change, and CSV export. It bootstraps its CSRF token from
  `/api/auth/csrf` and sends it with every state-changing call.
- `scripts/demo_server.py` boots the entire application with an in-memory
  database (CSRF enabled) so the console can be exercised with no Supabase
  project. It seeds the bundled course catalogue; set
  `ADMIN_EMAIL`/`ADMIN_PASSWORD` to create one administrator at startup. No
  demo members or applications are seeded.

### Module 8 — Student lifecycle management
`app/routes/admin.py`, `app/routes/auth.py`, `app/services/supabase_service.py`

- Administrators can **add a student** with full name, email, phone, registration
  number, an optional assigned course and an account status. Email and
  registration number must be unique (checked server-side and surfaced as field
  errors). The account is created with an **unusable random password** and a
  **one-time password-setup link** (7-day expiry, single use). Only the SHA-256
  hash of the token is stored; the raw link is shown to the admin once. Admins
  never see or set a student's password.
- **Edit** a student's details and status; **deactivate**, **reactivate** or mark
  as **withdrawn** from the profile page. Inactive/withdrawn students are signed
  out and cannot sign in or create/submit new applications, while their
  historical applications and decisions are preserved.
- **Permanently delete** requires a preview page listing the affected records, a
  typed `DELETE` confirmation and a reason. Stored files are removed before the
  row, and foreign keys cascade. Deleting an admin or your own account is
  refused.
- Every action is written to the audit log with the actor, target and reason.

**Verify:** `pytest tests/test_student_management.py tests/test_admin_enhanced.py -q`

**Run everything:** `pytest -q` (expect **248 passed**)

---

## Prerequisites

- Python 3.10–3.12
- A free [Supabase](https://supabase.com) account
- A [GitHub](https://github.com) account
- A [Render](https://render.com) account (for deployment)
- Git (optional but recommended)

---

## Step 1 — Create the Supabase project

1. Go to <https://supabase.com> → **New project**. Choose a name, a strong database
   password, and a region close to your users. Wait for provisioning to finish.
2. Open **SQL Editor → New query**, paste the entire contents of
   [`sql/schema.sql`](sql/schema.sql), and click **Run**.
   This creates the tables, indexes, triggers, the application-number function,
   row-level-security policies, and the private `admission-documents` bucket.
   The `courses` table includes the Degree/Diploma columns (`program_type`,
   `eligibility`, `tuition_fee`).
3. **Already have an existing database?** Run
   [`sql/upgrade_diploma.sql`](sql/upgrade_diploma.sql) instead (or as well) — it
   adds only the new course columns and index, is idempotent, and preserves all
   existing students, courses and applications.
4. (Optional) Run [`sql/seed.sql`](sql/seed.sql) to insert the default course
   catalogue (4 Degree + 6 Diploma programmes). It is idempotent and never
   overwrites courses you have edited. You can also run
   `flask --app wsgi seed-courses` after configuring `.env`. No demo members or
   applications are created.
5. Open **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `SUPABASE_ANON_KEY`
   - **service_role** key → `SUPABASE_SERVICE_ROLE_KEY` 🔒 *(server-side only)*
6. Confirm the private bucket exists under **Storage** (bucket name
   `admission-documents`, **not** public).

---

## Step 2 — Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

```dotenv
SECRET_KEY=<output of: python -c "import secrets;print(secrets.token_hex(32))">
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-public-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=admission-documents
FLASK_ENV=development
MAX_CONTENT_LENGTH=5242880
SIGNED_URL_EXPIRES_IN=300
# JSON API: require X-CSRF-Token on state-changing requests (recommended)
API_CSRF_ENABLED=true
# Browser origins allowed to call the API with credentials
# (8080 = static frontend, 8081 = static admin console stand-alone mode)
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:8081,http://127.0.0.1:8081
```

> 🔒 Never commit `.env`. It is already listed in `.gitignore`.

---

## Step 3 — Run locally

### Quick start on Windows (no cloud database needed)

The app can run entirely from the persistent local database in
`instance/local_db.json`. This is the fastest way to register, log in, browse
courses and use the admin area when Supabase is not configured or unreachable.

1. Make sure `.env` contains `USE_LOCAL_DB=true`.
2. Double-click **`START_APP.bat`** in the project folder.
3. Open <http://localhost:5000> in your browser (the script opens it for you).
4. See [`START_HERE.txt`](START_HERE.txt) for the local admin/student login and
   how to change the admin password.

Keep the black command window open while using the site. The local data survives
restarts and is stored in `instance/local_db.json`; uploaded documents go to
`instance/uploads/`. Local mode assumes **one** app process — close old server
windows before starting a new one, and do not enable the Flask reloader or run
multiple workers against the same file. To switch to Supabase later, set
`USE_LOCAL_DB=false` and fill in the Supabase keys.

> Do **not** open `frontend/index.html` directly from the file system. That file
> is a static preview and cannot register or log in without the backend running.
> Use <http://localhost:5000> or start the backend first.

### Manual start (any platform)

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the development server
python wsgi.py
```

Open <http://localhost:5000> in your browser.

Health check: <http://localhost:5000/healthz> returns
`{"status": "ok", "supabase_configured": true}`.

---

## Step 4 — Create the administrator and load your courses

The project ships with **no members**. The course catalogue is bundled but is
not inserted automatically. The first administrator is created by you — no old
password is needed, because there is nothing to reset yet.

**Administrator** account (required for the admin area):

The initial administrator is provisioned with the **`create-admin`** CLI
command. It reads `ADMIN_EMAIL`, `ADMIN_FULL_NAME` and `ADMIN_PASSWORD` from
the environment (or your `.env` file) and falls back to secure hidden input
prompts for anything missing. The password is **never** accepted from the
command line, never echoed to the console, and never hard-coded or logged —
it is hashed with Werkzeug's `scrypt` before it is written to the `users`
table.

Add these to your `.env` (see `.env.example`):

```ini
ADMIN_EMAIL=admin@yourcollege.edu
ADMIN_FULL_NAME=System Administrator
# Choose your own strong password; never commit it to source control.
ADMIN_PASSWORD=your-strong-password-here
```

Then provision the account:

```powershell
.\venv\Scripts\python.exe -m flask --app wsgi create-admin
```

The command is **idempotent and non-destructive**:

- **First run** — creates the administrator account.
- **Re-run with the same email** — does nothing and never overwrites the
  password (exit code 0; use `--reset-password` to rotate it).
- **Email already belongs to a user** — that account is promoted to
  administrator *without changing its password*; add `--reset-password` to
  also set a new one.
- **`--reset-password`** — rotates the password of an existing administrator.

Registration (both the web form at `/register` and the JSON API) always
creates `role = "student"` — there is **no way to self-assign the admin role**,
which is enforced by the test suite. Sign in at the dedicated page
**`/admin/login`**.

### Load the course catalogue

After the administrator exists, insert the bundled courses:

```powershell
.\venv\Scripts\python.exe -m flask --app wsgi seed-courses
```

Or run [`sql/seed.sql`](sql/seed.sql) in the Supabase SQL editor. Both are
idempotent by course code and never overwrite courses you have edited. The
default list is in [`app/data/courses.py`](app/data/courses.py).

### Rotating or resetting the administrator password

If the initial password was ever exposed, rotate it from the server (never
from a browser console):

```powershell
$env:ADMIN_EMAIL="admin@yourcollege.edu"
$env:ADMIN_PASSWORD="A-Strong-N3w-Passw0rd"
.\venv\Scripts\python.exe -m flask --app wsgi create-admin --reset-password
Remove-Item Env:ADMIN_EMAIL, Env:ADMIN_PASSWORD -ErrorAction SilentlyContinue
```

Admins can also change their own password (with the current password required)
at the static admin console: **`/admin-console` → profile → Change password**,
which goes through the server-side `/api/admin/profile/password` endpoint.

### Remove every existing member and start over

If you do not know the current administrator password, or you want a completely
blank project, use the destructive `reset-project` command. It deletes **every**
account (students and admins), every application, every course, every document
and every uploaded file, then asks you to set a **new** administrator email,
full name and password. The schema and the storage bucket are kept.

```powershell
.\venv\Scripts\python.exe -m flask --app wsgi reset-project
```

You must type `RESET` to confirm. The command never prints the password, and it
does **not** need the old password. For scripted use:

```powershell
$env:ADMIN_EMAIL="admin@yourcollege.edu"
$env:ADMIN_FULL_NAME="Admissions Administrator"
$env:ADMIN_PASSWORD="A-Strong-N3w-Passw0rd"
.\venv\Scripts\python.exe -m flask --app wsgi reset-project --yes
Remove-Item Env:ADMIN_EMAIL, Env:ADMIN_FULL_NAME, Env:ADMIN_PASSWORD -ErrorAction SilentlyContinue
```

Prefer SQL? [`sql/reset_all_data.sql`](sql/reset_all_data.sql) empties the
tables, but it cannot delete files in Supabase Storage — empty the private
`admission-documents` bucket separately, then run `flask create-admin`.

### Verifying the administrator login and student lockout

1. Start the app — `.\venv\Scripts\python.exe wsgi.py` — and open
   <http://localhost:5000/admin/login>.
2. Sign in with `admin34@edu.in` and the initial password; you should land on
   the admin dashboard (`/admin/dashboard`).
3. Sign out. Register (or log in as) an ordinary student and open
   <http://localhost:5000/admin/dashboard> directly — the request is
   redirected to the admin login. Signing in to `/admin/login` with a student
   account shows *"This account does not have administrator access."*

**Student** account: register through the UI at `/register`.

### Suggested manual test data

| Role    | Email                     | Password       |
|---------|---------------------------|----------------|
| Admin   | *(the email you entered)* | *(you choose)* |
| Student | `student@college.edu`     | *(you choose)* |

After signing in as the administrator, open **Manage Courses** and add your real
programmes — the catalogue starts empty.

---

## Diploma / Polytechnic courses

The catalogue holds **both Degree and Diploma / Polytechnic** programmes in the
single `courses` table, so existing students and applications are untouched and
each application still links to a course by `course_id`.

### What a course stores

| Field            | Meaning                                                             |
|------------------|---------------------------------------------------------------------|
| `code`           | Unique course code (e.g. `DIP-CSE`)                                 |
| `name`           | Course name / branch                                                |
| `program_type`   | `degree` or `diploma` (drives the badge and the branch filter)      |
| `duration_years` | Default **3** for regular post-SSLC/10th-entry diploma programmes   |
| `eligibility`    | Short eligibility statement shown to students                       |
| `tuition_fee`    | Annual tuition fee (optional; blank = "contact the admissions office") |
| `seats_total`    | Total sanctioned seats                                              |
| `description`    | Longer free-text description                                        |
| `is_active`      | Active/Inactive — **inactive courses are hidden from students**     |
| `eligible_qualifications` | SSLC / PUC / ITI values this course accepts. NULL or empty = open to every qualification; configured in **Manage Courses** and enforced at application time. |

### Database migration

- New databases: `sql/schema.sql` already contains the columns.
- Existing databases: run **`sql/upgrade_diploma.sql`** once (idempotent). It only
  adds `program_type`, `eligibility`, `tuition_fee` and an index — no data is
  changed or deleted.
- For the enhanced administrator area (audit log), also run
  **`sql/upgrade_admin.sql`** once. It creates `public.admin_audit_log` and is
  safe to re-run.
- For full student lifecycle management, also run
  **`sql/upgrade_students.sql`** once. It adds `status`, `registration_number`,
  `assigned_course_id` and the `invite_*` columns to `public.users`, backfills
  `status` from the legacy `is_active` flag, and adds supporting indexes. It is
  additive and safe to re-run.
- For SSLC / PUC / ITI qualification support, run **`sql/upgrade_qualifications.sql`**
  once (idempotent). It adds `institution_name`, `stream`, `trade`, `affiliation`
  and `roll_number` to `public.applications` plus `eligible_qualifications` to
  `public.courses`, and adds a percentage range check. Existing rows are
  untouched; a course with no `eligible_qualifications` stays open to all
  qualifications until you configure it in **Manage Courses**.

### Default course catalogue

The repository bundles 4 Degree and 6 Diploma programmes in
[`app/data/courses.py`](app/data/courses.py). Load them with either:

```powershell
.\venv\Scripts\python.exe -m flask --app wsgi seed-courses
```

or by running [`sql/seed.sql`](sql/seed.sql) in the Supabase SQL editor.

Both are **idempotent by course code**: a code that already exists is skipped,
so edits you make in **Manage Courses** are never overwritten. No demo students
or administrator passwords are bundled. Edit `app/data/courses.py` to change
the default list for future seeds, or edit courses directly in the dashboard.

### Student experience

- **`/courses`** — all active courses as responsive cards with a search box,
  a Degree/Diploma filter and a **course-status** filter (`?program_type=diploma`,
  `?status=all` to include closed courses). Cards show name, code, programme type,
  duration, eligibility, fee and seats read live from Supabase; closed courses
  are marked and never offer an "Apply now" action.
- **`/courses/<id>`** — full course detail page (code, duration, eligibility, fee,
  seats, status) with an **Apply** call to action.
- **`/student/apply`** — a searchable course picker (filter by branch/programme
  type, "View details" link, radio select). The server re-checks the selection:
  a student can never apply for an **inactive or nonexistent** course.
- **`/student/profile`** — update the name/phone shown to the admissions office;
  the login email is read-only. Password-protected forms also show a live
  **password strength meter** and a match hint.

### Administrator experience

- **Manage Courses** (`/admin/courses`) and the static console **Courses** tab:
  create/edit a course with type, duration, seats, annual fee and eligibility;
  activate/deactivate, or permanently delete a course that has no applications;
  see per-course application counts and available seats.
- **Admin dashboard** — an *Applications by course* table grouped per course.

---

## Administrator login, dashboard & audit log

### Separate administrator login

| Page | Path | Who it admits |
|------|------|---------------|
| Student login | `/login` | Any active account (admins are redirected to the admin dashboard) |
| **Admin login** | **`/admin/login`** | **Only accounts with `role = 'admin'`** |

- A student account is refused at `/admin/login` with a clear message and is
  **not** signed in.
- Anonymous visitors who open any `/admin/...` page are redirected to
  `/admin/login?next=...` and returned to where they were heading after login.
- Passwords are checked before the role, and the failure message is generic, so
  the page never reveals whether an email address exists.

### Dashboard

The dashboard reads everything live from Supabase (no hard-coded numbers) and
shows six cards — registered students, total / pending / approved / rejected
applications and active Polytechnic courses — plus dependency-free canvas charts
(applications by status, applications by course). The Recent applications table
links straight into the review workflow.

### Students management

`/admin/students` lists every registered student with **name, email, phone,
registration number, registration date, application count and account status**.
Search by name, email, phone or **registration/application number**; filter by
Active / Inactive / Withdrawn; sort by registration date, name, email or status;
page through the results.

From here an administrator can:

- **Add Student** — create the record (full name, email, phone, registration
  number, assigned course, status) with duplicate email/registration-number
  checks. The account is created without a usable password and a **one-time
  password-setup link** is generated for you to share out of band.
- **View / Edit** — open the full profile (details, assigned course, every
  application) or edit details and status.
- **Deactivate / Reactivate / mark Withdrawn** — inactive and withdrawn accounts
  cannot sign in or start new applications, but their history is preserved.
- **Resend setup link** — issue a fresh one-time password link.
- **Permanently delete** — a preview page lists the affected applications and
  documents; a typed `DELETE` confirmation and a reason are required first.

Admins never see or set a student's password. Your own account and other
administrator accounts cannot be deleted here, and every action is audited.

> **Registration number:** you can store a college-assigned
> `registration_number`, and the ADM number a student receives on submission
> (`ADM-YYYY-NNNNN`) is still searchable as a fallback reference.

### Reports & profile

- **Reports** (`/admin/reports`) — status/course-mix/monthly charts, a per-course
  table and the recent administrative activity feed, with a CSV export that
  honours the active filters.
- **Admin profile** (`/admin/profile`) — your account details, a secure password
  change (current password required) and your own recent activity.

### Audit log

`public.admin_audit_log` records the actor, action, entity, details, IP address
and time for important events: `admin_login`, `application_status_change`,
`document_verify`, `course_create` / `course_update` / `course_activate` /
`course_deactivate` / `course_delete`, `student_activate` / `student_deactivate` and
`admin_password_change`. The table has RLS enabled and **no public policy**, so
it is readable only by the backend (service role).

---

## Testing

The suite runs entirely offline using an in-memory fake for Supabase
(`tests/fake_supabase.py`), so it needs no credentials and makes no network calls.

```bash
pytest -q                 # run everything
pytest tests/test_auth.py -q
pytest tests/test_student.py -q
pytest tests/test_admin.py -q
pytest tests/test_admin_enhanced.py -q
pytest tests/test_student_management.py -q
pytest tests/test_api.py -q
pytest -q -k validation   # run a subset
```

Expected result: **248 passed**.

### Manual end-to-end checklist

1. Register a student, log out, log back in.
2. Start an application, fill every section, save the draft.
3. Upload a marks card (PDF/JPG/PNG) and submit → note the application number.
4. Open **`/admin/login`** and sign in with the account from `flask create-admin`.
5. Check the dashboard cards and charts, then open **Students** — find the student
   (try searching by name and by the application number).
6. Open the application, verify documents, request a correction with a note;
   confirm the student sees it.
7. Re-submit, then approve the application; confirm the change on the student side.
8. Visit **Reports** and **Admin Profile**; change your password and confirm the
   new one works. The audit feed should list your recent actions.
9. Export the CSV and open it in a spreadsheet.
10. Confirm a student attempting `/admin/...` receives **403**, an anonymous
    visitor is redirected to `/admin/login`, and opening another student's
    application returns **404**.
11. Prefer no Supabase yet? Run `.\venv\Scripts\python.exe scripts\demo_server.py`
    and repeat the checklist against `http://localhost:5010`. The in-memory
    database starts **empty**; set `ADMIN_EMAIL`, `ADMIN_FULL_NAME` and
    `ADMIN_PASSWORD` before starting it if you want an administrator created
    automatically. The static console is at `/admin-console/`.

---

## Deployment — GitHub

```bash
git init
git add .
git commit -m "College Admission Automation System"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Before pushing, confirm `.env` is **not** staged (`git status`). The `.gitignore`
already excludes it.

---

## Deployment — Render

### Option A — Blueprint (recommended, uses `render.yaml`)

1. Push the repo to GitHub.
2. In Render: **New + → Blueprint**, select the repository, and click **Apply**.
3. Render prompts for the `sync: false` variables. Paste your Supabase values:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
4. `SECRET_KEY` is generated automatically. `SUPABASE_STORAGE_BUCKET` and the
   size/expiry limits are set by the blueprint.
5. Click **Deploy**. Render runs `pip install -r requirements.txt` and starts
   Gunicorn with `wsgi:app`.

### Option B — Manual web service

1. **New + → Web Service** → connect the GitHub repo.
2. **Environment:** Python 3.
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:**
   `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
5. **Health check path:** `/healthz`
6. Add the environment variables from Step 2 (leave `FLASK_ENV=production`).

### Post-deploy

- Follow the full walkthrough in **[DEPLOYMENT.md](DEPLOYMENT.md)** — it covers
  project layout, requirements, Supabase setup, GitHub, Render, production
  environment variables, the end-to-end test checklist, and common errors.
- Open `https://<your-app>.onrender.com/healthz` — it must report
  `"supabase_configured": true`.
- Create the first admin once (Render **Shell**). The catalogue starts empty;
  add your real courses in **Manage Courses** afterwards:
  ```bash
  flask --app wsgi create-admin
  ```
  If the database already contains members you no longer control, run
  `flask --app wsgi reset-project` to wipe it and set a new administrator.
- Because `FLASK_ENV=production`, session cookies are marked `Secure` (HTTPS-only).
- Free Render instances sleep after inactivity; the first request may take ~30s.

---

## Security model

| Requirement                              | How it is met                                                                 |
|------------------------------------------|-------------------------------------------------------------------------------|
| Hash passwords securely                  | `werkzeug.security.generate_password_hash(..., method="scrypt")`              |
| Validate all inputs on the server        | `app/utils/validators.py`, used by every POST route                           |
| Protect against SQL injection            | Parameterised Supabase client calls; no concatenated SQL                      |
| Prevent unauthorised access              | `@login_required` + `@admin_required` / `@student_required`                   |
| Students see only their own applications | Ownership check in `_get_owned_application` and document routes (else 404)    |
| Secrets in environment variables         | `.env` locally, Render env vars in production; `.env` git-ignored             |
| Never expose the service-role key        | Only the Flask server uses it; the browser receives rendered HTML only        |
| Secure document storage                  | Private bucket + short-lived signed URLs (`SIGNED_URL_EXPIRES_IN`)            |
| CSRF protection                          | `CSRFProtect` before-request hook, token on every form                        |
| Session hardening                        | `HttpOnly`, `SameSite=Lax`, `Secure` in production, strong session protection |
| User enumeration resistance              | Generic login error message                                                   |
| Open-redirect prevention                 | Only relative `next` URLs are followed                                        |
| API authentication failures              | JSON `401`/`403` (never an HTML redirect); role decorators in `app/api`       |
| API CSRF                                 | `X-CSRF-Token` on `/api` writes, bootstrapped via `GET /api/auth/csrf`        |
| No secrets in logs                       | Passwords/hashes are never logged; login failures log the email only         |

**Defence in depth:** RLS policies are enabled on every table in `schema.sql`.
The backend uses the service-role key (which bypasses RLS) for trusted server
operations, while the policies protect any future direct client access.

---

## Route reference

| Method        | Path                                          | Access    | Purpose                        |
|---------------|-----------------------------------------------|-----------|--------------------------------|
| GET           | `/`                                           | Public    | Home / course highlights       |
| GET           | `/courses`                                    | Public    | Course catalogue (Degree + Diploma; `?program_type=`, `?status=active\|all`) |
| GET           | `/courses/<course_id>`                        | Public    | Course detail page             |
| GET           | `/healthz`                                    | Public    | Health/readiness probe         |
| GET/POST      | `/register`                                   | Public    | Student registration           |
| GET/POST      | `/login`                                      | Public    | Login                          |
| POST          | `/logout`                                     | Any user  | Logout                         |
| GET/POST      | `/setup-password/<token>`                     | Public    | One-time password setup from an invitation |
| GET           | `/student/dashboard`                          | Student   | Application list + status      |
| GET/POST      | `/student/profile`                            | Student   | Edit own name / phone (email is fixed) |
| GET/POST      | `/student/apply`                              | Student   | New application                |
| GET/POST      | `/student/application/<id>/edit`              | Student   | Edit draft/correction          |
| GET           | `/student/application/<id>`                   | Student   | Application detail             |
| POST          | `/student/application/<id>/submit`            | Student   | Submit application             |
| POST          | `/student/application/<id>/upload`            | Student   | Upload document                |
| POST          | `/student/document/<id>/delete`               | Student   | Delete document                |
| GET           | `/student/document/<id>`                      | Student   | Signed URL for own document    |
| GET/POST      | `/admin/login`                                | Public    | **Dedicated administrator login** (admins only) |
| GET           | `/admin/dashboard`                            | Admin     | Statistics dashboard + charts  |
| GET           | `/admin/students`                             | Admin     | Students management (search/sort/filter) |
| GET/POST      | `/admin/students/new`                         | Admin     | Add a student + issue a setup link |
| GET           | `/admin/students/<user_id>`                   | Admin     | Student profile + applications |
| GET/POST      | `/admin/students/<user_id>/edit`              | Admin     | Edit a student's details/status |
| POST          | `/admin/students/<user_id>/status`            | Admin     | Set status (active/inactive/withdrawn) |
| POST          | `/admin/students/<user_id>/invite`            | Admin     | Resend a password-setup link   |
| GET/POST      | `/admin/students/<user_id>/delete`            | Admin     | Preview + permanently delete a student |
| GET           | `/admin/applications`                         | Admin     | Search/filter applications (`?status=`, `?course_id=`, `?date_from=`, `?date_to=`) |
| GET           | `/admin/application/<id>`                     | Admin     | Review application             |
| POST          | `/admin/application/<id>/status`              | Admin     | Approve/reject/correction      |
| POST          | `/admin/document/<id>/verify`                 | Admin     | Verify/unverify a document     |
| GET           | `/admin/document/<id>`                        | Admin     | Signed URL for a document      |
| GET           | `/admin/notifications`                        | Admin     | Action centre: pending work + unverified documents + activity |
| GET           | `/admin/courses`                              | Admin     | Course management              |
| POST          | `/admin/courses/create`                       | Admin     | Add course                     |
| POST          | `/admin/courses/<id>/update`                  | Admin     | Update course                  |
| POST          | `/admin/courses/<id>/toggle`                  | Admin     | Activate/deactivate course     |
| POST          | `/admin/courses/<id>/delete`                  | Admin     | Delete course (no applications) |
| GET           | `/admin/reports`                              | Admin     | Reports, charts + audit feed   |
| GET/POST      | `/admin/profile`                              | Admin     | Admin profile + password change|
| GET           | `/admin/export/applications.csv`              | Admin     | CSV export (filter-aware)      |

---

## REST API (`/api`)

Alongside the server-rendered pages, the backend exposes a complete **JSON REST
API** under `/api`. It is a thin presentation layer over the same service layer,
so authorization and validation behave identically. It is what the standalone
`frontend/` uses when `USE_SAMPLE_DATA` is `false`.

### Authentication model

- Session-cookie based (Flask-Login). Successful `login`/`register` set an
  `HttpOnly`, `SameSite=Lax` cookie; send `credentials: "include"` from browsers.
- Every response is JSON. Success responses include `"ok": true`; errors include
  `"ok": false` and an `"error"` message (plus `"errors"` for field problems).
- Roles are enforced server-side: students can only read/modify **their own**
  applications, and only administrators may change a status to approved/rejected.

### CSRF protection

State-changing API calls (`POST`, `PUT`, `PATCH`, `DELETE`) require an
`X-CSRF-Token` header (or a `csrf_token` body field). Fetch a token once from
`GET /api/auth/csrf`; `login`, `register`, `me` and `csrf` also return it as
`csrf_token` and the static frontend caches it automatically. Token checking can
be disabled for trusted integrations with `API_CSRF_ENABLED=false`.

### CORS

Cross-origin browser calls are allowed only for the origins in
`CORS_ALLOWED_ORIGINS` (credentials enabled, `Vary: Origin`). No extra dependency
is required.

### Endpoints

| Method        | Path                                          | Access   | Purpose                              |
|---------------|-----------------------------------------------|----------|--------------------------------------|
| GET           | `/api/auth/csrf`                              | Public   | Fetch a CSRF token                   |
| POST          | `/api/auth/register` (alias `/api/register`)  | Public   | Create a student account             |
| POST          | `/api/auth/login` (alias `/api/login`)        | Public   | Log in                               |
| POST          | `/api/auth/logout` (alias `/api/logout`)      | Any      | Log out                              |
| GET           | `/api/auth/me` (alias `/api/me`)              | Any      | Current session user (`null` if none)|
| GET           | `/api/courses`                                | Public   | Course catalogue (`?program_type=degree|diploma`, `?active=false` for all) |
| GET           | `/api/announcements`                          | Public   | Published announcements              |
| GET           | `/api/applications`                           | User     | Own list (admins: all, filterable)   |
| GET           | `/api/applications/my`                        | Student  | Own applications                     |
| POST          | `/api/applications`                           | Student  | Create a draft application           |
| GET           | `/api/applications/<application_id>`          | Owner/Admin | Application + documents + history |
| PUT / PATCH   | `/api/applications/<application_id>`          | Student  | Update an editable application       |
| POST          | `/api/applications/<application_id>/submit`   | Student  | Submit (requires marks card)         |
| GET           | `/api/applications/<application_id>/documents`| Owner/Admin | List documents (`?urls=true` for links) |
| POST          | `/api/applications/<application_id>/documents`| Student  | Upload a document (multipart)        |
| GET           | `/api/documents/<document_id>`                | Owner/Admin | Short-lived signed URL            |
| DELETE        | `/api/documents/<document_id>`                | Student  | Delete a document                    |
| POST          | `/api/applications/track`                     | Public   | Track by number + email              |
| GET           | `/api/applications/track/<application_number>`| Public*  | Track by number (`?email=`)          |
| GET           | `/api/admin/applications`                     | Admin    | Search/filter/sort/date + pagination |
| GET           | `/api/admin/applications/<application_id>`    | Admin    | Full review view (documents with signed URLs, named history) |
| PATCH / POST  | `/api/admin/applications/<application_id>/status` | Admin | Approve / reject / request correction |
| GET           | `/api/admin/stats`                            | Admin    | Counts (incl. `pending`, `students_total`, `courses_active`, `diploma_active`) |
| GET           | `/api/admin/students`                         | Admin    | Student list (`?q=`, `?status=`, `?sort=`, `?order=`, `?page=`, `?per_page=`) |
| POST          | `/api/admin/students`                         | Admin    | Create a student + one-time setup link |
| GET           | `/api/admin/students/<user_id>`               | Admin    | Student profile + applications       |
| PATCH / PUT   | `/api/admin/students/<user_id>`               | Admin    | Update a student's details/status    |
| POST / PATCH  | `/api/admin/students/<user_id>/status`        | Admin    | Set status (`active`/`inactive`/`withdrawn`) |
| POST          | `/api/admin/students/<user_id>/invite`        | Admin    | Reissue the password-setup link      |
| DELETE        | `/api/admin/students/<user_id>`               | Admin    | Permanently delete (`confirm=DELETE`, `reason` required) |
| GET           | `/api/admin/audit`                            | Admin    | Recent audit-log entries (`?limit=`) |
| GET           | `/api/admin/profile`                          | Admin    | The signed-in administrator's own account (never a hash) |
| POST / PATCH  | `/api/admin/profile/password`                 | Admin    | Change own password (re-verifies current password, audited) |
| POST / PATCH  | `/api/admin/documents/<document_id>/verify`   | Admin    | Verify / un-verify a document        |
| GET           | `/api/admin/courses`                          | Admin    | Course list (active + inactive) with `application_count` |
| POST          | `/api/admin/courses`                          | Admin    | Create a course                      |
| PATCH / PUT   | `/api/admin/courses/<course_id>`              | Admin    | Update a course                      |
| POST          | `/api/admin/courses/<course_id>/toggle`       | Admin    | Activate / deactivate a course       |
| DELETE        | `/api/admin/courses/<course_id>`              | Admin    | Delete a course (no applications)    |
| GET           | `/api/admin/export/applications.csv`          | Admin    | CSV report (same filters as the list)|

\* Anonymous tracking requires the email used on the application; a logged-in
owner or an administrator may omit it. The admin list accepts `?status=`,
`?course_id=`, `?q=`, `?from=` & `?to=` (submission date, `YYYY-MM-DD`), `?sort=`
(whitelisted columns such as `application_number`, `first_name`, `last_name`,
`percentage`, `status`, `submitted_at`, `created_at`), `?order=asc|desc`, and
`?page=` & `?per_page=` (max 100). The CSV export honours the same filters.

### Example requests and responses

Register and obtain a session + CSRF token:

```bash
curl -c cookies.txt -H "Content-Type: application/json" \
  -d '{"full_name":"Arjun Sharma","email":"arjun@example.com","phone":"9876543210","password":"StrongPass1","confirm_password":"StrongPass1"}' \
  http://localhost:5000/api/auth/register
```

```json
{
  "ok": true,
  "user": {"id": "…", "name": "Arjun Sharma", "email": "arjun@example.com", "role": "student", "phone": "9876543210"},
  "csrf_token": "…"
}
```

Create an application (note the CSRF header and session cookie):

```bash
curl -b cookies.txt -c cookies.txt -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -d '{"first_name":"Arjun","last_name":"Sharma","date_of_birth":"2007-04-18","gender":"male","category":"general","email":"arjun@example.com","phone":"9876543210","address_line":"42 Lake View","city":"Bengaluru","state":"Karnataka","postal_code":"560041","qualifying_exam":"Class 12","board_university":"CBSE","passing_year":"2025","marks_obtained":"462","marks_total":"500","course_id":"<course-uuid>"}' \
  http://localhost:5000/api/applications
```

```json
{
  "ok": true,
  "application": {
    "id": "…", "status": "draft", "application_number": null,
    "applicantName": "Arjun Sharma", "email": "arjun@example.com",
    "course_id": "…", "courseName": "B.Tech Computer Science & Engineering",
    "percentage": 92.4, "created_at": "…"
  }
}
```

Upload a private document (multipart) and submit:

```bash
curl -b cookies.txt -H "X-CSRF-Token: <token>" \
  -F "doc_type=marks_card" -F "file=@marks.pdf" \
  http://localhost:5000/api/applications/<application_id>/documents

curl -b cookies.txt -H "X-CSRF-Token: <token>" \
  -X POST http://localhost:5000/api/applications/<application_id>/submit
```

Administrator approves an application:

```bash
curl -b admin_cookies.txt -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <admin-token>" -X PATCH \
  -d '{"status":"approved","note":"Documents verified."}' \
  http://localhost:5000/api/admin/applications/<application_id>/status
```

Error responses use a consistent shape:

```json
{ "ok": false, "error": "Invalid email or password." }
{ "ok": false, "error": "Please correct the highlighted fields.", "errors": { "password": "Password must be at least 8 characters long." } }
```

| Status | When it is returned                                                     |
|--------|-------------------------------------------------------------------------|
| 200    | Successful read/update                                                  |
| 201    | Resource created (registration, application, document)                  |
| 400    | Malformed request / unknown filter                                      |
| 401    | Not logged in (or bad credentials)                                      |
| 403    | Wrong role, deactivated account, missing/invalid CSRF token, email mismatch |
| 404    | Not found, or not owned by the caller (existence is not leaked)         |
| 405    | HTTP method not allowed for the endpoint                                |
| 409    | Business-rule conflict (duplicate email, already submitted, missing marks card) |
| 413    | Uploaded file exceeds `MAX_CONTENT_LENGTH`                              |
| 422    | Validation errors (field messages under `errors`)                       |
| 500    | Unexpected server error (logged server-side, no internals returned)     |

---

## Admin dashboard (static console)

Alongside the server-rendered admin pages, `admin/` contains a self-contained
HTML/CSS/JS dashboard that talks **only** to the `/api` JSON endpoints. It is the
same console used as the primary review interface. Its sidebar exposes
**Dashboard, Students, Applications, Courses, Reports** and **Profile**. It
includes:

- **Dashboard overview** — live cards for registered students, total / pending /
  approved / rejected applications and active Polytechnic courses, plus recent
  administrator activity, all from `/api/admin/stats` and `/api/admin/audit`.
- **Summary cards for applications** — total, pending, approved, rejected and
  correction-requested counts from `/api/admin/stats`; clicking a card filters the
  table to that status.
- **Searchable, sortable, filterable, paginated table** — free-text search
  (`?q=`), course and status filters, a submission-date range (`?from=`/`?to=`),
  click-to-sort columns and server-side pagination (`?page=`/`?per_page=`).
- **Detail drawer** — every field, an academic record, uploaded documents with
  short-lived signed URLs and verify/un-verify buttons, a **status history
  timeline showing who changed what and when** (names resolved server-side), and
  approve / reject / request-correction actions with confirmation dialogs
  (reject and correction require a note — enforced by both the UI *and* the API).
- **Course management** — create, edit, activate/deactivate and delete Degree and
  Diploma / Polytechnic courses (type, duration, eligibility, annual fee, seats),
  with per-course application counts; changes immediately reflect in the public
  catalogue and the dashboard filter.
- **Students management** — a searchable, sortable, filterable, paginated table
  (name, email, phone, registration number, application count, status); a detail
  modal shows the student's account and every application, and administrators can
  activate/deactivate the account (never exposing password hashes).
- **Reports** — applications-by-status and applications-by-course breakdowns plus
  the recent administrator audit trail; the CSV export downloads the currently
  filtered list.
- **Admin profile** — the signed-in administrator's account details and a secure
  password change that re-verifies the current password server-side and is audited.
- **CSV export** — downloads the currently filtered list as `admission_report_….csv`.
- **Loading, validation and success states** — spinners on every fetch, inline
  field errors, and toast notifications for every action outcome.

Every one of these calls goes through an admin-only API route, so a student or
anonymous visitor can never reach the data — no matter what the page shows.

### Run it

**Served by Flask (recommended, same origin — no CORS setup):**

```bash
python wsgi.py
# open http://localhost:5000/admin-console/
```

**Stand-alone (any static server) during development:**

```powershell
.\venv\Scripts\python.exe -m http.server 8081 --directory admin
# open http://localhost:8081/ and enter the API URL in the login page's
# “Advanced” panel (or pass ?api=http://localhost:5000)
```

`http://localhost:8081` is already whitelisted in the default
`CORS_ALLOWED_ORIGINS`; same-site cookies (`SameSite=Lax`) are sent
cross-port on `localhost`, so the session works without extra configuration.

### Try it without Supabase

`scripts/demo_server.py` runs the whole application (public site + console +
API with CSRF enabled) against an **in-memory database** — no Supabase project
and no network access:

```bash
.\venv\Scripts\python.exe scripts\demo_server.py
```

It inserts the bundled course catalogue, but creates **no demo members or
applications**. To have the server create one administrator at startup, set the
variables first:

```powershell
$env:ADMIN_EMAIL="admin@example.com"
$env:ADMIN_FULL_NAME="Admissions Administrator"
$env:ADMIN_PASSWORD="A-Strong-Passw0rd"
.\venv\Scripts\python.exe scripts\demo_server.py
```

| Page            | URL                                    |
|-----------------|----------------------------------------|
| Admin console   | `http://localhost:5010/admin-console/` |
| Public site     | `http://localhost:5010/`               |

Everything else is created through the UI (or the API) and disappears when the
server stops. Set `SEED_DEMO_COURSES=0` to start with an empty catalogue.

## Standalone frontend preview

In addition to the Jinja templates served by Flask, the repository ships a
**fully static, framework-free front end** in the `frontend/` folder. It is a
complete, clickable implementation of the portal (all 9 pages, reusable CSS and
JavaScript, validation, loading/empty/error states). It now uses the Flask API
by default (`USE_SAMPLE_DATA: false`); the built-in sample members, applications
and courses have been removed.

> The static front end is a *second* presentation layer. The Flask app in
> `app/` remains the production server-rendered UI that talks to Supabase. Both
> are included so you can compare them; use whichever you prefer.

### Run it locally

Any static file server works. From the project root:

```powershell
# Option A — Python (already in your virtualenv)
.\venv\Scripts\python.exe -m http.server 8080 --directory frontend
# then open http://localhost:8080/index.html
```

```bash
# Option B — Python on macOS/Linux
python3 -m http.server 8080 --directory frontend
```

> Open the pages through the server (`http://localhost:8080/...`). The pages
> call the Flask API, so start the backend first.

### No demo accounts

The static frontend no longer ships demo credentials or quick-login buttons.
Create an account through `register.html`, or sign in with the administrator you
created with `flask create-admin` / `flask reset-project`. When the backend is
running, students can apply (`admission.html`) and track status (`status.html`);
administrators can review applications from `application_details.html`.

### Switching back to sample data (optional)

Everything network-related lives in `frontend/assets/js/api.js`. Flip one flag in
`frontend/assets/js/config.js`:

```js
window.APP_CONFIG = {
  USE_SAMPLE_DATA: true,                          // optional: turn preview mode on
  API_BASE_URL: "http://localhost:5000/api",       // ← your Flask URL
  ...
};
```

With the default `USE_SAMPLE_DATA: false`, every call is a real `fetch()` against
the endpoint map in `config.js` (`/auth/login`, `/courses`, `/applications`,
`/admin/stats`, …). The browser **never** talks to a database directly — only to
your Flask API, which owns the Supabase credentials.

The Flask backend now implements that endpoint map (see
[REST API](#rest-api-api)) **and** the CORS/CSRF handling the browser needs, so no
extra package is required. Just list the static origin in `.env`:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:8080
```

The static client fetches a CSRF token automatically from `/api/auth/csrf` before
its first write, so logins and applications work out of the box. In production,
serve the API and frontend under the same site (or use HTTPS with
`SameSite=None` cookies) so the session cookie is sent.

### How sample data is kept separate from real operations

- `frontend/assets/js/sample-data.js` is intentionally **empty** — no demo
  members, applications or courses are bundled.
- `frontend/assets/js/api.js` is the single boundary for data access and chooses
  between the (empty) preview engine and real HTTP.
- All other files render whatever the API returns; they contain no hard-coded
  records.
- A dismissible banner reminds you when preview mode is active.

### Frontend file organisation

| Folder | Purpose |
|---|---|
| `frontend/assets/css/base.css` | Design tokens (blue/white theme), reset, typography, layout |
| `frontend/assets/css/components.css` | Navbar, buttons, cards, forms, tables, badges, modals, toasts |
| `frontend/assets/css/pages.css` | Page-specific layouts (hero, auth, dashboards, tracker) |
| `frontend/assets/js/config.js` | One place for the API URL, endpoint map and the sample flag |
| `frontend/assets/js/api.js` | Sample-vs-real data layer (the only place that fetches) |
| `frontend/assets/js/sample-data.js` | Intentionally empty (no demo records) |
| `frontend/assets/js/validation.js` | Reusable field rules + form validation |
| `frontend/assets/js/auth.js` | Session handling and route guards |
| `frontend/assets/js/ui.js` | Header/footer, toasts, modals, empty/loading states |
| `frontend/assets/js/components.js` | Reusable renderers (course card, timeline, table row) |
| `frontend/assets/js/main.js` | Shared bootstrap + guards + preview banner |
| `frontend/assets/js/pages/*.js` | One script per page |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Supabase is not configured` warning and empty data | Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`, then restart. |
| Register/login/apply does nothing, or courses look empty | The backend is not running. Start it with `START_APP.bat` and use <http://localhost:5000>. Do not open `frontend/index.html` directly. |
| Submit application button does nothing | Refresh the page once (the fixed `main.js`/`ui.js` are versioned). The app saves the form as a draft first; upload a marks card, then click **Submit application** and confirm. |
| Admin sign-in fails in `/admin-console` but works in `/admin/login` | A stale standalone API URL was saved in the browser. It is now ignored when Flask serves the console; alternatively clear the `admin_api_base` localStorage key. |
| Changes to courses/applications disappear after restarting | Only one server process may own `instance/local_db.json`. Close all old command windows before starting `START_APP.bat`; the save routine now also retries briefly on Windows file locks. |
| `Invalid or missing CSRF token` | The form was opened before login or the session expired — refresh and retry. Do not post forms from outside the app. |
| `new row violates row-level security policy` | You are using the anon key on the server. Use the **service_role** key in `SUPABASE_SERVICE_ROLE_KEY`. |
| Course pages show no Diploma courses / `column program_type does not exist` | Run [`sql/upgrade_diploma.sql`](sql/upgrade_diploma.sql) once, then add/activate diploma courses in **Manage Courses**. |
| Student add/edit/status fails with `column status does not exist` (or `registration_number`, `invite_*`) | Run [`sql/upgrade_students.sql`](sql/upgrade_students.sql) once, then restart the app. |
| Application save fails with `column institution_name does not exist` (or `stream`, `trade`, `affiliation`, `roll_number`) | Run [`sql/upgrade_qualifications.sql`](sql/upgrade_qualifications.sql) once, then restart the app. |
| A student says their password setup link is invalid | Links expire after 7 days and are single use. Open the student's profile and click **Resend setup link**. |
| Upload fails with a storage error | Ensure the `admission-documents` bucket exists and is **private**, and that `SUPABASE_STORAGE_BUCKET` matches its name. |
| `413 Request Entity Too Large` | The file exceeds `MAX_CONTENT_LENGTH` (default 5 MB). |
| Render deploy crashes with `gunicorn: command not found` | Make sure `requirements.txt` is committed — it pins `gunicorn`. |
| Cookies not set behind a proxy | Keep `FLASK_ENV=production` on Render so cookies are `Secure` over HTTPS. |

---

## License

Provided as a complete reference implementation for educational use. Adapt and
extend it as needed for your institution.
=======
# College-admission-automation
>>>>>>> 52068cf67c3253c5aee536d2b28a4a5cef30d28c
