from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file, jsonify, current_app
from werkzeug.security import generate_password_hash
from database import get_db
from routes.notifications import fanout_notification
from functools import wraps
import os
import io
import json
import base64
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

CATEGORIES = ['logical', 'verbal', 'numerical', 'spatial']


def _ordinal(n):
    """Return n as an English ordinal: 1 -> '1st', 22 -> '22nd', 113 -> '113th'."""
    # 11/12/13 are special cases — they all take 'th' regardless of last digit.
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


def _rank_users(rows):
    """Assign competition ranks (ties share a rank, the next rank skips).

    Input rows are already ordered by best_iq DESC. Returns a list of dicts
    with `rank` (int) and `rank_label` (e.g. '1st') added.
    """
    ranked = []
    prev_iq = object()  # sentinel that won't compare equal to any real score
    last_rank = 0
    for i, row in enumerate(rows, start=1):
        iq = row['best_iq']
        if iq != prev_iq:
            last_rank = i
            prev_iq = iq
        d = dict(row)
        d['rank'] = last_rank
        d['rank_label'] = _ordinal(last_rank)
        ranked.append(d)
    return ranked


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('auth.login'))
        if not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@admin_required
def dashboard():
    db = get_db()
    stats = {
        'users': db.execute('SELECT COUNT(*) FROM users WHERE is_admin = 0').fetchone()[0],
        'questions': db.execute('SELECT COUNT(*) FROM questions').fetchone()[0],
        'tests_taken': db.execute('SELECT COUNT(*) FROM test_results').fetchone()[0],
        'avg_iq': db.execute('SELECT AVG(iq_score) FROM test_results').fetchone()[0],
    }

    # Test selector for the ranking panel. A numeric id targets a specific
    # admin test; empty/missing = best-per-user across everything (default).
    selected_test = (request.args.get('test_id') or '').strip()
    selected_label = None
    selected_test_id = None  # numeric id, only set when a real test is chosen

    if selected_test:
        try:
            selected_test_id = int(selected_test)
        except ValueError:
            selected_test_id = None
            selected_test = ''

    tests_for_filter = db.execute(
        'SELECT id, title FROM tests ORDER BY created_at DESC'
    ).fetchall()

    # Group by user so each person appears once on the ranking, with their
    # best IQ score as the ranking key and the total attempt count shown
    # alongside. `latest` is the timestamp of their most recent attempt in
    # the selected scope and breaks ties (earlier achievement wins) as well
    # as feeding the "Latest attempt" column.
    base_select = (
        '''SELECT u.id AS user_id, u.username,
                  MAX(tr.iq_score) AS best_iq,
                  COUNT(tr.id) AS attempts,
                  MAX(tr.taken_at) AS latest
           FROM test_results tr
           JOIN users u ON u.id = tr.user_id'''
    )
    # In the unfiltered "All recent results" view the admin wants to see
    # which test produced each user's best IQ — pull the title from the
    # attempt that matches the user's max iq_score (earliest taken_at wins
    # ties so the column is deterministic).
    all_select = (
        '''SELECT u.id AS user_id, u.username,
                  MAX(tr.iq_score) AS best_iq,
                  COUNT(tr.id) AS attempts,
                  MAX(tr.taken_at) AS latest,
                  (SELECT COALESCE(t2.title, 'Quick Brainova Test')
                     FROM test_results tr2
                     LEFT JOIN tests t2 ON t2.id = tr2.test_id
                     WHERE tr2.user_id = u.id
                     ORDER BY tr2.iq_score DESC, tr2.taken_at ASC
                     LIMIT 1
                  ) AS best_test_title
           FROM test_results tr
           JOIN users u ON u.id = tr.user_id'''
    )
    order_clause = ' GROUP BY u.id ORDER BY best_iq DESC, latest ASC LIMIT 10'

    if selected_test_id is not None:
        test_row = db.execute(
            'SELECT title FROM tests WHERE id = ?', (selected_test_id,)
        ).fetchone()
        if test_row:
            selected_label = test_row['title']
            rows = db.execute(
                base_select + ' WHERE tr.test_id = ?' + order_clause,
                (selected_test_id,)
            ).fetchall()
        else:
            # Test was deleted between the page render and the form submit —
            # fall back to the unfiltered view rather than 404'ing.
            selected_test = ''
            selected_test_id = None
            rows = db.execute(all_select + order_clause).fetchall()
    else:
        rows = db.execute(all_select + order_clause).fetchall()

    ranking = _rank_users(rows)

    db.close()
    if stats['avg_iq']:
        stats['avg_iq'] = round(stats['avg_iq'], 1)
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        ranking=ranking,
        tests_for_filter=tests_for_filter,
        selected_test=selected_test,
        selected_label=selected_label,
    )


