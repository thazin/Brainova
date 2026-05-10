# Brainova

A Flask-based Brainova testing platform with admin-defined tests, AI-generated questions, and per-user notifications.

## Features

### For users
- Register, log in, and land on a personal dashboard with stats, latest result, and available tests.
- Take the **Quick Brainova Test** (legacy mixed-category test) or any **admin-published test**.
- Per-question countdown timer, shuffle, and answer randomization.
- View detailed results with answer review.
- Download results as **PDF** or **Excel**.
- In-app **notification inbox** with an unread-count badge in the navbar.

### For admins
- Dashboard with platform-wide stats (users, questions, tests taken, average IQ).
- **Question management** — manual CRUD plus an AI generator (Gemini) that produces 10 reasoning questions per category for review before saving.
- **Test management** — create/update/delete tests with:
  - Time limit (minutes)
  - Number of questions
  - Category filter (or mixed pool)
  - Shuffle on/off
  - Status: `draft` / `published` / `unpublished`
- Publishing a test fans out a notification to every non-admin user.
- The system **prevents publishing a test that asks for more questions than the pool can supply.**
- **User management** — view, edit, delete normal users (admin accounts are protected).

## Tech stack

- **Backend**: Python 3 + Flask 3
- **Database**: SQLite (file: `brainova.db`)
- **Frontend**: Jinja2 templates + Bootstrap 5
- **PDF/Excel export**: ReportLab + openpyxl
- **AI question generation**: Google Gemini (`google-genai`)

## Project structure

```
BRAINOVA_v4/
├── app.py                 # Flask app factory & blueprint registration
├── database.py            # SQLite connection, schema bootstrap, migrations, seed data
├── schema.sql             # Authoritative DDL
├── requirements.txt
├── routes/
│   ├── auth.py            # Login, register, logout
│   ├── admin.py           # Admin dashboard, questions, tests, users
│   ├── profile.py         # User dashboard, profile view & edit
│   ├── test.py            # Take tests, view/download results
│   └── notifications.py   # Inbox + fanout helpers
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── admin/             # dashboard, questions, tests, users, ...
│   ├── auth/              # login, register
│   ├── profile/           # dashboard, profile, edit
│   ├── test/              # start, take, take_custom, list, result
│   └── notifications/     # inbox
└── static/
    ├── css/style.css
    └── js/test.js         # Timer + per-question navigation
```

## Setup

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. (Optional) Configure the AI generator

Set the `GEMINI_API_KEY` environment variable to enable the **Generate Questions** button on the admin dashboard. Without it, manual question entry still works.

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

### 3. Run

```powershell
python app.py
```

The app starts on `http://127.0.0.1:5000`. The first run creates `brainova.db`, applies migrations, seeds 12 sample questions across 4 categories, and creates a default admin account:

| Field    | Value             |
|----------|-------------------|
| Username | `admin`           |
| Email    | `admin@brainova.com`|
| Password | `admin123`        |

> Change the admin password from the user-management page after first login.

## Database schema

| Table | Purpose |
|-------|---------|
| `users` | Account credentials, `is_admin` flag |
| `questions` | The question pool (text, category, optional difficulty) |
| `answers` | Multiple-choice options per question |
| `tests` | Admin-defined tests (time limit, count, category filter, shuffle, status) |
| `test_results` | Per-attempt summary (score, total, IQ, optional `test_id`) |
| `test_answers` | Per-question detail for each result |
| `notifications` | One row per recipient — fanned out at publish time |

## API & Routes

All endpoints are server-rendered Flask routes (HTML responses, form-based POSTs). Blueprints are registered in `app.py`.

### Root

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Landing page; redirects logged-in users to their dashboard |

### Auth (`routes/auth.py`)

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/register` | Create a new user account |
| GET / POST | `/login` | Authenticate and start a session |
| GET | `/logout` | Clear session |

### Profile (`routes/profile.py`, prefix `/profile`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/profile/dashboard` | User dashboard: stats, latest result, available tests |
| GET | `/profile/` | View own profile |
| GET / POST | `/profile/edit` | Edit profile |

