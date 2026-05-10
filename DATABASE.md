# Brainova — Database Design

SQLite database (`brainova.db`). Schema is created by `database.py:init_db()`
from `schema.sql`, with two runtime migrations applied on top:

1. `questions.difficulty` is added if missing.
2. `test_results.test_id` is added if missing (`REFERENCES tests(id)`).

`PRAGMA foreign_keys = ON` is enabled on every connection.

---

## 1. Entity Overview

| Entity            | Purpose                                                            |
| ----------------- | ------------------------------------------------------------------ |
| `users`           | Account records. Both regular users and admins.                    |
| `questions`       | The reusable question pool, tagged by cognitive category.          |
| `answers`         | Multiple-choice options for each question; one is `is_correct=1`.  |
| `tests`           | Admin-defined tests. Questions are sampled from the pool at runtime. |
| `test_results`    | One row per attempt. Holds score, IQ score, and (optional) test link. |
| `test_answers`    | Per-question detail of an attempt (which option, correct?).        |
| `notifications`   | In-app notifications fanned out to users (e.g. "test published"). |

---

## 2. ER Diagram

```
                          ┌──────────────┐
                          │    users     │
                          │──────────────│
                          │ id (PK)      │
                          │ username     │
                          │ email        │
                          │ password     │
                          │ is_admin     │
                          │ created_at   │
                          └──────┬───────┘
                                 │ 1
              ┌──────────────────┼──────────────────────────┐
              │                  │                          │
              │ N                │ N                        │ N
   ┌──────────▼──────────┐ ┌─────▼──────────┐   ┌───────────▼───────────┐
   │       tests         │ │ test_results   │   │     notifications     │
   │─────────────────────│ │────────────────│   │───────────────────────│
   │ id (PK)             │ │ id (PK)        │   │ id (PK)               │
   │ title               │ │ user_id (FK)   │   │ user_id (FK)          │
   │ description         │ │ test_id (FK?)  │   │ test_id (FK?)         │
   │ time_limit          │ │ score          │   │ title                 │
   │ num_questions       │ │ total_questions│   │ message               │
   │ category            │ │ iq_score       │   │ is_read               │
   │ shuffle             │ │ taken_at       │   │ created_at            │
   │ status              │ └─────┬──────────┘   └───────────────────────┘
   │ created_by (FK)     │       │ 1
   │ created_at          │       │ N
   │ updated_at          │ ┌─────▼──────────────┐
   │ published_at        │ │   test_answers     │
   └─────────┬───────────┘ │────────────────────│
             │ 1           │ id (PK)            │
             │ N           │ result_id (FK)     │
             │ (via        │ question_id (FK)   │
             │  test_id)   │ selected_answer_id │     ┌──────────────────┐
             │             │ is_correct         │ N─1 │     answers      │
             │             └────────┬───────────┘     │──────────────────│
             │                      │ N               │ id (PK)          │
             │                      │ (selected)      │ question_id (FK) │
             │                      └────────────────►│ option_text      │
             │                                        │ is_correct       │
             │                                        └─────────┬────────┘
             │                                                  │ N
             │                                                  │ 1
             │                                       ┌──────────▼───────┐
             │                                       │    questions     │
             │                                       │──────────────────│
             │                                       │ id (PK)          │
             │                                       │ question_text    │
             │                                       │ category         │
             │                                       │ difficulty       │
             │                                       │ created_at       │
             │                                       └──────────────────┘
```

---

## 3. Tables

### 3.1 `users`

| Column      | Type      | Constraints                          | Notes                                |
| ----------- | --------- | ------------------------------------ | ------------------------------------ |
| id          | INTEGER   | PK, AUTOINCREMENT                    |                                      |
| username    | TEXT      | NOT NULL, UNIQUE                     |                                      |
| email       | TEXT      | NOT NULL, UNIQUE                     | Lowercased in app code.              |
| password    | TEXT      | NOT NULL                             | Werkzeug `generate_password_hash`.   |
| is_admin    | INTEGER   | DEFAULT 0                            | 0/1 boolean.                         |
| created_at  | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP            |                                      |

