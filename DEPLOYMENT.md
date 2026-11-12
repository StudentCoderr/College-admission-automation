# Deployment Guide — College Admission Automation System

Step-by-step instructions for taking this project from your local machine to a
live URL, using **GitHub** for source control and **Render** for hosting, with
**Supabase** (PostgreSQL + Storage) as the persistent online database.

Everything stores admission records, users, status history and document
**metadata** in Supabase PostgreSQL; document **bytes** live in a private
Supabase Storage bucket and are served through short-lived signed URLs. Nothing
is written to the server's local disk.

> ⚠️ **Never commit secrets.** `.env` is already ignored (`.gitignore`). The
> Supabase **service-role key** is server-side only — the browser must never
> see it. If you see `SUPABASE_SERVICE_ROLE_KEY` or `SECRET_KEY` in a file that
> will be pushed to GitHub, stop and remove them first.

---

## 1. Organize the complete project directory

From the project root, the layout is:

```
college-admsion-automation/
├── app/                          # Flask application package
│   ├── __init__.py               # App factory, /admin-console mount, CLI (create-admin, reset-project)
│   ├── config.py                 # All settings from environment variables
│   ├── extensions.py             # Flask-Login + CSRF singletons
│   ├── models/
│   ├── services/                 # Supabase data access, application lifecycle, document rules
│   ├── api/                      # JSON REST API under /api (used by the admin console)
│   ├── routes/                   # Server-rendered pages (student/admin/public)
│   ├── templates/                # Jinja HTML templates (auto-discovered by Flask)
│   └── static/                   # CSS/JS/images for the server-rendered pages
├── admin/                        # Static admin console (HTML/CSS/JS, talks to /api)
├── frontend/                     # Optional static student-facing preview
├── sql/
│   ├── schema.sql                # Tables, indexes, triggers, RLS, storage bucket (run first)
│   ├── reset_all_data.sql        # Destructive: remove every row and start over
│   └── seed.sql                  # Default Degree + Diploma course catalogue
├── tests/                        # Offline pytest suite (in-memory fake DB)
├── scripts/
│   └── demo_server.py            # DEV ONLY: in-memory database with seeded courses (no Supabase)
├── wsgi.py                       # Gunicorn entry point (production)
├── Procfile                      # Render start command
├── render.yaml                   # Render Blueprint (infra as code)
├── requirements.txt              # Python dependencies
├── .env.example                  # Template for local environment variables
├── .gitignore                    # Excludes .env and venv
└── README.md
```

**Before you begin:** open `.gitignore` and confirm these lines exist (they do
in this project):

```gitignore
# Secrets - never commit
.env
*.env
!.env.example
```

---

## 2. Create `requirements.txt`

This file already exists and is correct. It pins every runtime dependency:

```text
Flask==3.0.3
Werkzeug==3.0.3
Flask-Login==0.6.3
supabase==2.7.4
python-dotenv==1.0.1
gunicorn==22.0.0
pytest==8.2.2
```

| Package          | Why it is here                                             |
|------------------|------------------------------------------------------------|
| `Flask`          | Web framework (templates, routes, sessions)                |
| `Werkzeug`       | Password hashing (scrypt) and request handling             |
| `Flask-Login`    | Session login for students and admins                      |
| `supabase`       | Python client for PostgreSQL, Auth, and Storage            |
| `python-dotenv`  | Loads `.env` locally (config.py calls `load_dotenv()`)      |
| `gunicorn`       | Production WSGI server used by Render                      |
| `pytest`         | Test suite (harmless in production, used only in CI/local) |

`pytest` is technically a dev dependency, but keeping it in `requirements.txt`
keeps setup simple. If you want a production-only build later, split it into
`requirements-dev.txt`.