@admin_bp.route('/questions')
@admin_required
def questions():
    category = request.args.get('category', '')
    db = get_db()
    if category and category in CATEGORIES:
        qs = db.execute(
            'SELECT * FROM questions WHERE category = ? ORDER BY id DESC',
            (category,)
        ).fetchall()
    else:
        qs = db.execute('SELECT * FROM questions ORDER BY id DESC').fetchall()

    # Per-category counts so the filter pills can show how many questions fall
    # into each bucket; `total` is the unfiltered count.
    counts = {
        cat: db.execute(
            'SELECT COUNT(*) FROM questions WHERE category = ?', (cat,)
        ).fetchone()[0]
        for cat in CATEGORIES
    }
    total = db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    db.close()
    return render_template('admin/questions.html', questions=qs,
                           categories=CATEGORIES, selected=category,
                           counts=counts, total=total)


@admin_bp.route('/questions/add', methods=['GET', 'POST'])
@admin_required
def add_question():
    if request.method == 'POST':
        q_text = request.form['question_text'].strip()
        category = request.form['category']
        options = [request.form.get(f'option_{i}', '').strip() for i in range(1, 6)]
        correct_idx = request.form.get('correct_answer')

        error = None
        if not q_text:
            error = 'Question text is required.'
        elif category not in CATEGORIES:
            error = 'Invalid category.'
        elif any(o == '' for o in options):
            error = 'All 5 answer options are required.'
        elif correct_idx is None:
            error = 'Please select the correct answer.'

        if error is None:
            db = get_db()
            cur = db.execute(
                'INSERT INTO questions (question_text, category) VALUES (?, ?)',
                (q_text, category)
            )
            q_id = cur.lastrowid
            for i, opt in enumerate(options):
                db.execute(
                    'INSERT INTO answers (question_id, option_text, is_correct) VALUES (?, ?, ?)',
                    (q_id, opt, 1 if str(i) == correct_idx else 0)
                )
            db.commit()
            db.close()
            flash('Question added successfully.', 'success')
            return redirect(url_for('admin.questions'))

        flash(error, 'danger')

    return render_template('admin/add_question.html', categories=CATEGORIES)


QUESTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "choices": {
                "type": "array",
                "items": {"type": "string"},
            },
            "answer": {"type": "string"},
            "difficulty": {"type": "integer"},
        },
        "required": ["text", "choices", "answer", "difficulty"],
        "propertyOrdering": ["text", "choices", "answer", "difficulty"],
    },
}


def _get_gemini_api_key():
    """Prefer env var; fall back to app.secret_key for backward compat."""
    return os.environ.get('GEMINI_API_KEY') or current_app.secret_key