A default admin (`admin / admin123`) is seeded by `init_db()` if no admin exists.

### 3.2 `questions`

| Column         | Type      | Constraints                                                       |
| -------------- | --------- | ----------------------------------------------------------------- |
| id             | INTEGER   | PK, AUTOINCREMENT                                                 |
| question_text  | TEXT      | NOT NULL                                                          |
| category       | TEXT      | NOT NULL, CHECK ∈ {logical, verbal, numerical, spatial}           |
| difficulty     | INTEGER   | NULLABLE (1–5; populated by Gemini-generated questions)           |
| created_at     | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP                                         |

### 3.3 `answers`

| Column       | Type    | Constraints                                                |
| ------------ | ------- | ---------------------------------------------------------- |
| id           | INTEGER | PK, AUTOINCREMENT                                          |
| question_id  | INTEGER | NOT NULL, FK → `questions(id)` **ON DELETE CASCADE**       |
| option_text  | TEXT    | NOT NULL                                                   |
| is_correct   | INTEGER | DEFAULT 0 (0/1)                                            |

Exactly one row per question must have `is_correct = 1` (enforced in app code).

### 3.4 `tests`

Admin-defined tests. The question list is **not** stored here — the engine
samples `num_questions` rows from `questions` at runtime, optionally filtered
by `category`.

| Column         | Type      | Constraints                                                  |
| -------------- | --------- | ------------------------------------------------------------ |
| id             | INTEGER   | PK, AUTOINCREMENT                                            |
| title          | TEXT      | NOT NULL                                                     |
| description    | TEXT      |                                                              |
| time_limit     | INTEGER   | NOT NULL, minutes                                            |
| num_questions  | INTEGER   | NOT NULL                                                     |
| category       | TEXT      | NULL = mixed pool                                            |
| shuffle        | INTEGER   | NOT NULL, DEFAULT 1                                          |
| status         | TEXT      | NOT NULL, CHECK ∈ {draft, published, unpublished}            |
| created_by     | INTEGER   | NOT NULL, FK → `users(id)`                                   |
| created_at     | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP                                    |
| updated_at     | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP                                    |
| published_at   | TIMESTAMP | NULL until first publish                                     |

**Index:** `idx_tests_status` on `status` (the user-facing list filters by `status='published'`).

### 3.5 `test_results`

One row per completed attempt.

| Column           | Type      | Constraints                                                  |
| ---------------- | --------- | ------------------------------------------------------------ |
| id               | INTEGER   | PK, AUTOINCREMENT                                            |
| user_id          | INTEGER   | NOT NULL, FK → `users(id)`                                   |
| test_id          | INTEGER   | **NULLABLE**, FK → `tests(id)` (added via migration)         |
| score            | INTEGER   | NOT NULL, raw correct count                                  |
| total_questions  | INTEGER   | NOT NULL                                                     |
| iq_score         | INTEGER   | NOT NULL                                                     |
| taken_at         | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP                                    |

`test_id IS NULL` means the legacy / quick-start Brainova test
(no admin-defined parent). Deleting a test sets `test_id = NULL` on its
results so historical scores stay queryable (see `admin.delete_test`).

### 3.6 `test_answers`

Per-question record for a result, used by the answer-review screen.

| Column              | Type    | Constraints                                          |
| ------------------- | ------- | ---------------------------------------------------- |
| id                  | INTEGER | PK, AUTOINCREMENT                                    |
| result_id           | INTEGER | NOT NULL, FK → `test_results(id)`                    |
| question_id         | INTEGER | NOT NULL, FK → `questions(id)`                       |
| selected_answer_id  | INTEGER | NULLABLE, FK → `answers(id)`                         |
| is_correct          | INTEGER | DEFAULT 0 (0/1, captured at submit time)             |

`is_correct` is denormalised so historical scores stay correct even if a
question's answers are later edited. When admins edit a question's options,
`selected_answer_id` is nulled out for past rows (the option text is gone)
but `is_correct` is preserved — so the score stays right; just the "your
selected option" view will read as unanswered.