**Verify locally (optional):**

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
```

---

## 3. Configure Flask to serve HTML templates and static files

Flask discovers templates and static assets automatically from the `app`
package:

- **Templates**: `app/templates/**` → auto-rendered by `render_template(...)`.
  The project uses a shared `base.html` (role-aware navigation + flash
  messages) that every page extends.
- **Static files**: `app/static/**` → served at `/static/...` automatically.
- **JSON REST API**: mounted at `/api` (blueprint wiring in `app/api/__init__.py`).
- **Static admin console**: `admin/**` is served by Flask at `/admin-console/`
  (registered in `app/__init__.py` via `send_from_directory`), so it works
  same-origin in production with no CORS configuration.
- **Entry point**: `wsgi.py` builds the app:

```python
# wsgi.py
from app import create_app
app = create_app()
```

Gunicorn imports `app` from `wsgi.py`; the `if __name__ == "__main__"` block
(the local `debug=True` dev server) is never executed on Render.

---

## 4. Configure environment variables (`.env.example`)

The file `.env.example` documents every variable the app reads
(`app/config.py`). Copy it for local development:

```bash
copy .env.example .env           # Windows
# cp .env.example .env           # macOS/Linux
```

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
FLASK_ENV=development

SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-public-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=admission-documents

MAX_CONTENT_LENGTH=5242880
SIGNED_URL_EXPIRES_IN=300

API_CSRF_ENABLED=true
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:8081,http://127.0.0.1:8081,http://localhost:5000,http://127.0.0.1:5000
```

| Variable | Local (development) | Production (Render) |
|---|---|---|
| `SECRET_KEY` | any long random value | **random, secret, unique** — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_ENV` | `development` | `production` (this also turns on `SESSION_COOKIE_SECURE`) |
| `SUPABASE_URL` | your project URL | same |
| `SUPABASE_ANON_KEY` | your anon key | same (this backend does not use it, but it is kept for reference) |
| `SUPABASE_SERVICE_ROLE_KEY` | your service-role key | same — **server side only, never in the browser** |
| `SUPABASE_STORAGE_BUCKET` | `admission-documents` | same (created by `schema.sql`) |
| `MAX_CONTENT_LENGTH` | `5242880` (5 MB) | same |
| `SIGNED_URL_EXPIRES_IN` | `300` (5 min) | same or lower for tighter security |
| `API_CSRF_ENABLED` | `true` | `true` (keep it) |
| `CORS_ALLOWED_ORIGINS` | localhost ports | **add your production origin** if you serve the static frontend/console cross-origin |

> Generate the random secret once and use **one** value in production
> (`SECRET_KEY` is used to sign session cookies; changing it logs everyone out).

---

## 5. Create the Supabase project and run the SQL schema

1. Go to <https://supabase.com> → **Start your project** → log in with GitHub.
2. **New project**: name it (e.g. `college-admission`), set a strong **database
   password**, choose a region close to your users, pick the Free plan.
3. Wait ~1–2 minutes for the project to provision.
4. Open **SQL Editor** (left sidebar) → **New query**.
5. Paste the entire contents of `sql/schema.sql` → **Run**. This creates:
   - Tables: `users`, `courses`, `applications`, `documents`,
     `application_status_history`, `announcements`
   - Indexes and the `updated_at` trigger
   - The `generate_application_number()` RPC (produces `ADM-2026-00001` …)
   - **Row Level Security** as defence-in-depth
   - The **private storage bucket** `admission-documents`
6. (Optional) Run `sql/seed.sql` to insert the bundled Degree + Diploma course
   catalogue. It is idempotent and does not overwrite edited courses. No demo
   members or administrator passwords are bundled.
7. Verify: **Table Editor → public → applications** shows an empty table; check
   **Storage → Buckets** shows `admission-documents` with **public = off**.

> The schema is idempotent — re-running it is safe.

---

## 6. Configure authentication, database access, and private document storage

All three are already implemented server-side; this step is about **what** they
are and **where** the keys go, so no source changes are needed.

**Authentication**
- Flask-Login sessions: passwords hashed with **scrypt** (`werkzeug.security`),
  session cookie is `HttpOnly`, `SameSite=Lax` locally and `Secure` when
  `FLASK_ENV=production`.
- Roles enforced on every route (`admin_required` / `student_required` and the
  JSON variants), plus record-level ownership checks.
- An admin account is **not** created by the SQL seed (password hashes are
  generated by the app). Create it after deploy with the bundled CLI —
  see step 9.

**Database access**
- The app never talks to PostgreSQL in the browser. `app/services/supabase_service.py`
  is the single data-access layer and uses the **service-role key**, which
  bypasses RLS for server-side operations.
- Put `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the Render environment
  (step 9). The anon key is kept in the backend but not used directly.

**Private document storage**
- The storage bucket `admission-documents` is **private** (created by
  `schema.sql`).
- Uploads are streamed as bytes to Supabase Storage and their metadata recorded
  in `public.documents`; paths are namespaced per application.
- Access is always by **short-lived signed URL** generated server-side
  (`SIGNED_URL_EXPIRES_IN` seconds), so there is no public file URL.
- The static admin console opens documents through those signed URLs returned
  by `GET /api/admin/applications/<id>`.

---

## 7. Upload the source code to GitHub

1. Create a repository at <https://github.com/new> (e.g. `college-admission-system`,
   private or public as you prefer).
2. From the project root:

```bash
git init
git add .
git status                      # ⚠️ confirm .env is NOT listed
git commit -m "College Admission Automation System"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

3. **Double-check** on GitHub that `.env` is not in the file list. If you
   already committed it once, remove it from history:

```bash
git rm --cached .env
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Remove .env from version control"
```

---

## 8. Deploy the Flask application on Render

Two equivalent options:

### Option A — Blueprint (recommended)

`render.yaml` already describes the service (Python 3.12.4, build command,
start command, health check, environment variables). From Render:

1. <https://dashboard.render.com> → **New +** → **Blueprint**.
2. Connect your GitHub account and select the repository.
3. Render reads `render.yaml`, creates the web service, and starts deploying —
   you only review the values.
4. Secrets that are marked `sync: false` (`SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `CORS_ALLOWED_ORIGINS`)
   must be filled in the service's **Environment** panel (step 9).

### Option B — Manual web service

1. <https://dashboard.render.com> → **New +** → **Web Service**.
2. Connect GitHub and pick the repository.
3. Set the values shown below, then **Create Web Service**:

| Setting | Value |
|---|---|
| Name | `college-admission-system` |
| Runtime | `Python 3` (or Python 3.12.4) |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120` |
| Health check path | `/healthz` (see `Procfile` notes) |

The same command is in `Procfile`, so Option A uses it automatically.

**During the first deploy:** the build installs `requirements.txt` (about
1–2 minutes), then the service boots. Render's health check calls `/healthz`,
which returns `{"status": "ok", "supabase_configured": true}` once the database
env vars are set.

---

## 9. Configure production environment variables and start commands

### Environment variables (Render → your service → Environment)

Add every variable from `.env.example`. Values **override** the file defaults
because `app/config.py` reads from the environment first.

| Key | Value | Notes |
|---|---|---|
| `PYTHON_VERSION` | `3.12.4` | Already set by `render.yaml` |
| `FLASK_ENV` | `production` | Enables `SESSION_COOKIE_SECURE` |
| `SECRET_KEY` | random 64-char string | Generate once; keep it stable |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | From Project Settings → API |
| `SUPABASE_ANON_KEY` | anon public key | From Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role key | **Server-side only** |
| `SUPABASE_STORAGE_BUCKET` | `admission-documents` | Matches the bucket created by the schema |
| `MAX_CONTENT_LENGTH` | `5242880` | 5 MB upload limit |
| `SIGNED_URL_EXPIRES_IN` | `300` | Signed URL lifetime (seconds) |
| `API_CSRF_ENABLED` | `true` | Keep CSRF on |
| `CORS_ALLOWED_ORIGINS` | your origins | Add `https://your-app.onrender.com` if you serve the static frontend/console cross-origin (same-origin `/admin-console/` needs nothing) |

### Create the admin account on the deployed database

Render lets you open a shell inside the running service:

1. Service → **Shell** (top-right).
2. Run:

```bash
flask --app wsgi create-admin
```

`create-admin` prompts for an email, full name and password, then creates an
`admin` row with a correct scrypt hash. No old password is required. The
deployed environment's env vars are already loaded, so it writes straight into
your production Supabase database. The course catalogue is empty by design —
add your real courses in **Manage Courses**.

If the production database already contains members you no longer control, run:

```bash
flask --app wsgi reset-project
```

This permanently deletes every account, application, course and uploaded file,
then prompts for a new administrator. Type `RESET` to confirm.

> The same commands work locally against a real Supabase project if you fill
> `.env` with the production service-role key — but running them in Render's
> Shell is safer because the secrets never leave the platform.

### Start commands

- **Local dev**: `python wsgi.py` (or `flask --app wsgi run`) — `debug=True`,
  no gunicorn.
- **Production (Render)**: `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2
  --threads 4 --timeout 120` — WSGI only, debug never runs.

---

## 10. Test everything through the deployed URL

Use the URL Render assigns (e.g. `https://college-admission-system.onrender.com`).

### A. Public site (server-rendered)

1. Open the root URL → home page with courses and announcements renders.
2. **Register** at `/register` with a student email/password → you are logged in.
3. **Start an application** at `/applications/new` (student dashboard) → fill
   personal, contact, academic details → **save draft**.
4. **Upload a document** (PDF/JPG/PNG under 5 MB) on the application page → it
   is stored in the private Supabase bucket, metadata in PostgreSQL.
5. **Submit** → you receive the application number (e.g. `ADM-2026-00001`).
6. **Track status** at `/status` using the number + email; it shows the
   submitted state.
7. Log out, log in again → your application is still there (persistent DB).

### B. Admin console (static, same origin)

8. Open `https://your-app.onrender.com/admin-console/` → **Sign in** with the
   admin account created in step 9.
9. Dashboard cards show totals; the table lists the submitted application.
10. **Open the drawer** → verify the document, **Approve** with a note.
11. Check the **status history** now shows who approved it and when.
12. Back at `/status` (student side) → status shows **Approved**.
13. Optional: try the **Courses** tab and **Export CSV**.

### C. Confirming persistence

- Create an application, then inspect the same record in
  **Supabase → Table Editor → public.applications**. Stop and restart the
  Render service (or let the free instance sleep) — the record, its documents
  and its status history remain, because they live in Supabase, not on the
  Render filesystem.

---

## Local development vs production settings

| Concern | Local (`.env`: `FLASK_ENV=development`) | Production (Render: `FLASK_ENV=production`) |
|---|---|---|
| WSGI server | Flask dev server (`debug=True`) | Gunicorn (Procfile / start command) |
| Session cookies | `HttpOnly`, `SameSite=Lax`, no `Secure` (plain `http://localhost`) | + `Secure` (HTTPS) |
| Database | Real Supabase project, or `scripts/demo_server.py` for an in-memory database with seeded courses | Always the real Supabase project |
| Document storage | Supabase Storage | Supabase Storage (same code path) |
| Secrets | `.env` file (git-ignored) | Render Environment variables (never in repo) |
| Templates/static | Auto-served by Flask | Auto-served by Flask (same) |
| `SECRET_KEY` | Dev fallback in `config.py` is fine locally | Must be set to a real secret |
| Admin account | `flask --app wsgi create-admin` | Same command in Render Shell |
| Reset everything | `flask --app wsgi reset-project` | Same command in Render Shell |
| Courses | `flask --app wsgi seed-courses` or add them in **Manage Courses** | Same |

---

## Common deployment errors and their solutions

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails: `ModuleNotFoundError: supabase / gunicorn` | Stale build cache or dependency missing | Confirm `requirements.txt` is committed; on Render, trigger a **manual deploy → Clear build cache**. |
| App boots but pages return empty lists, and logs say `Supabase is not configured` | `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` missing or empty | Add both to the service **Environment** panel and redeploy. Ensure no trailing spaces. |
| Login works locally but fails on Render | `SECRET_KEY` differs between deploys (or unset) | Set one stable random `SECRET_KEY`. Changing it invalidates all sessions. |
| Session “disappears” after a page reload on HTTPS | `SESSION_COOKIE_SECURE` off (i.e. `FLASK_ENV` not `production`) | Set `FLASK_ENV=production`. |
| Session “disappears” on `http://` (not Render) | Cookie is `Secure` but URL is plain HTTP | Only use `FLASK_ENV=production` behind HTTPS. |
| `403 Invalid or missing CSRF token` from the admin console | Console served from a different origin than the API without a cached token (usually fine — it bootstraps from `/api/auth/csrf`) | Ensure `API_CSRF_ENABLED` isn't disabled, cookies are `SameSite=Lax` + HTTPS, and you're not mixing `http`/`https` origins. |
| Browser console shows blocked `fetch` (CORS) for a served static frontend | The serving origin is not in `CORS_ALLOWED_ORIGINS` | Add `https://your-app.onrender.com` (or your custom domain) to `CORS_ALLOWED_ORIGINS`. Same-origin `/admin-console/` needs no CORS. |
| Document upload fails with 400/413 | Extension not allowed or file > 5 MB | Only PDF/JPG/PNG up to `MAX_CONTENT_LENGTH` (5 MB default). |
| `Could not generate a secure link` (502) when opening a document | Signed URL generation failed → service key missing/invalid or bucket missing | Check `SUPABASE_SERVICE_ROLE_KEY` and that bucket `admission-documents` exists (run `schema.sql`). |
| `relation "public.users" does not exist` | SQL schema never run | Run `sql/schema.sql` in the Supabase SQL Editor and redeploy. |
| Application creates but `application_number` stays `null` after submit | `generate_application_number()` RPC missing | Run `schema.sql` again (it creates the function; idempotent). |
| Render health check failing/restart loop | `/healthz` not responding in time or app cras | Check logs (`Service → Logs`). `gunicorn --timeout 120` is already set for slow cold starts. |
| Free instance feels slow / sleeps | Render free tier spins down after inactivity | First request after sleep can take ~30–60 s; upgrade to a paid instance for always-on. |
| `flask` command not found in Render Shell | venv not activated in the shell | Use the full path or `python -m flask --app wsgi ...` inside the service venv. |
| Committing secrets | `.env` or keys pasted into code | `git rm --cached .env`, add to `.gitignore`, rotate the leaked keys in Supabase settings. |
| Wrong values in `render.yaml` env (Blueprint) | `sync: false` vars left empty | Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ALLOWED_ORIGINS` in the service Environment panel. |

---

## Quick reference — files that make deployment work

| File | Role |
|---|---|
| `requirements.txt` | Installs Flask + Supabase + gunicorn |
| `wsgi.py` | Production WSGI entry point |
| `Procfile` | Render start command |
| `render.yaml` | Render Blueprint (infra as code) |
| `app/config.py` | Reads every setting from env vars |
| `sql/schema.sql` | Database tables, RLS, storage bucket |
| `sql/reset_all_data.sql` | Destructive reset (empty every table) |
| `sql/seed.sql` | Default Degree + Diploma course catalogue |
| `.env.example` | Documented template for env vars |
| `.gitignore` | Keeps `.env` out of GitHub |