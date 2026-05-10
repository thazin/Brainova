from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from functools import wraps

profile_bp = Blueprint('profile', __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access that page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@profile_bp.route('/dashboard')
@login_required
def dashboard():
    """Landing page for normal users after login."""
    db = get_db()
    user = db.execute(
        'SELECT username FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()

    last_result = db.execute(
        'SELECT * FROM test_results WHERE user_id = ? ORDER BY taken_at DESC LIMIT 1',
        (session['user_id'],)
    ).fetchone()

    stats = {
        'tests_taken': db.execute(
            'SELECT COUNT(*) FROM test_results WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()[0],
        'best_iq': db.execute(
            'SELECT MAX(iq_score) FROM test_results WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()[0],
        'available_tests': db.execute(
            "SELECT COUNT(*) FROM tests WHERE status = 'published'"
        ).fetchone()[0],
        'unread_notifications': db.execute(
            'SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0',
            (session['user_id'],)
        ).fetchone()[0],
    }

    available_tests = db.execute(
        '''SELECT * FROM tests WHERE status = 'published'
           ORDER BY COALESCE(published_at, created_at) DESC LIMIT 4'''
    ).fetchall()

    recent_results = db.execute(
        '''SELECT tr.*, t.title AS test_title
           FROM test_results tr
           LEFT JOIN tests t ON tr.test_id = t.id
           WHERE tr.user_id = ?
           ORDER BY tr.taken_at DESC LIMIT 5''',
        (session['user_id'],)
    ).fetchall()
    db.close()

    return render_template(
        'profile/dashboard.html',
        user=user,
        last_result=last_result,
        stats=stats,
        available_tests=available_tests,
        recent_results=recent_results,
    )


@profile_bp.route('/')
@login_required
def view():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    results = db.execute(
        'SELECT * FROM test_results WHERE user_id = ? ORDER BY taken_at DESC LIMIT 10',
        (session['user_id'],)
    ).fetchall()
    db.close()
    return render_template('profile/profile.html', user=user, results=results)


@profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        error = None
        if not username or not email:
            error = 'Username and email are required.'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters.'
        else:
            conflict = db.execute(
                'SELECT id FROM users WHERE (username = ? OR email = ?) AND id != ?',
                (username, email, session['user_id'])
            ).fetchone()
            if conflict:
                error = 'Username or email already in use by another account.'

        if error is None and new_password:
            if not check_password_hash(user['password'], current_password):
                error = 'Current password is incorrect.'
            elif len(new_password) < 6:
                error = 'New password must be at least 6 characters.'
            elif new_password != confirm_password:
                error = 'New passwords do not match.'

        if error is None:
            if new_password:
                db.execute(
                    'UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?',
                    (username, email, generate_password_hash(new_password), session['user_id'])
                )
            else:
                db.execute(
                    'UPDATE users SET username = ?, email = ? WHERE id = ?',
                    (username, email, session['user_id'])
                )
            db.commit()
            session['username'] = username
            db.close()
            flash('Profile updated successfully.', 'success')
            return redirect(url_for('profile.view'))

        db.close()
        flash(error, 'danger')
    else:
        db.close()

    return render_template('profile/edit.html', user=user)
