# Frontend — College Admission Portal (static)

A complete, responsive **HTML5 + CSS3 + vanilla JavaScript** front end for the
College Admission Automation System. It uses the Flask API by default and never
opens a database connection from JavaScript. No demo members or demo
applications are bundled; the backend course catalogue can be seeded with
`flask --app wsgi seed-courses`.

## Pages

| File | Description |
|---|---|
| `index.html` | Homepage — hero, intro, featured courses, announcements, footer |
| `register.html` | Student registration |
| `login.html` | Login for students and administrators |
| `courses.html` | Course listing with eligibility, duration, fees, seats |
| `admission.html` | Multi-section application form (6 steps + document upload) |
| `student_dashboard.html` | Profile, application summary and status |
| `status.html` | Public application tracking with a progress timeline |
| `admin_dashboard.html` | Statistics, status chart and application table |
| `application_details.html` | Detailed review page with approve/reject actions |

## Run locally

```powershell
# from the repository root
.\venv\Scripts\python.exe -m http.server 8080 --directory frontend
```

Then open <http://localhost:8080/index.html>.

Any static server works (`npx serve`, VS Code Live Server, etc.). Serving over
HTTP is recommended so links, redirects and the session guard behave exactly as
in production.

## Try the flows

There are **no demo credentials**. Create the first administrator from the
project root, then sign in with the credentials you choose:

```powershell
.\venv\Scripts\python.exe -m flask --app wsgi create-admin
# If the database already has members you no longer control:
.\venv\Scripts\python.exe -m flask --app wsgi reset-project
```

- **Student:** register at `register.html`, apply via `admission.html`, see the
  summary on the dashboard, then track it on `status.html`.
- **Admin:** sign in, add your real courses in the Flask admin area, then open
  an application to approve, reject or request corrections.

> The static frontend and the Flask-rendered pages share the same backend/API.
> Load the bundled catalogue with `flask --app wsgi seed-courses`, or add your
> own courses in **Manage Courses**.

## Connect to the Flask backend

This is already the default in `assets/js/config.js`:

```js
window.APP_CONFIG = {
  USE_SAMPLE_DATA: false,                    // use the real API
  API_BASE_URL: "http://localhost:5000/api",
  ...
};
```

The endpoint contract is declared in the same file. Enable CORS on Flask for the
static origin:

```python
from flask_cors import CORS
CORS(app, supports_credentials=True, origins=["http://localhost:8080"])
```

## Structure

```
frontend/
├── *.html                      # the 9 pages
└── assets/
    ├── css/                    # base.css, components.css, pages.css
    └── js/
        ├── config.js           # API URL, endpoint map, USE_SAMPLE_DATA
        ├── sample-data.js      # intentionally empty (no demo records)
        ├── api.js              # the ONLY module that fetches data
        ├── validation.js       # reusable form validation
        ├── auth.js             # session + route guards
        ├── ui.js               # header/footer, toasts, modals, states
        ├── components.js       # course card, timeline, table row renderers
        ├── main.js             # shared bootstrap, guards, preview banner
        └── pages/              # one script per page
```

> `sample-data.js` is intentionally empty. All data comes from the Flask API.
> The empty arrays exist only so the preview-mode code path still renders normal
> empty states instead of failing.