@admin_bp.route('/questions/generate', methods=['POST'])
@admin_required
def generate_questions():
    category = request.form.get('category', '').strip().lower()
    if category not in CATEGORIES:
        flash('Please choose a valid category.', 'danger')
        return redirect(url_for('admin.dashboard'))

    api_key = _get_gemini_api_key()
    if not api_key:
        flash('GEMINI_API_KEY environment variable is not set on the server.', 'danger')
        return redirect(url_for('admin.dashboard'))

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        flash('The "google-genai" package is not installed. Run: pip install google-genai', 'danger')
        return redirect(url_for('admin.dashboard'))

    category_descriptions = {
        'logical': 'logical reasoning (syllogisms, deductive patterns, sequences, conditional logic)',
        'verbal': 'verbal reasoning (analogies, vocabulary, word relationships, odd-one-out)',
        'numerical': 'numerical reasoning (arithmetic, percentages, ratios, number sequences)',
        'spatial': 'spatial reasoning (shapes, geometry, rotations, visualization)',
    }
    topic = category_descriptions[category]

    prompt = (
        f"Generate exactly 10 high-quality IQ-test reasoning questions about {topic}.\n\n"
        "Return a JSON array of 10 dictionaries. Each dictionary must follow this schema:\n"
        '{"text": str, "choices": list of 4-5 strings, "answer": str, "difficulty": int (1-5)}\n\n'
        "Strict requirements:\n"
        "- `answer` MUST be one of the strings in `choices` (exact match).\n"
        "- Distractors (wrong answers) must be logically plausible — derivable from a "
        "common reasoning error or near-miss, never random or nonsensical.\n"
        "- Cover a spread of difficulties from 1 (easy) to 5 (hard).\n"
        "- No duplicate questions; each question stands alone without external context."
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QUESTION_SCHEMA,
            ),
        )
    except Exception as e:
        flash(f'Gemini API error: {e}', 'danger')
        return redirect(url_for('admin.dashboard'))

    text = response.text or ""
    try:
        questions = json.loads(text)
        if not isinstance(questions, list):
            raise ValueError("Expected a JSON array at the top level.")
    except (json.JSONDecodeError, ValueError) as e:
        flash(f'Model returned invalid JSON: {e}', 'danger')
        return redirect(url_for('admin.dashboard'))

    valid_questions = []
    skipped = 0
    for q in questions:
        q_text = (q.get('text') or '').strip()
        choices = q.get('choices') or []
        answer = q.get('answer')
        difficulty = q.get('difficulty')

        if not q_text or not isinstance(choices, list) or len(choices) < 2 or answer not in choices:
            skipped += 1
            continue

        valid_questions.append({
            'text': q_text,
            'choices': [str(c) for c in choices],
            'answer': answer,
            'difficulty': difficulty if isinstance(difficulty, int) else None,
        })

    if not valid_questions:
        flash('The model did not return any valid questions. Please try again.', 'warning')
        return redirect(url_for('admin.dashboard'))

    if skipped:
        flash(f'Skipped {skipped} invalid item(s) returned by the model.', 'warning')

    payload = {'category': category, 'questions': valid_questions}
    payload_b64 = base64.b64encode(
        json.dumps(payload).encode('utf-8')
    ).decode('ascii')

    return render_template(
        'admin/review_questions.html',
        category=category,
        questions=valid_questions,
        payload_b64=payload_b64,
    )


@admin_bp.route('/questions/generate/submit', methods=['POST'])
@admin_required
def submit_generated_questions():
    payload_b64 = request.form.get('payload', '')
    try:
        payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
        category = payload['category']
        questions = payload['questions']
        if category not in CATEGORIES or not isinstance(questions, list):
            raise ValueError('Invalid payload')
    except Exception:
        flash('The review payload was malformed. Please regenerate.', 'danger')
        return redirect(url_for('admin.dashboard'))

    db = get_db()
    inserted = 0
    rejected = 0

    for i, q in enumerate(questions):
        if request.form.get(f'accept_{i}') != '1':
            rejected += 1
            continue

        q_text = (q.get('text') or '').strip()
        choices = q.get('choices') or []
        answer = q.get('answer')
        difficulty = q.get('difficulty')

        if not q_text or not isinstance(choices, list) or len(choices) < 2 or answer not in choices:
            rejected += 1
            continue

        cur = db.execute(
            'INSERT INTO questions (question_text, category, difficulty) VALUES (?, ?, ?)',
            (q_text, category, difficulty if isinstance(difficulty, int) else None)
        )
        q_id = cur.lastrowid
        for opt in choices:
            db.execute(
                'INSERT INTO answers (question_id, option_text, is_correct) VALUES (?, ?, ?)',
                (q_id, opt, 1 if opt == answer else 0)
            )
        inserted += 1

    db.commit()
    db.close()

    msg = f'Saved {inserted} accepted {category} question(s).'
    if rejected:
        msg += f' Discarded {rejected} rejected question(s).'
    flash(msg, 'success' if inserted else 'warning')
    return redirect(url_for('admin.questions', category=category))


