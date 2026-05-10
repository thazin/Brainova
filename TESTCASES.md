# Brainova — Test Cases

Manual test cases covering every feature exposed in the Flask app. Use the default admin (`admin` / `admin123`) for admin flows; create a separate normal user for user flows.

## 1. Authentication

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Auth | 1 | TC-AUTH-01 | Register a new user with valid data | 1. Open `/register`. 2. Enter unique username, email, password. 3. Submit. | Account is created, user is redirected to login (or dashboard) and can log in. |
| Auth | 2 | TC-AUTH-02 | Register with duplicate username | 1. Register a user. 2. Try to register again with the same username. | Registration is rejected with an error message; no duplicate row in `users`. |
| Auth | 3 | TC-AUTH-03 | Register with empty fields | 1. Open `/register`. 2. Submit with one or more fields blank. | Form is rejected; validation message shown. |
| Auth | 4 | TC-AUTH-04 | Login with valid credentials | 1. Open `/login`. 2. Enter valid username + password. 3. Submit. | User is redirected to `/profile/dashboard` (or `/admin/` for admin). |
| Auth | 5 | TC-AUTH-05 | Login with wrong password | 1. Open `/login`. 2. Enter valid username + wrong password. | Login fails with an error message; no session created. |
| Auth | 6 | TC-AUTH-06 | Login with non-existent user | 1. Open `/login`. 2. Enter unknown username. | Login fails with an error message. |
| Auth | 7 | TC-AUTH-07 | Logout clears session | 1. Log in. 2. Visit `/logout`. 3. Try to open `/profile/dashboard`. | Session is cleared; user is redirected to `/login`. |
| Auth | 8 | TC-AUTH-08 | Access protected route while logged out | 1. Without logging in, open `/profile/dashboard` or `/test/`. | Redirected to `/login`. |
| Auth | 9 | TC-AUTH-09 | Non-admin cannot access admin pages | 1. Log in as a normal user. 2. Visit `/admin/`. | Access denied / redirected (not admin dashboard). |

## 2. Profile & User Dashboard

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Profile | 10 | TC-PROF-01 | View user dashboard | 1. Log in as user. 2. Open `/profile/dashboard`. | Page shows user's stats, latest result, and available published tests. |
| Profile | 11 | TC-PROF-02 | View own profile | 1. Log in. 2. Open `/profile/`. | Profile details are displayed. |
| Profile | 12 | TC-PROF-03 | Edit profile with valid data | 1. Open `/profile/edit`. 2. Change username/email. 3. Save. | Changes persist and are reflected on `/profile/`. |
| Profile | 13 | TC-PROF-04 | Edit profile with duplicate email | 1. Open `/profile/edit`. 2. Set email to one that already exists. 3. Save. | Update is rejected with an error message. |
| Profile | 14 | TC-PROF-05 | Unread notification badge appears | 1. As admin, publish a test. 2. Log in as user. 3. Look at navbar. | Navbar shows unread-count badge > 0. |

## 3. Quick Brainova Test

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| QuickTest | 15 | TC-QT-01 | Start quick test | 1. Log in as user. 2. Open `/test/`. | Test start page is shown. |
| QuickTest | 16 | TC-QT-02 | Take and submit quick test | 1. Open `/test/take`. 2. Answer all questions. 3. Submit. | Result page is displayed with score, total, and IQ. |
| QuickTest | 17 | TC-QT-03 | Submit quick test with no answers | 1. Open `/test/take`. 2. Submit without answering. | Result is recorded with score 0; user is redirected to result page. |
| QuickTest | 18 | TC-QT-04 | Per-question countdown timer | 1. Start `/test/take`. 2. Wait without answering. | Timer auto-advances or auto-submits per `static/js/test.js` behavior. |
| QuickTest | 19 | TC-QT-05 | Answer order changes between attempts | 1. Take quick test twice. 2. Compare answer ordering for the same question. | Answers are randomized per render. |

