# Brainova — Ranking System

Brainova has **two distinct ranking surfaces**, each driven by a different SQL query and serving a different audience:

| Surface | Audience | Scope | Where |
|---|---|---|---|
| **Per-test leaderboard** | All logged-in users | One specific published test, current calendar month | [routes/test.py:530](routes/test.py#L530) (`test.leaderboard`) |
| **Admin dashboard ranking** | Admins only | All users, all-time, optionally filtered to one test | [routes/admin.py:61](routes/admin.py#L61) (`admin.dashboard`) |

Both surfaces share the same **competition ranking** algorithm and the same `_ordinal()` formatter, but they answer different questions. The leaderboard answers *"who is the best on this test this month?"*; the admin ranking answers *"who is performing well on the platform overall?"*.

---

## 1. Shared algorithm — competition ranking ("1224")

Both ranking views use **competition ranking**: tied scores share the same rank, and the next distinct score skips ahead by the size of the tied group.

```
IQ 145  → 1st
IQ 140  → 2nd
IQ 140  → 2nd   ← tie
IQ 130  → 4th   ← skips 3rd because two users are tied at 2nd
IQ 120  → 5th
```

Implementation pattern (used in both files):

```python
prev_iq = sentinel
last_rank = 0
for i, row in enumerate(rows, start=1):
    if row['best_iq'] != prev_iq:
        last_rank = i
        prev_iq = row['best_iq']
    row['rank'] = last_rank
```

The list is already ORDER BY'd by `best_iq DESC` before this loop runs, so a single pass is enough. Display order *within* a tied group is broken deterministically by an earlier secondary sort (earliest `taken_at` wins), but the **rank number itself** stays tied — only the visual position differs.

### Ordinal labels

`_ordinal(n)` ([routes/admin.py:17](routes/admin.py#L17), [routes/test.py:599](routes/test.py#L599)) renders rank numbers as English ordinals: `1 → "1st"`, `2 → "2nd"`, `3 → "3rd"`, `4 → "4th"`, `21 → "21st"`, `113 → "113th"`. Numbers in the **11–13 range** get `"th"` regardless of last digit (`11th`, `12th`, `13th`), which is the case most naive ordinal helpers get wrong.

---

## 2. Per-test monthly leaderboard

Route: `GET /test/<test_id>/leaderboard` ([routes/test.py:530](routes/test.py#L530))

Template: [templates/test/leaderboard.html](templates/test/leaderboard.html)

### Window — current calendar month

The leaderboard **resets at the start of every calendar month**. Past results are not deleted (the user can still see them in their history and exports), they just stop appearing on the leaderboard once the month rolls over.

```python
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
next_month  = month_start + 1 month
WHERE taken_at >= month_start AND taken_at < next_month
```

The window is computed as half-open `[month_start, next_month)` so attempts on the very last second of the month are included and attempts on the very first second of the next month are not. December → January is handled explicitly.

`taken_at` is stored by SQLite as `'YYYY-MM-DD HH:MM:SS'`, which is **lexicographically sortable** as ISO-style — so the string comparison in the WHERE clause is correct without any date casting.

### Ranking rule — best IQ per user, this month

A user with multiple attempts in the month appears **once**, ranked by their highest in-month IQ score. The query has three parts:

1. **`best` subquery** — for each user, find their max `iq_score` on this test in this month.
2. **Main query** — join back to `test_results` to fetch the row that produced that max IQ.
3. **`attempts` correlated subquery** — count *all* of that user's attempts on this test in-month (not just the best one), so the leaderboard can show "5 attempts" alongside the best score.

```sql
SELECT tr.id, tr.user_id, u.username, tr.score, tr.total_questions,
       tr.iq_score, tr.taken_at,
       (SELECT COUNT(*) FROM test_results x
          WHERE x.user_id = tr.user_id
            AND x.test_id = ?
            AND x.taken_at >= ? AND x.taken_at < ?) AS attempts
FROM test_results tr
JOIN users u ON u.id = tr.user_id
JOIN (SELECT user_id, MAX(iq_score) AS best_iq
        FROM test_results
        WHERE test_id = ?
          AND taken_at >= ? AND taken_at < ?
        GROUP BY user_id) best
  ON best.user_id = tr.user_id
 AND best.best_iq = tr.iq_score
WHERE tr.test_id = ?
  AND tr.taken_at >= ? AND tr.taken_at < ?
GROUP BY tr.user_id
ORDER BY tr.iq_score DESC, MIN(tr.taken_at) ASC
```

The `GROUP BY tr.user_id` collapses the case where a user hit the same max IQ on two attempts (e.g., perfect scores) — only the earliest attempt represents them on the board. `ORDER BY ... MIN(tr.taken_at) ASC` then gives the **earlier achiever** the higher display position when IQs tie.

### Output shape

For each ranked entry the view computes:

| Field | Meaning |
|---|---|
| `rank`, `rank_label` | Competition rank as `int` and `"1st"` |
| `result_id` | The specific result row that earned the rank (so the row can link to the user's review) |
| `user_id`, `username` | Who they are; `is_me` flags the current viewer's row |
| `score`, `total_questions` | Raw correct count |
| `iq_score`, `accuracy` | The ranking key + a derived accuracy percent |
| `attempts` | How many times the user tried *this test* this month |
| `taken_at` | When the best attempt happened |
| `tied`, `tied_with` | True/N if other users share this exact rank |

### Podium

The template uses the entries to render a 1st/2nd/3rd podium. `_pick(rank_value)` returns the **first** entry with each podium rank, so when multiple users tie at e.g. rank 1 the podium shows one representative and the table beneath shows the others — `tied_with` lets the template render a "+N tied" badge. This keeps the podium layout clean while still being honest about ties.

### "My rank"

`my_rank` is set to the current user's competition rank if they appear on the board this month, otherwise `None`. The template uses it to render a "You're ranked Nth this month" banner, separately from the row highlight.

---

## 3. Admin dashboard ranking

Route: `GET /admin/?test_id=<id>` ([routes/admin.py:61](routes/admin.py#L61))

Template: [templates/admin/dashboard.html](templates/admin/dashboard.html)

### Audience

Admin-only. Renders alongside the platform stats card on the admin dashboard. The list is **capped at 10 users** — it is a leaderboard summary, not a paginated user explorer.

### Two modes

A query-string parameter switches the ranking scope:

| `test_id` query param | Mode | What's ranked |
|---|---|---|
| Empty / missing | **All recent results** (default) | Each user's best IQ across **every test they've taken** |
| Numeric (e.g. `?test_id=4`) | **Single-test mode** | Each user's best IQ on that specific test |
| Numeric but test was deleted | Falls back to default mode | Avoids a 404 if the dropdown loses sync mid-render |

The form is a simple `<select>` posting back to the same URL, so admins can flip between *"who's the best overall?"* and *"who's the best on test X?"* without leaving the dashboard.

### Query

The base SELECT groups by user and uses `MAX(tr.iq_score)` as the ranking key:

```sql
SELECT u.id AS user_id, u.username,
       MAX(tr.iq_score) AS best_iq,
       COUNT(tr.id)     AS attempts,
       MAX(tr.taken_at) AS latest
  FROM test_results tr
  JOIN users u ON u.id = tr.user_id
 [WHERE tr.test_id = ?]                       -- single-test mode only
 GROUP BY u.id
 ORDER BY best_iq DESC, latest ASC
 LIMIT 10
```

In **default mode** an additional correlated subquery pulls the title of the test that produced the user's best IQ (`'Quick Brainova Test'` if `test_id IS NULL`) so the table can show the *"best test"* column alongside their score. Ties in `best_iq` are broken by **earlier** `latest` — the user who reached that IQ first gets the higher rank.

### Differences from the leaderboard

| Aspect | Per-test leaderboard | Admin dashboard ranking |
|---|---|---|
| **Time window** | Current calendar month | All-time |
| **Scope** | One published test | All tests, optionally filtered |
| **Audience** | All logged-in users | Admins only |
| **Size** | Unbounded | Top 10 |
| **Tie-breaker** | Earlier `taken_at` of the best attempt | Earlier `latest` (most-recent attempt overall) |
| **Reset** | Monthly | Never |
| **Extra column** | `attempts` this month | `attempts` lifetime, `best_test_title` (default mode) |

The admin view exists for **operational visibility** ("are people using the platform? who are the power users?"), while the leaderboard exists for **per-test competition** ("who's winning *this* contest *this* month?").

---

## 4. IQ score — the ranking key

Both rankings sort by `iq_score`, computed at submit-time by `calculate_iq()` ([routes/test.py:31](routes/test.py#L31)) from the raw correct-answer count:

```
pct = score / total_questions
if pct <= 0.5:  iq = 70 + pct * 60          # 0% → 70, 50% → 100
else:           iq = 100 + (pct - 0.5) * 90 # 50% → 100, 100% → 145
```

This is a **piecewise-linear** mapping, not a real psychometric IQ — it gives more granularity in the upper half of the score range so a top scorer separates more clearly from a near-top scorer. The output is clamped to roughly 70–145 and stored as an integer.

A side effect: two users with **identical raw scores on identical-length tests will always have identical IQ scores**, so the system genuinely ties them rather than separating them by anything noisy. That's why the tie handling above matters.

`_iq_label()` ([routes/test.py:155](routes/test.py#L155)) maps the IQ score to a human label — `Below Average`, `Low Average`, `Average`, `High Average`, `Superior`, `Very Superior` — used in result pages and exports, but **not** in ranking sort order.

---

## 5. Edge cases & invariants

- **Empty leaderboard** — first day of the month before anyone has taken the test: `entries` is `[]`, `total_players` is 0, `podium` is `{first: None, second: None, third: None}`. The template renders an empty state.
- **User deletes their own result** — `/test/result/<id>/delete` removes the row outright. They drop off the leaderboard and admin ranking immediately on the next render. No tombstone.
- **Admin deletes a user** — `delete_user` cascades through `test_answers` and `test_results` ([routes/admin.py:884-892](routes/admin.py#L884-L892)), so the user disappears from every ranking on the next render.
- **Admin deletes a test** — `delete_test` sets `test_results.test_id = NULL` rather than deleting the result rows ([routes/admin.py:858-862](routes/admin.py#L858-L862)). Those orphaned results no longer appear on any per-test leaderboard, but they **do** still count toward the user's lifetime ranking on the admin dashboard (default mode), which is the intended behavior.
- **Editing a question after attempts exist** — `edit_question` clears `selected_answer_id` on historical `test_answers` to make the answer-row delete succeed, but **preserves `is_correct`** ([routes/admin.py:438-457](routes/admin.py#L438-L457)). Past `iq_score` values therefore stay frozen in time, which keeps historical rankings stable even when the question pool evolves.
- **Month rollover** — there is no scheduled job. The leaderboard query simply uses `datetime.now()` at request time, so the moment the calendar flips to the new month the board is empty and starts filling up again.