@admin_bp.route('/questions/edit/<int:q_id>', methods=['GET', 'POST'])
@admin_required
def edit_question(q_id):
    db = get_db()
    question = db.execute('SELECT * FROM questions WHERE id = ?', (q_id,)).fetchone()
    if not question:
        db.close()
        flash('Question not found.', 'danger')
        return redirect(url_for('admin.questions'))

    answers = db.execute(
        'SELECT * FROM answers WHERE question_id = ? ORDER BY id',
        (q_id,)
    ).fetchall()

    if request.method == 'POST':
        q_text = request.form['question_text'].strip()
        category = request.form['category']
        options = [request.form.get(f'option_{i}', '').strip() for i in range(1, 6)]
        correct_idx = request.form.get('correct_answer')

        error = None
        if not q_text:
            error = 'Question text is required.'
        elif category not in CATEGORIES:
            error = 'Invalid category.'
        elif any(o == '' for o in options):
            error = 'All 5 answer options are required.'
        elif correct_idx is None:
            error = 'Please select the correct answer.'

        if error is None:
            db.execute(
                'UPDATE questions SET question_text = ?, category = ? WHERE id = ?',
                (q_text, category, q_id)
            )
            # Past test_answers rows reference the soon-to-be-deleted answer
            # ids via selected_answer_id (FK without CASCADE). Null those out
            # so the delete succeeds. The is_correct flag on test_answers is
            # preserved, so historical scores stay correct — just the "your
            # selected option" text in the answer review will read as
            # unanswered for that one question.
            db.execute(
                'UPDATE test_answers SET selected_answer_id = NULL WHERE question_id = ?',
                (q_id,)
            )
            db.execute('DELETE FROM answers WHERE question_id = ?', (q_id,))
            for i, opt in enumerate(options):
                db.execute(
                    'INSERT INTO answers (question_id, option_text, is_correct) VALUES (?, ?, ?)',
                    (q_id, opt, 1 if str(i) == correct_idx else 0)
                )
            db.commit()
            db.close()
            flash('Question updated successfully.', 'success')
            return redirect(url_for('admin.questions'))

        db.close()
        flash(error, 'danger')
        return render_template('admin/edit_question.html', question=question,
                               answers=answers, categories=CATEGORIES)

    db.close()
    return render_template('admin/edit_question.html', question=question,
                           answers=answers, categories=CATEGORIES)