## 4. Published Tests

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| PubTest | 20 | TC-PT-01 | List published tests | 1. Log in as user. 2. Open `/test/list`. | Only tests with status `published` are listed. |
| PubTest | 21 | TC-PT-02 | Begin a published test | 1. Open `/test/list`. 2. Click a test → `/test/<id>/begin`. | Test page shows the configured number of questions and a timer matching `time_limit`. |
| PubTest | 22 | TC-PT-03 | Submit published test | 1. Begin a published test. 2. Answer all. 3. Submit. | Result is saved with the originating `test_id`; user lands on result page. |
| PubTest | 23 | TC-PT-04 | Access draft / unpublished test directly | 1. As admin, create a test in `draft` status. 2. As user, open `/test/<id>/begin`. | 404 (route only serves `published` tests). |
| PubTest | 24 | TC-PT-05 | Shuffle off — fixed order | 1. Admin creates test with shuffle=off. 2. User begins it twice. | Question order is identical across attempts. |
| PubTest | 25 | TC-PT-06 | Shuffle on — randomized order | 1. Admin creates test with shuffle=on. 2. User begins it twice. | Question order differs across attempts. |
| PubTest | 26 | TC-PT-07 | Per-test leaderboard | 1. Multiple users submit a test. 2. Open `/test/<id>/leaderboard`. | Top scorers listed in descending score order. |
| PubTest | 27 | TC-PT-08 | Tampered q_ids in submission | 1. On the take page, modify hidden `q_ids`. 2. Submit. | Scoring still operates on the submitted ids; no server crash; result is consistent with submitted set. |

## 5. Results & Export

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Result | 28 | TC-RES-01 | View own result detail | 1. Take a test. 2. Open `/test/result/<result_id>`. | Result with answer review is displayed. |
| Result | 29 | TC-RES-02 | View another user's result | 1. Log in as user A. 2. Open `/test/result/<id_of_user_B>`. | 404 / forbidden — `_load_result_for_user` blocks access. |
| Result | 30 | TC-RES-03 | Delete own result | 1. Open own result. 2. POST `/test/result/<id>/delete`. | Result + linked `test_answers` are removed; user redirected to dashboard. |
| Result | 31 | TC-RES-04 | Download result as PDF | 1. Open own result. 2. Click *Download PDF*. | PDF file downloads, contains score/IQ and question review. |
| Result | 32 | TC-RES-05 | Download result as Excel | 1. Open own result. 2. Click *Download Excel*. | `.xlsx` file downloads, contains score/IQ and question review. |
| Result | 33 | TC-RES-06 | Download other user's result | 1. As user A, hit `/test/result/<id_of_user_B>/download/pdf`. | 404 / forbidden. |
| Result | 34 | TC-RES-07 | IQ label maps to range | 1. Submit results across score ranges. 2. Inspect labels on result page. | Label matches `_iq_label` boundaries. |

## 6. Admin Dashboard

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Admin | 35 | TC-ADM-01 | View admin dashboard | 1. Log in as admin. 2. Open `/admin/`. | Stats: total users, questions, tests taken, average IQ are shown. |
| Admin | 36 | TC-ADM-02 | User ranking on dashboard | 1. Have multiple users with different IQ averages. 2. Open `/admin/`. | Users are ordered correctly with proper ordinal ranks. |

## 7. Question Management (Manual)

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Question | 37 | TC-Q-01 | List all questions | 1. Open `/admin/questions`. | All questions displayed grouped/listed by category. |
| Question | 38 | TC-Q-02 | Add question with valid data | 1. Open `/admin/questions/add`. 2. Fill question, category, options, mark correct. 3. Save. | Question + answers saved; visible in list. |
| Question | 39 | TC-Q-03 | Add question with no correct answer | 1. Open add form. 2. Submit without selecting a correct option. | Form is rejected with error. |
| Question | 40 | TC-Q-04 | Edit question | 1. Open `/admin/questions/edit/<id>`. 2. Modify text/options. 3. Save. | Changes persist. |
| Question | 41 | TC-Q-05 | Delete question | 1. From list, POST `/admin/questions/delete/<id>`. | Question + its answers removed. |
| Question | 42 | TC-Q-06 | Non-admin cannot reach question CRUD | 1. As normal user, GET `/admin/questions`. | Access denied. |

## 8. AI Question Generator

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| AIGen | 43 | TC-AI-01 | Generate questions with valid Gemini key | 1. Set `GEMINI_API_KEY`. 2. Restart app. 3. POST `/admin/questions/generate` for a category. | Review page shows ~10 generated questions with options. |
| AIGen | 44 | TC-AI-02 | Generate without API key | 1. Unset `GEMINI_API_KEY`. 2. Click *Generate*. | Friendly error displayed; manual flow still works. |
| AIGen | 45 | TC-AI-03 | Submit selected generated questions | 1. On review page, keep some, deselect others. 2. POST `/admin/questions/generate/submit`. | Only selected questions persisted. |
| AIGen | 46 | TC-AI-04 | Generate with invalid category | 1. POST `/admin/questions/generate` with unknown category. | Request rejected gracefully. |

