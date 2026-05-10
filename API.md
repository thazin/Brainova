# Brainova — API & Routes

## About the API

Brainova does **not** expose a JSON REST API. All endpoints are server-rendered **Flask** routes that return HTML (via Jinja2) or, in a few cases, binary file downloads (PDF, Excel). State-changing actions are driven by **HTML form POSTs**, not by JSON request bodies. There are no API tokens, no `Authorization` headers, and no CORS layer — the app is consumed exclusively by a browser session.

### Architecture

- **Framework**: Flask 3 ([app.py](app.py)) with a single app instance and five blueprints.
- **Blueprints** (registered in [app.py:12-16](app.py#L12-L16)):
  - `auth` — register / login / logout, no URL prefix.
  - `admin` — `/admin/*`, gated by `@admin_required`.
  - `profile` — `/profile/*`, gated by `@login_required`.
  - `test` — `/test/*`, gated by `@login_required`.
  - `notifications` — `/notifications/*`, gated by `@login_required`.
- **Persistence**: SQLite via [database.py](database.py). Each request opens a connection, runs its queries, commits, and closes — no ORM, no connection pool.
- **Templates**: server-side rendering with Jinja2 in [templates/](templates/). The `unread_notifications` count is injected into every template by a context processor in [app.py:20](app.py#L20) so the navbar badge works on every page.

### Request / response conventions

| Aspect | Convention |
|---|---|
| **Read endpoints** | `GET`, return rendered HTML |
| **Write endpoints** | `POST` with `application/x-www-form-urlencoded` form data |
| **GET + POST on same URL** | The route renders the form on `GET` and processes it on `POST` (e.g. `/register`, `/admin/tests/new`) |
| **Validation errors** | Re-render the same form with a `flash(..., 'danger')` message; no 4xx status code |
| **Success after POST** | `redirect()` to a clean GET URL (Post/Redirect/Get pattern), often with a `flash(..., 'success')` |
| **Authorization failure** | Redirect to `/login` (unauthenticated) or `/` (non-admin hitting `/admin`) with a flash message |
| **Resource-not-found** | `abort(404)` for hidden resources (draft tests, others' notifications); flash + redirect for user-facing "not found" cases (own deleted result) |
| **Binary downloads** | `send_file()` with `as_attachment=True` for PDF and Excel result exports |

### Authentication & sessions

- Authentication is **session-cookie based**. On successful `/login`, the route stores `user_id`, `username`, and `is_admin` in `session` ([routes/auth.py:75-77](routes/auth.py#L75-L77)).
- Passwords are hashed with `werkzeug.security.generate_password_hash` (PBKDF2 by default) and verified with `check_password_hash`. Plain-text passwords are never stored.
- Two decorators enforce route-level access:
  - `@login_required` — defined per blueprint (e.g. [routes/profile.py:9](routes/profile.py#L9)). Redirects unauthenticated requests to `/login`.
  - `@admin_required` — [routes/admin.py:48](routes/admin.py#L48). Requires `session['is_admin']` to be true; otherwise redirects with a flash message.
- `/logout` calls `session.clear()` and redirects to `/login`.

### Authorization model

Authorization is enforced **inside each handler**, not by middleware:

- **Result access** — `_load_result_for_user` ([routes/test.py:170](routes/test.py#L170)) joins on `tr.user_id = ?`, so any user attempting to read or export another user's result gets a "not found" response, not a 403. Same pattern for `delete_result`, `download_pdf`, `download_excel`.
- **Notification access** — `mark_read` and `delete` ([routes/notifications.py:89-119](routes/notifications.py#L89-L119)) verify `note.user_id == session['user_id']` and `abort(404)` otherwise.
- **Admin-only resources** — every `/admin/*` route is decorated with `@admin_required`; admin user accounts are additionally protected from edits/deletes through `/admin/users/*` ([routes/admin.py:521](routes/admin.py#L521), [routes/admin.py:879](routes/admin.py#L879)).
- **Hidden tests** — `/test/<id>/begin` and `/test/<id>/leaderboard` filter by `status = 'published'`; draft and unpublished tests return 404 to non-admins.

### Cross-cutting features

- **Flash messages** — used everywhere for user feedback (`success`, `danger`, `warning`, `info`). Rendered by the base template's flash partial.
- **Notification fanout** — `fanout_notification` ([routes/notifications.py:21](routes/notifications.py#L21)) inserts one row per non-admin user at publish time. Trades storage for O(1) per-user reads, which keeps the navbar unread-count query trivial as the user base grows.
- **AI-generated questions** — `/admin/questions/generate` calls Google Gemini (`google-genai`) with a structured-output JSON schema, then renders a review page. Nothing is persisted until the admin accepts items in `/admin/questions/generate/submit`.
- **Result exports** — PDFs are built with ReportLab; Excel workbooks with openpyxl. Both are streamed back via `send_file` with no temp files.
- **Pool-size guard** — `num_questions` is validated at create, edit, **and** publish time, because the question pool can shrink between drafting and publishing ([routes/admin.py:631-638](routes/admin.py#L631-L638), [routes/admin.py:798-808](routes/admin.py#L798-L808)).
- **Runtime randomization** — `tests.shuffle` is honored at request time inside `_select_questions_for_test` ([routes/test.py:416](routes/test.py#L416)). The form posts back the exact `q_ids` the user actually saw, so scoring stays correct even when the question pool changes between renders.

### What this API is *not*

- **Not stateless** — every request relies on the session cookie.
- **Not JSON** — there are no `application/json` request or response bodies. (Gemini responses are parsed internally but never exposed.)
- **Not versioned** — no `/v1/` prefix; URLs are stable but unversioned.
- **Not CSRF-protected** — there is no Flask-WTF / CSRF token layer. State-changing POSTs rely on the session cookie alone, which is acceptable for the current intranet/educational scope but is the first thing to add if this is exposed publicly.
- **Not rate-limited** — there is no per-IP or per-user throttling on login, registration, or AI generation.

---

## Routes

All endpoints are server-rendered Flask routes (HTML responses, form-based POSTs). Blueprints are registered in [app.py](app.py).

## Root

| Method | URL | Name | Description |
|---|---|---|---|
| GET | `/` | `index` | Landing page. Redirects logged-in admins to the admin dashboard and normal users to the profile dashboard. |

## Auth — [routes/auth.py](routes/auth.py)

| Method | URL | Name | Description |
|---|---|---|---|
| GET / POST | `/register` | `auth.register` | Show the registration form (GET) and create a new user account (POST). Validates username length, password length, and uniqueness of username/email. |
| GET / POST | `/login` | `auth.login` | Show the login form (GET) and authenticate the user (POST). Accepts username **or** email as the identifier. Starts a session and redirects to the appropriate dashboard. |
| GET | `/logout` | `auth.logout` | Clear the session and redirect to the login page. |

## Profile — [routes/profile.py](routes/profile.py) (prefix `/profile`)

| Method | URL | Name | Description |
|---|---|---|---|
| GET | `/profile/dashboard` | `profile.dashboard` | User landing page. Shows stats (tests taken, best IQ, available tests, unread notifications), the latest 4 published tests, and the 5 most recent results. |
| GET | `/profile/` | `profile.view` | View the logged-in user's profile and their 10 most recent results. |
| GET / POST | `/profile/edit` | `profile.edit` | Show the profile-edit form (GET) and update username, email, and (optionally) password (POST). Requires the current password to change the password. |

## Test — [routes/test.py](routes/test.py) (prefix `/test`)

| Method | URL | Name | Description |
|---|---|---|---|
| GET | `/test/` | `test.start` | Start page for the legacy Quick Brainova Test. Shows per-category counts and the user's last result. |
| GET / POST | `/test/take` | `test.take` | GET renders the quick test (all questions, randomized order). POST scores submitted answers, computes the IQ, persists the result and per-question rows, then redirects to the result page. |
| GET | `/test/list` | `test.list_published` | Catalog of all admin-published tests visible to a normal user. |
| GET / POST | `/test/<test_id>/begin` | `test.begin` | GET renders an admin-published test (questions selected and optionally shuffled at request time). POST scores the exact `q_ids` the user saw, persists the result against the originating `test_id`, and redirects to the result page. Returns 404 for non-published tests. |
| GET | `/test/<test_id>/leaderboard` | `test.leaderboard` | Monthly top scorers for a single published test. Uses competition ranking (ties share a rank), resets at the start of each calendar month, and highlights the logged-in user's row. |
| GET | `/test/result/<result_id>` | `test.result` | Detailed result review with per-question breakdown (selected vs. correct answer, category, correctness). Authorized to the result's owner only. |
| POST | `/test/result/<result_id>/delete` | `test.delete_result` | Delete the user's own result and its per-question rows. Authorized to the result's owner only. |
| GET | `/test/result/<result_id>/download/pdf` | `test.download_pdf` | Download the result as a styled PDF (ReportLab) with summary table and answer review. Owner only. |
| GET | `/test/result/<result_id>/download/excel` | `test.download_excel` | Download the result as an Excel workbook (openpyxl) with two sheets: Summary and Answer Review. Owner only. |

## Admin — [routes/admin.py](routes/admin.py) (prefix `/admin`, all `@admin_required`)

| Method | URL | Name | Description |
|---|---|---|---|
| GET | `/admin/` | `admin.dashboard` | Admin dashboard. Shows platform stats (users, questions, tests taken, average IQ) and a top-10 user ranking with optional `?test_id=` filter. |
| GET | `/admin/questions` | `admin.questions` | List all questions, optionally filtered by `?category=`. Shows per-category counts. |
| GET / POST | `/admin/questions/add` | `admin.add_question` | Show (GET) and submit (POST) the manual add-question form. Requires 5 options and a marked correct answer. |
| POST | `/admin/questions/generate` | `admin.generate_questions` | Use Gemini to generate 10 reasoning questions for a given category. Renders a review page; nothing is persisted yet. Requires `GEMINI_API_KEY`. |
| POST | `/admin/questions/generate/submit` | `admin.submit_generated_questions` | Persist the subset of AI-generated questions the admin accepted on the review page. |
| GET / POST | `/admin/questions/edit/<q_id>` | `admin.edit_question` | Show (GET) and submit (POST) the edit-question form. Replaces the answer rows; clears `selected_answer_id` on historical `test_answers` to preserve scores. |
| POST | `/admin/questions/delete/<q_id>` | `admin.delete_question` | Delete a question. Removes referencing `test_answers` rows first; option rows cascade. |
| GET | `/admin/tests` | `admin.tests` | List all tests with creator and per-test attempt count. |
| GET / POST | `/admin/tests/new` | `admin.new_test` | Show (GET) and submit (POST) the new-test form. Validates time limit, question count vs. pool size, category, and status. If created as `published`, fans out notifications. |
| GET / POST | `/admin/tests/<test_id>/edit` | `admin.edit_test` | Show (GET) and submit (POST) the edit-test form. Fans out notifications only on the first transition into `published`. |
| POST | `/admin/tests/<test_id>/publish` | `admin.publish_test` | Publish a test. Re-validates the question pool at publish time. Fans out notifications only on first publish. |
| POST | `/admin/tests/<test_id>/unpublish` | `admin.unpublish_test` | Mark a test as `unpublished`. Hides it from users immediately. |
| POST | `/admin/tests/<test_id>/delete` | `admin.delete_test` | Delete a test. Detaches existing `test_results` (sets `test_id = NULL`) and removes related notifications. |
| GET | `/admin/users` | `admin.users` | List non-admin users with their test count and best IQ. |
| GET / POST | `/admin/users/<user_id>/edit` | `admin.edit_user` | Show (GET) and submit (POST) the edit-user form. Admin accounts are protected. Password is optional. |
| POST | `/admin/users/<user_id>/delete` | `admin.delete_user` | Delete a non-admin user and cascade their `test_answers` and `test_results`. Admin accounts are protected. |

## Notifications — [routes/notifications.py](routes/notifications.py) (prefix `/notifications`)

| Method | URL | Name | Description |
|---|---|---|---|
| GET | `/notifications/` | `notifications.inbox` | Inbox view. Fetches the user's notifications (newest first) and marks all unread ones as read after rendering. |
| POST | `/notifications/<note_id>/read` | `notifications.mark_read` | Mark a single notification as read. Owner only — returns 404 otherwise. |
| POST | `/notifications/<note_id>/delete` | `notifications.delete` | Delete a single notification. Owner only — returns 404 otherwise. |

## Cross-cutting

- **Auth guards** — `@login_required` on user routes, `@admin_required` on every `/admin/*` route.
- **Template context** — `unread_notifications` is injected globally so the navbar badge is available on every page (see [app.py:20](app.py#L20)).
- **Result authorization** — `_load_result_for_user` ensures users can only read or export their own results.
- **Notification fanout** — `fanout_notification` in [routes/notifications.py:21](routes/notifications.py#L21) inserts one row per non-admin user at publish time, keeping per-user reads O(1).