@admin_bp.route('/questions/delete/<int:q_id>', methods=['POST'])
@admin_required
def delete_question(q_id):
    db = get_db()
    # `test_answers` references both questions(id) and answers(id) without
    # ON DELETE CASCADE, so we must clear historical answer rows for this
    # question before SQLite will let us drop it. The answers (options) are
    # cleaned up automatically by the CASCADE on answers.question_id.
    db.execute('DELETE FROM test_answers WHERE question_id = ?', (q_id,))
    db.execute('DELETE FROM questions WHERE id = ?', (q_id,))
    db.commit()
    db.close()
    flash('Question deleted.', 'success')
    return redirect(url_for('admin.questions'))


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
@admin_required
def users():
    db = get_db()
    rows = db.execute(
        '''SELECT u.id, u.username, u.email, u.created_at,
                  COUNT(tr.id) AS test_count,
                  MAX(tr.iq_score) AS best_iq
           FROM users u
           LEFT JOIN test_results tr ON tr.user_id = u.id
           WHERE u.is_admin = 0
           GROUP BY u.id
           ORDER BY u.created_at DESC'''
    ).fetchall()
    db.close()
    return render_template('admin/users.html', users=rows)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        db.close()
        flash('User not found.', 'danger')
        return redirect(url_for('admin.users'))

    if user['is_admin']:
        db.close()
        flash('Admin accounts cannot be managed from this page.', 'danger')
        return redirect(url_for('admin.users'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')

        error = None
        if len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif not email or '@' not in email:
            error = 'A valid email is required.'
        elif new_password and len(new_password) < 6:
            error = 'New password must be at least 6 characters.'
        else:
            clash = db.execute(
                'SELECT id FROM users WHERE (username = ? OR email = ?) AND id != ?',
                (username, email, user_id)
            ).fetchone()
            if clash:
                error = 'Another user already has that username or email.'

        if error:
            flash(error, 'danger')
            db.close()
            return render_template('admin/edit_user.html', user=user)

        if new_password:
            db.execute(
                'UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?',
                (username, email, generate_password_hash(new_password), user_id)
            )
        else:
            db.execute(
                'UPDATE users SET username = ?, email = ? WHERE id = ?',
                (username, email, user_id)
            )
        db.commit()
        db.close()

        flash(f'User "{username}" updated.', 'success')
        return redirect(url_for('admin.users'))

    db.close()
    return render_template('admin/edit_user.html', user=user)


# ---------------------------------------------------------------------------
# Tests (admin-defined, published to users)
# ---------------------------------------------------------------------------

VALID_STATUSES = ('draft', 'published', 'unpublished')


def _available_question_count(db, category):
    """How many questions exist in the pool the test would draw from."""
    if category and category in CATEGORIES:
        return db.execute(
            'SELECT COUNT(*) FROM questions WHERE category = ?', (category,)
        ).fetchone()[0]
    return db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]


def _parse_test_form(form, db):
    """Validate and normalize the test create/edit form.

    Returns (data_dict, error_message). If error_message is set, data_dict
    still holds the user's input so the form can be re-rendered with values
    preserved.
    """
    title = (form.get('title') or '').strip()
    description = (form.get('description') or '').strip()
    category = (form.get('category') or '').strip().lower() or None
    shuffle = 1 if form.get('shuffle') else 0
    status = (form.get('status') or 'draft').strip().lower()

    # Coerce numeric inputs defensively — HTML form values are always strings.
    try:
        time_limit = int(form.get('time_limit') or 0)
    except ValueError:
        time_limit = 0
    try:
        num_questions = int(form.get('num_questions') or 0)
    except ValueError:
        num_questions = 0

    data = {
        'title': title,
        'description': description,
        'category': category,
        'shuffle': shuffle,
        'status': status,
        'time_limit': time_limit,
        'num_questions': num_questions,
    }

    if not title:
        return data, 'Title is required.'
    if category is not None and category not in CATEGORIES:
        return data, 'Invalid category.'
    if status not in VALID_STATUSES:
        return data, 'Invalid status.'
    if time_limit <= 0:
        return data, 'Time limit must be a positive number of minutes.'
    if num_questions <= 0:
        return data, 'Number of questions must be a positive integer.'

    # Business rule: cannot ask for more questions than the pool can supply.
    available = _available_question_count(db, category)
    if num_questions > available:
        scope = f'in the "{category}" category' if category else 'in the database'
        return data, (
            f'Only {available} questions are available {scope}; '
            f'you requested {num_questions}.'
        )

    return data, None


@admin_bp.route('/tests')
@admin_required
def tests():
    db = get_db()
    rows = db.execute(
        '''SELECT t.*, u.username AS created_by_name,
                  (SELECT COUNT(*) FROM test_results tr WHERE tr.test_id = t.id) AS attempts
           FROM tests t
           JOIN users u ON t.created_by = u.id
           ORDER BY t.created_at DESC'''
    ).fetchall()
    db.close()
    return render_template('admin/tests.html', tests=rows)


@admin_bp.route('/tests/new', methods=['GET', 'POST'])
@admin_required
def new_test():
    db = get_db()
    if request.method == 'POST':
        data, error = _parse_test_form(request.form, db)
        if error:
            db.close()
            flash(error, 'danger')
            return render_template('admin/test_form.html',
                                   test=data, categories=CATEGORIES,
                                   statuses=VALID_STATUSES, mode='new')

        now = datetime.utcnow().isoformat(timespec='seconds')
        published_at = now if data['status'] == 'published' else None
        cur = db.execute(
            '''INSERT INTO tests (title, description, time_limit, num_questions,
                                  category, shuffle, status, created_by,
                                  created_at, updated_at, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (data['title'], data['description'], data['time_limit'],
             data['num_questions'], data['category'], data['shuffle'],
             data['status'], session['user_id'], now, now, published_at)
        )
        test_id = cur.lastrowid

        # Only fan out notifications when the test is created already published.
        if data['status'] == 'published':
            recipients = fanout_notification(
                db,
                title=f'New test available: {data["title"]}',
                message=(
                    f'A new test "{data["title"]}" has been published. '
                    f'Time limit: {data["time_limit"]} min, '
                    f'{data["num_questions"]} questions.'
                ),
                test_id=test_id,
            )
            db.commit()
            db.close()
            flash(
                f'Test created and published. Notified {recipients} user(s).',
                'success',
            )
        else:
            db.commit()
            db.close()
            flash('Test created as draft. No notifications sent.', 'success')
        return redirect(url_for('admin.tests'))

    db.close()
    # Default values for fresh form
    blank = {'title': '', 'description': '', 'category': None, 'shuffle': 1,
             'status': 'draft', 'time_limit': 30, 'num_questions': 10}
    return render_template('admin/test_form.html', test=blank,
                           categories=CATEGORIES, statuses=VALID_STATUSES,
                           mode='new')


@admin_bp.route('/tests/<int:test_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_test(test_id):
    db = get_db()
    test = db.execute('SELECT * FROM tests WHERE id = ?', (test_id,)).fetchone()
    if not test:
        db.close()
        flash('Test not found.', 'danger')
        return redirect(url_for('admin.tests'))

    if request.method == 'POST':
        data, error = _parse_test_form(request.form, db)
        if error:
            db.close()
            flash(error, 'danger')
            # Preserve the row id so the form posts back to the right URL.
            data['id'] = test_id
            return render_template('admin/test_form.html', test=data,
                                   categories=CATEGORIES,
                                   statuses=VALID_STATUSES, mode='edit')

        now = datetime.utcnow().isoformat(timespec='seconds')
        # Preserve the original publish timestamp; only set it the first time
        # the test transitions to "published".
        published_at = test['published_at']
        first_publish = (
            data['status'] == 'published' and test['status'] != 'published'
        )
        if first_publish:
            published_at = now

        db.execute(
            '''UPDATE tests
               SET title = ?, description = ?, time_limit = ?, num_questions = ?,
                   category = ?, shuffle = ?, status = ?, updated_at = ?,
                   published_at = ?
               WHERE id = ?''',
            (data['title'], data['description'], data['time_limit'],
             data['num_questions'], data['category'], data['shuffle'],
             data['status'], now, published_at, test_id)
        )

        if first_publish:
            recipients = fanout_notification(
                db,
                title=f'Test published: {data["title"]}',
                message=(
                    f'"{data["title"]}" is now available to take. '
                    f'Time limit: {data["time_limit"]} min, '
                    f'{data["num_questions"]} questions.'
                ),
                test_id=test_id,
            )
            db.commit()
            db.close()
            flash(
                f'Test updated and published. Notified {recipients} user(s).',
                'success'
            )
        else:
            db.commit()
            db.close()
            flash('Test updated.', 'success')
        return redirect(url_for('admin.tests'))

    db.close()
    return render_template('admin/test_form.html', test=test,
                           categories=CATEGORIES, statuses=VALID_STATUSES,
                           mode='edit')


@admin_bp.route('/tests/<int:test_id>/publish', methods=['POST'])
@admin_required
def publish_test(test_id):
    db = get_db()
    test = db.execute('SELECT * FROM tests WHERE id = ?', (test_id,)).fetchone()
    if not test:
        db.close()
        flash('Test not found.', 'danger')
        return redirect(url_for('admin.tests'))

    # Re-validate question count at publish-time — the pool may have shrunk
    # since the draft was created.
    available = _available_question_count(db, test['category'])
    if test['num_questions'] > available:
        db.close()
        flash(
            f'Cannot publish: only {available} questions available, '
            f'test needs {test["num_questions"]}.',
            'danger'
        )
        return redirect(url_for('admin.tests'))

    now = datetime.utcnow().isoformat(timespec='seconds')
    first_publish = test['status'] != 'published'
    db.execute(
        '''UPDATE tests SET status = 'published', updated_at = ?,
           published_at = COALESCE(published_at, ?) WHERE id = ?''',
        (now, now, test_id)
    )

    if first_publish:
        recipients = fanout_notification(
            db,
            title=f'Test published: {test["title"]}',
            message=(
                f'"{test["title"]}" is now available to take. '
                f'Time limit: {test["time_limit"]} min, '
                f'{test["num_questions"]} questions.'
            ),
            test_id=test_id,
        )
        db.commit()
        db.close()
        flash(f'Test published. Notified {recipients} user(s).', 'success')
    else:
        db.commit()
        db.close()
        flash('Test re-published.', 'success')
    return redirect(url_for('admin.tests'))


@admin_bp.route('/tests/<int:test_id>/unpublish', methods=['POST'])
@admin_required
def unpublish_test(test_id):
    db = get_db()
    now = datetime.utcnow().isoformat(timespec='seconds')
    db.execute(
        "UPDATE tests SET status = 'unpublished', updated_at = ? WHERE id = ?",
        (now, test_id)
    )
    db.commit()
    db.close()
    flash('Test unpublished. Users can no longer see it.', 'success')
    return redirect(url_for('admin.tests'))


@admin_bp.route('/tests/<int:test_id>/delete', methods=['POST'])
@admin_required
def delete_test(test_id):
    db = get_db()
    # Detach existing results so the foreign-key reference doesn't keep them
    # tied to a now-deleted test row.
    db.execute('UPDATE test_results SET test_id = NULL WHERE test_id = ?', (test_id,))
    db.execute('DELETE FROM notifications WHERE test_id = ?', (test_id,))
    db.execute('DELETE FROM tests WHERE id = ?', (test_id,))
    db.commit()
    db.close()
    flash('Test deleted.', 'success')
    return redirect(url_for('admin.tests'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    db = get_db()
    user = db.execute('SELECT username, is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        db.close()
        flash('User not found.', 'danger')
        return redirect(url_for('admin.users'))

    if user['is_admin']:
        db.close()
        flash('Admin accounts cannot be deleted from this page.', 'danger')
        return redirect(url_for('admin.users'))

    # Cascade manually: test_answers -> test_results -> users
    db.execute(
        '''DELETE FROM test_answers
           WHERE result_id IN (SELECT id FROM test_results WHERE user_id = ?)''',
        (user_id,)
    )
    db.execute('DELETE FROM test_results WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    db.close()

    flash(f'User "{user["username"]}" and all their test results were deleted.', 'success')
    return redirect(url_for('admin.users'))