## 9. Test Management

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Test | 47 | TC-TM-01 | List all tests | 1. Open `/admin/tests`. | All tests with their status displayed. |
| Test | 48 | TC-TM-02 | Create a draft test | 1. `/admin/tests/new`. 2. Fill title, time, count, category, shuffle. Status=draft. Save. | Test saved as `draft`; not visible to users. |
| Test | 49 | TC-TM-03 | Create test exceeding pool size | 1. New test with `num_questions` > available pool. 2. Save. | Validation error blocks save. |
| Test | 50 | TC-TM-04 | Edit test | 1. Open `/admin/tests/<id>/edit`. 2. Change time/count. Save. | Changes persist. |
| Test | 51 | TC-TM-05 | Publish a valid test | 1. POST `/admin/tests/<id>/publish` on a draft test with sufficient pool. | Status flips to `published`; notifications fanned out to all non-admin users. |
| Test | 52 | TC-TM-06 | Publish blocked when pool shrinks | 1. Create draft with N questions. 2. Delete enough questions so pool < N. 3. Publish. | Publish rejected; status remains `draft`. |
| Test | 53 | TC-TM-07 | Unpublish a test | 1. POST `/admin/tests/<id>/unpublish` on a published test. | Status flips to `unpublished`; test no longer in user's published list. |
| Test | 54 | TC-TM-08 | Delete a test | 1. POST `/admin/tests/<id>/delete`. | Test row removed; related notifications/results behave per schema constraints. |
| Test | 55 | TC-TM-09 | Category filter respected | 1. Create a test filtered by `logical`. 2. User takes it. | Only logical-category questions appear. |
| Test | 56 | TC-TM-10 | Mixed-pool test | 1. Create a test with no category filter. 2. User takes it. | Questions can come from any category. |

## 10. User Management

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Users | 57 | TC-UM-01 | List users | 1. Open `/admin/users`. | All users displayed, admins flagged. |
| Users | 58 | TC-UM-02 | Edit normal user | 1. Open `/admin/users/<id>/edit`. 2. Change username/email. Save. | Changes persist. |
| Users | 59 | TC-UM-03 | Delete normal user | 1. POST `/admin/users/<id>/delete` on a non-admin. | User removed from list. |
| Users | 60 | TC-UM-04 | Delete admin account is blocked | 1. POST `/admin/users/<admin_id>/delete`. | Operation blocked with error; admin row remains. |

## 11. Notifications

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Notif | 61 | TC-NT-01 | Fanout on publish | 1. Have N non-admin users. 2. Admin publishes a test. | N rows inserted in `notifications`, one per recipient. |
| Notif | 62 | TC-NT-02 | Inbox view | 1. Log in as user. 2. Open `/notifications/`. | All received notifications listed (newest first). |
| Notif | 63 | TC-NT-03 | Mark notification as read | 1. POST `/notifications/<id>/read`. | Notification marked read; navbar badge decrements. |
| Notif | 64 | TC-NT-04 | Delete notification | 1. POST `/notifications/<id>/delete`. | Notification removed from inbox. |
| Notif | 65 | TC-NT-05 | Cross-user access blocked | 1. As user A, POST `/notifications/<id_of_user_B>/read`. | Operation rejected (no effect on B's row). |
| Notif | 66 | TC-NT-06 | Admin does not get badge | 1. Log in as admin. 2. Inspect navbar. | `unread_notifications` is 0; no inbox link surfaced for admin. |

## 12. Database & Migrations

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| DB | 67 | TC-DB-01 | First-run bootstrap | 1. Delete `brainova.db`. 2. Run `python app.py`. | DB recreated, schema applied, seed data + default admin inserted. |
| DB | 68 | TC-DB-02 | Idempotent migrations | 1. Run app on existing DB. | No duplicate columns; app starts cleanly. |
| DB | 69 | TC-DB-03 | Default admin login works after bootstrap | 1. Fresh DB. 2. Log in with `admin` / `admin123`. | Login succeeds and lands on admin dashboard. |

## 13. Security / Authorization

| Category | No | ID | TestCase | Steps | Expected Result |
|---|---|---|---|---|---|
| Sec | 70 | TC-SEC-01 | Direct admin URL as user | 1. As normal user, GET `/admin/tests/new`. | Access denied / redirected. |
| Sec | 71 | TC-SEC-02 | CSRF / form forgery on POST | 1. Submit forged POST to `/admin/questions/delete/<id>` from outside the app. | Behavior depends on Flask config — verify it does not act on unauthenticated requests. |
| Sec | 72 | TC-SEC-03 | SQL injection in login | 1. Submit `' OR 1=1 --` in username field. | Login fails; queries are parameterized. |
| Sec | 73 | TC-SEC-04 | Password storage | 1. Inspect `users.password` after register. | Passwords are hashed (not stored in plaintext). |
| Sec | 74 | TC-SEC-05 | Session expiry on logout | 1. Log in. 2. Logout. 3. Use browser back button + refresh on a protected page. | Page is no longer accessible; redirected to login. |