### 3.7 `notifications`

| Column      | Type      | Constraints                                                |
| ----------- | --------- | ---------------------------------------------------------- |
| id          | INTEGER   | PK, AUTOINCREMENT                                          |
| user_id     | INTEGER   | NOT NULL, FK → `users(id)` **ON DELETE CASCADE**           |
| test_id     | INTEGER   | NULLABLE, FK → `tests(id)` **ON DELETE CASCADE**           |
| title       | TEXT      | NOT NULL                                                   |
| message     | TEXT      | NOT NULL                                                   |
| is_read     | INTEGER   | NOT NULL, DEFAULT 0                                        |
| created_at  | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP                                  |

**Index:** `idx_notifications_user_unread` on `(user_id, is_read)` — powers
the unread-counter badge in the navbar.

---

## 4. Relationships

| From               | → To              | Cardinality | On delete                              |
| ------------------ | ----------------- | ----------- | -------------------------------------- |
| `answers.question_id`         | `questions.id` | N → 1 | CASCADE                                |
| `tests.created_by`            | `users.id`     | N → 1 | (no action — admin protected by app)   |
| `test_results.user_id`        | `users.id`     | N → 1 | manual cascade in `admin.delete_user`  |
| `test_results.test_id`        | `tests.id`     | N → 1 | manual `SET NULL` in `admin.delete_test` |
| `test_answers.result_id`      | `test_results.id` | N → 1 | manual cascade                       |
| `test_answers.question_id`    | `questions.id` | N → 1 | manual cascade in `admin.delete_question` |
| `test_answers.selected_answer_id` | `answers.id` | N → 1 | nulled out by `admin.edit_question`  |
| `notifications.user_id`       | `users.id`     | N → 1 | CASCADE                                |
| `notifications.test_id`       | `tests.id`     | N → 1 | CASCADE                                |

App-level cascades exist where the schema doesn't (no `ON DELETE CASCADE`
on `test_results` / `test_answers`) so historical rows can be deliberately
preserved instead of vanishing with their parent.

---

## 5. Indexes

| Index                              | Table         | Purpose                                |
| ---------------------------------- | ------------- | -------------------------------------- |
| `idx_tests_status`                 | tests         | Fast filter for published tests        |
| `idx_notifications_user_unread`    | notifications | Unread count for the bell icon         |

(SQLite auto-creates indexes on PK and UNIQUE columns: `users.username`,
`users.email`.)

---

## 6. Migrations

`database.py:init_db()` runs idempotent migrations on top of `schema.sql`:

| Migration                                    | Reason                                       |
| -------------------------------------------- | -------------------------------------------- |
| `ALTER TABLE questions ADD COLUMN difficulty INTEGER` | Added when Gemini-generated questions started carrying difficulty 1–5. |
| `ALTER TABLE test_results ADD COLUMN test_id INTEGER REFERENCES tests(id)` | Added when admin-defined tests were introduced. Existing rows keep `test_id IS NULL` and are treated as the legacy "Quick Brainova Test" bucket. |

Seeding:
- A default admin (`admin / admin123`) is inserted if no admin exists.
- 12 sample questions across all four categories are inserted on first run.

---

## 7. Key Query Patterns

- **Recent ranking (admin dashboard):** `GROUP BY u.id` over `test_results`,
  ordering by `MAX(iq_score) DESC, MAX(taken_at) ASC`. Optionally filtered
  by `tr.test_id = ?`.
- **Monthly leaderboard (per test):** restrict `taken_at` to the current
  calendar month, take each user's best attempt, competition-rank by
  `iq_score`.
- **Test attempt count (admin tests page):** correlated subquery
  `SELECT COUNT(*) FROM test_results WHERE test_id = t.id`.
- **Unread notifications:** `COUNT(*) WHERE user_id = ? AND is_read = 0`,
  served by `idx_notifications_user_unread`.