### Test (`routes/test.py`, prefix `/test`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/test/` | Start the legacy Quick Brainova Test |
| GET / POST | `/test/take` | Take and submit the quick test |
| GET | `/test/list` | List admin-published tests |
| GET / POST | `/test/<test_id>/begin` | Take and submit a published test |
| GET | `/test/<test_id>/leaderboard` | Per-test leaderboard |
| GET | `/test/result/<result_id>` | Detailed result review |
| POST | `/test/result/<result_id>/delete` | Delete own result |
| GET | `/test/result/<result_id>/download/pdf` | Download result as PDF |
| GET | `/test/result/<result_id>/download/excel` | Download result as Excel |

### Admin (`routes/admin.py`, prefix `/admin`, all `@admin_required`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/` | Admin dashboard + platform stats |
| GET | `/admin/questions` | List all questions |
| GET / POST | `/admin/questions/add` | Add a question manually |
| POST | `/admin/questions/generate` | AI-generate 10 questions (Gemini) for review |
| POST | `/admin/questions/generate/submit` | Persist reviewed AI-generated questions |
| GET / POST | `/admin/questions/edit/<q_id>` | Edit a question |
| POST | `/admin/questions/delete/<q_id>` | Delete a question |
| GET | `/admin/tests` | List all tests |
| GET / POST | `/admin/tests/new` | Create a new test |
| GET / POST | `/admin/tests/<test_id>/edit` | Edit a test |
| POST | `/admin/tests/<test_id>/publish` | Publish + fan out notifications |
| POST | `/admin/tests/<test_id>/unpublish` | Unpublish a test |
| POST | `/admin/tests/<test_id>/delete` | Delete a test |
| GET | `/admin/users` | List users |
| GET / POST | `/admin/users/<user_id>/edit` | Edit a user |
| POST | `/admin/users/<user_id>/delete` | Delete a user (admin accounts protected) |

### Notifications (`routes/notifications.py`, prefix `/notifications`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/notifications/` | Inbox view |
| POST | `/notifications/<note_id>/read` | Mark a notification as read |
| POST | `/notifications/<note_id>/delete` | Delete a notification |

### Cross-cutting

- **Auth guards** — `@login_required` on user routes, `@admin_required` on every `/admin/*` route.
- **Template context** — `unread_notifications` is injected globally so the navbar badge is available on every page.
- **Result authorization** — `_load_result_for_user` ensures users can only read or export their own results.

## Example admin workflow

1. Log in as `admin`.
2. Open **Manage Questions** and either add manually or click **Generate** (requires Gemini key) to bulk-create questions.
3. Open **Manage Tests** → **New Test**:
   - Title: *"Logical Reasoning Sprint"*
   - Time limit: `15`
   - Questions: `10`
   - Category: `logical`
   - Shuffle: on
   - Status: `published`
4. Save. Every normal user instantly receives a notification.
5. Users open their dashboard, see the test in *Available Tests*, click **Start**, take it, and submit. Their result is stored against the originating `test_id` for later analytics.

## Design notes

- **Notification fanout** — a notification is inserted **per recipient** at publish time (write-time fanout). This trades a tiny amount of storage for O(1) per-user reads, keeping the navbar badge query trivial as the user base grows.
- **Runtime randomization** — `tests.shuffle` is honored at request time inside `_select_questions_for_test()`. The form posts back the exact `q_ids` the user saw, so scoring is correct even when the question pool changes between renders.
- **Pool-size guard** — `num_questions` is validated both at create/edit *and* at publish time, because the pool can shrink between drafting and publishing.
- **Authorization** — `@admin_required` and `@login_required` decorators gate every privileged route; user-facing test routes return 404 for any test not in the `published` status.
- **Migrations** — additive columns are applied in `database.py` via `PRAGMA table_info` checks, so the existing `brainova.db` upgrades in place without manual SQL.

## License

For internal/educational use.
